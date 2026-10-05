"""Full backtest of the game algorithms.

Three parts, all read-only towards live games:

1. **Historical replay** - every finished round in the window is recomputed
   from its revealed server seed: SHA-256(seed) must equal the commitment
   published before betting, the recomputed outcome must equal the stored
   one, and every bet must have been settled exactly as the rules say
   (status, multiplier and payout to the paisa).
2. **Statistical fairness** - large Monte-Carlo runs of the engines' own
   provably-fair functions with a fresh random seed: chi-square tests for
   WinGo numbers and Mines tiles, the Aviator crash distribution against its
   closed form, and simulated vs theoretical return for every bet type.
3. **Hold** - what the house kept vs what the payout tables predict.

The report is stored (``backtest.latest``) so the super admin page can show
it, plus a short history of earlier runs.
"""

from __future__ import annotations

import json
import math
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import comb
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.games.aviator.rules import CURRENT_CRASH_FORMULA, compute_crash_point, crash_formula_of
from app.games.mines.rules import compute_mines_multiplier_bp, derive_mine_positions
from app.games.simulated_players import BOT_NAMES
from app.games.wingo.rules import (
    MODES, WingoOutcome, compute_outcome, number_colours, number_size, payout_x100, payouts_from_config,
)
from app.models.game import GameEntry, GameRound, GameSetting
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.hold_analyzer import WINGO_PICKS, aviator_rtp, aviator_win_probability, mines_rtp, wingo_ev
from app.utils.rng import hash_server_seed

LATEST_KEY = "backtest.latest"
HISTORY_KEY = "backtest.history"
FINISHED = ("COMPLETED", "HISTORY", "SETTLED")
MAX_ISSUES = 20


# ---------------------------------------------------------------- statistics
def _gammainc_upper(a: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(a, x) (Numerical Recipes, series / continued fraction)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, total, delta = a, 1.0 / a, 1.0 / a
        for _ in range(500):
            ap += 1
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-14:
                break
        return max(0.0, 1.0 - total * math.exp(-x + a * math.log(x) - gln))
    b = x + 1 - a
    c = 1 / 1e-300
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - gln) * h)


def chi_square(observed: List[int], expected: List[float]) -> Dict[str, Any]:
    stat = sum((o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0)
    df = len(observed) - 1
    return {"statistic": round(stat, 3), "df": df, "p_value": round(_gammainc_upper(df / 2, stat / 2), 4)}


def _check(name: str, ok: bool, detail: str, warn_only: bool = False) -> Dict[str, Any]:
    return {"name": name, "status": "pass" if ok else ("warn" if warn_only else "fail"), "detail": detail}


# ---------------------------------------------------------------- 1. historical replay
def _wingo_entry_issue(entry: GameEntry, drawn: WingoOutcome, payouts: Dict[str, int]) -> Optional[str]:
    sel = entry.selection or {}
    mult = payout_x100(str(sel.get("type", "")), str(sel.get("value", "")), drawn, payouts)
    want_status = "WON" if mult else "LOST"
    want_payout = entry.bet_amount * mult // 100 if mult else 0
    if entry.status != want_status:
        return f"status {entry.status}, rules say {want_status}"
    if entry.payout_amount != want_payout:
        return f"paid {entry.payout_amount}, rules say {want_payout}"
    return None


def _aviator_entry_issue(entry: GameEntry, crash_x100: int) -> Optional[str]:
    sel = entry.selection or {}
    if entry.status == "WON":
        m = int(entry.multiplier or 0)
        if m < 100 or m > crash_x100:
            return f"cashed out at {m / 100:.2f}x but the plane crashed at {crash_x100 / 100:.2f}x"
        if entry.payout_amount != entry.bet_amount * m // 100:
            return f"paid {entry.payout_amount}, {m / 100:.2f}x of {entry.bet_amount} is {entry.bet_amount * m // 100}"
        return None
    if entry.status == "LOST":
        target = sel.get("auto_cashout")
        if target is not None and int(round(float(target) * 100)) < crash_x100:
            return f"auto cash-out {float(target):.2f}x was reached (crash {crash_x100 / 100:.2f}x) but the bet lost"
        return None
    return None


def _mines_entry_issue(entry: GameEntry, mines: set) -> Optional[str]:
    sel = entry.selection or {}
    stored = set(sel.get("mines") or [])
    if stored and stored != mines:
        return "stored mine layout differs from the seed"
    revealed = list(sel.get("revealed_tiles") or [])
    hit = [t for t in revealed if t in mines]
    if entry.status == "LOST":
        if not hit or revealed[-1] not in mines:
            return "marked lost but no mine was opened"
        if entry.payout_amount != 0:
            return f"lost bet paid {entry.payout_amount}"
        return None
    if entry.status == "WON":
        if hit:
            return "won although a mine was opened"
        mult = compute_mines_multiplier_bp(len(revealed), int(sel.get("mine_count", 0)), int(sel.get("house_edge_bp", 300)))
        if int(entry.multiplier or 0) != mult or entry.payout_amount != entry.bet_amount * mult // 100:
            return f"paid {entry.payout_amount} at {(entry.multiplier or 0) / 100:.2f}x, rules say {entry.bet_amount * mult // 100} at {mult / 100:.2f}x"
    return None


def _teen_patti_entry_issue(entry: GameEntry, winner: str, payout_x100: int) -> Optional[str]:
    side = (entry.selection or {}).get("value")
    if winner == "TIE":
        if entry.status != "WON" or entry.payout_amount != entry.bet_amount:
            return f"tie should refund {entry.bet_amount}, bet is {entry.status} paid {entry.payout_amount}"
        return None
    if side == winner:
        expected = entry.bet_amount * payout_x100 // 100
        if entry.status != "WON" or entry.payout_amount != expected:
            return f"Player {side} won: expected {expected}, bet is {entry.status} paid {entry.payout_amount}"
        return None
    if entry.status != "LOST" or entry.payout_amount:
        return f"Player {side} lost but bet is {entry.status} paid {entry.payout_amount}"
    return None


async def historical_replay(db: AsyncSession, days: int, max_rounds: int) -> Dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    bot_ids = set((await db.execute(select(User.id).where(User.username.in_(BOT_NAMES)))).scalars().all())
    groups = ["aviator", "mines", *MODES, "teen_patti"]
    out: Dict[str, Any] = {}
    for game_id in groups:
        rounds = (await db.execute(
            select(GameRound)
            .where(GameRound.game_id == game_id, GameRound.status.in_(FINISHED), GameRound.server_seed.isnot(None),
                   GameRound.created_at >= since)
            .order_by(GameRound.round_no.desc()).limit(max_rounds)
        )).scalars().all()
        g = {
            "rounds": len(rounds), "hash_ok": 0, "outcome_ok": 0, "bets": 0, "settled_ok": 0, "open_in_finished": 0,
            "wagered": 0, "paid": 0, "expected_paid": 0.0, "real_wagered": 0, "real_paid": 0,
            "issues": [], "outcomes": defaultdict(int),
        }
        entries_by_round: Dict[str, List[GameEntry]] = defaultdict(list)
        ids = [r.id for r in rounds]
        for i in range(0, len(ids), 500):
            for e in (await db.execute(select(GameEntry).where(GameEntry.round_id.in_(ids[i:i + 500])))).scalars().all():
                entries_by_round[e.round_id].append(e)

        def issue(r: GameRound, what: str, entry: Optional[GameEntry] = None) -> None:
            if len(g["issues"]) < MAX_ISSUES:
                g["issues"].append({"round_no": r.round_no, "round_id": r.id, "entry_id": entry.id if entry else None, "problem": what})

        for r in rounds:
            seed, client = r.server_seed or "", r.client_seed or r.id
            result = r.result or {}
            if hash_server_seed(seed) == r.server_seed_hash:
                g["hash_ok"] += 1
            else:
                issue(r, "revealed seed does not match the published hash")

            entries = entries_by_round.get(r.id, [])
            if game_id in MODES:
                drawn = compute_outcome(seed, client, r.round_no)
                g["outcomes"][drawn.number] += 1
                if result.get("number") == drawn.number:
                    g["outcome_ok"] += 1
                else:
                    issue(r, f"stored number {result.get('number')}, seed gives {drawn.number}")
                payouts = result.get("payouts_x100") or payouts_from_config(None)
                checker = lambda e, drawn=drawn, payouts=payouts: _wingo_entry_issue(e, drawn, payouts)  # noqa: E731
                ev = lambda e, payouts=payouts: wingo_ev(str((e.selection or {}).get("type", "")), str((e.selection or {}).get("value", "")), payouts) or 0  # noqa: E731
            elif game_id == "teen_patti":
                from app.games.teen_patti.rules import compute_outcome as teen_patti_outcome

                hand = teen_patti_outcome(seed, client, r.round_no)
                g["outcomes"][hand.winner] += 1
                if result.get("winner") == hand.winner and result.get("player_a") == hand.player_a and result.get("player_b") == hand.player_b:
                    g["outcome_ok"] += 1
                else:
                    issue(r, f"stored winner {result.get('winner')}, seed gives {hand.winner}")
                tp_payout = int(result.get("payout_x100") or 196)
                checker = lambda e, w=hand.winner, p=tp_payout: _teen_patti_entry_issue(e, w, p)  # noqa: E731
                # each side wins ~49.94% of hands, ties (~0.12%) refund the stake
                ev = lambda e, p=tp_payout: 0.4994 * p / 100 + 0.0012  # noqa: E731
            elif game_id == "aviator":
                edge = int(result.get("house_edge_bp", 300))
                formula = crash_formula_of(result)
                crash = compute_crash_point(seed, client, r.round_no, edge, formula)
                bucket = "1.00x" if crash == 100 else "<2x" if crash < 200 else "2-10x" if crash < 1000 else "10x+"
                g["outcomes"][bucket] += 1
                if int(result.get("crash_point_x100", -1)) == crash:
                    g["outcome_ok"] += 1
                else:
                    issue(r, f"stored crash {result.get('crash_point_x100')}, seed gives {crash}")
                checker = lambda e, crash=crash: _aviator_entry_issue(e, crash)  # noqa: E731
                ev = lambda e, edge=edge, f=formula: aviator_rtp(edge, int(round(float((e.selection or {}).get("auto_cashout") or 2) * 100)), f)  # noqa: E731
            else:  # mines: one round per session
                layout_ok = True
                for e in entries:
                    m = int((e.selection or {}).get("mine_count", 0) or 0)
                    if not 1 <= m <= 24:
                        continue
                    mines = derive_mine_positions(seed, r.client_seed or "", r.round_no, m)
                    stored = set((e.selection or {}).get("mines") or [])
                    layout_ok = layout_ok and (not stored or stored == mines)
                    g["outcomes"][f"{m} mines"] += 1
                if layout_ok:
                    g["outcome_ok"] += 1
                else:
                    issue(r, "stored mine layout differs from the seed")
                checker = lambda e, r=r, seed=seed: _mines_entry_issue(  # noqa: E731
                    e, derive_mine_positions(seed, r.client_seed or "", r.round_no, int((e.selection or {}).get("mine_count", 1) or 1)))
                ev = lambda e: 1 - int((e.selection or {}).get("house_edge_bp", 300)) / 10_000  # noqa: E731

            for e in entries:
                if e.status in ("REFUNDED", "CANCELLED"):
                    continue
                if e.status in ("PLACED", "CASHING_OUT"):
                    g["open_in_finished"] += 1
                    issue(r, f"bet still {e.status} in a finished round", e)
                    continue
                g["bets"] += 1
                problem = checker(e)
                if problem:
                    issue(r, problem, e)
                else:
                    g["settled_ok"] += 1
                paid = e.payout_amount if e.status == "WON" else 0
                g["wagered"] += e.bet_amount
                g["paid"] += paid
                g["expected_paid"] += e.bet_amount * ev(e)
                if e.user_id not in bot_ids:
                    g["real_wagered"] += e.bet_amount
                    g["real_paid"] += paid

        w = g["wagered"]
        out[game_id] = {
            **{k: v for k, v in g.items() if k not in ("outcomes", "expected_paid")},
            "outcomes": dict(sorted(g["outcomes"].items(), key=lambda kv: str(kv[0]))),
            "actual_hold_pct": round((w - g["paid"]) / w * 100, 2) if w else None,
            "expected_hold_pct": round((w - g["expected_paid"]) / w * 100, 2) if w else None,
            "real_hold_pct": round((g["real_wagered"] - g["real_paid"]) / g["real_wagered"] * 100, 2) if g["real_wagered"] else None,
        }
    return {"days": days, "max_rounds_per_game": max_rounds, "games": out}


# ---------------------------------------------------------------- 2. statistical fairness
def wingo_statistics(n: int) -> Dict[str, Any]:
    seed, client = secrets.token_hex(32), "backtest"
    payouts = payouts_from_config(None)
    counts = [0] * 10
    returned = defaultdict(float)
    for i in range(n):
        o = compute_outcome(seed, client, i)
        counts[o.number] += 1
        for t, v in WINGO_PICKS:
            returned[(t, v)] += payout_x100(t, v, o, payouts) / 100
    picks = []
    for t, v in WINGO_PICKS:
        mults = [payout_x100(t, v, WingoOutcome(k, number_colours(k), number_size(k)), payouts) / 100 for k in range(10)]
        mean = sum(mults) / 10
        se = math.sqrt(sum((x - mean) ** 2 for x in mults) / 10 / n)
        sim = returned[(t, v)] / n
        picks.append({"pick": f"{t.title()} {v.title() if not v.isdigit() else v}", "simulated_rtp_pct": round(sim * 100, 2),
                      "theoretical_rtp_pct": round(mean * 100, 2), "z": round((sim - mean) / se, 2) if se else 0.0})
    return {"rounds": n, "server_seed": seed, "client_seed": client, "number_counts": counts,
            "chi_square": chi_square(counts, [n / 10] * 10), "picks": picks}


AVIATOR_THRESHOLDS = [101, 120, 150, 200, 300, 500, 1000, 2000, 5000, 10000]


def aviator_statistics(n: int, edge: int) -> Dict[str, Any]:
    seed, client = secrets.token_hex(32), "backtest"
    crashes = sorted(compute_crash_point(seed, client, i, edge, CURRENT_CRASH_FORMULA) for i in range(n))
    import bisect

    survival = []
    for t in AVIATOR_THRESHOLDS:
        sim = (n - bisect.bisect_left(crashes, t)) / n
        theory = aviator_win_probability(t, edge, CURRENT_CRASH_FORMULA)
        se = math.sqrt(theory * (1 - theory) / n)
        survival.append({"multiplier": t / 100, "simulated_pct": round(sim * 100, 3),
                         "theoretical_pct": round(theory * 100, 3), "z": round((sim - theory) / se, 2) if se else 0.0})
    rtps = []
    for target in (150, 200, 500, 1000):
        wins = n - bisect.bisect_left(crashes, target)
        rtps.append({"cashout": target / 100, "simulated_rtp_pct": round(wins * target / 100 / n * 100, 2),
                     "theoretical_rtp_pct": round(aviator_rtp(edge, target, CURRENT_CRASH_FORMULA) * 100, 2)})
    return {
        "rounds": n, "server_seed": seed, "client_seed": client, "house_edge_bp": edge,
        "median_crash": crashes[n // 2] / 100,
        "instant_crash_pct": round(sum(1 for c in crashes if c == 100) / n * 100, 3),
        # 1.00x whenever the formula lands below 1.01x
        "instant_crash_theoretical_pct": round((1 - aviator_win_probability(101, edge, CURRENT_CRASH_FORMULA)) * 100, 3),
        "max_survival_gap_pp": round(max(abs(s["simulated_pct"] - s["theoretical_pct"]) for s in survival), 3),
        "survival": survival,
        "rtp": rtps,
    }


MINES_COMBOS = [(1, 5), (3, 3), (3, 8), (5, 5), (10, 2), (24, 1)]


def mines_statistics(n: int, edge: int, mine_count: int = 3) -> Dict[str, Any]:
    seed, client = secrets.token_hex(32), "backtest"
    tiles = [0] * 25
    layouts = [derive_mine_positions(seed, client, i, mine_count) for i in range(n)]
    for layout in layouts:
        for t in layout:
            tiles[t] += 1
    combos = []
    for m, k in MINES_COMBOS:
        picks = set(range(k))
        sample = layouts if m == mine_count else [derive_mine_positions(seed, client + f"-{m}", i, m) for i in range(n // 5)]
        wins = sum(1 for layout in sample if not (layout & picks))
        mult = compute_mines_multiplier_bp(k, m, edge) / 100
        p_win = comb(25 - m, k) / comb(25, k)
        se = math.sqrt(p_win * (1 - p_win) / len(sample))
        combos.append({
            "mines": m, "tiles_opened": k, "pays": mult,
            "win_chance_pct": round(p_win * 100, 3),
            "z": round((wins / len(sample) - p_win) / se, 2) if se else 0.0,
            "simulated_win_pct": round(wins / len(sample) * 100, 3),
            "theoretical_rtp_pct": round(mines_rtp(m, k, edge) * 100, 2),
            "simulated_rtp_pct": round(wins * mult / len(sample) * 100, 2),
            "sample": len(sample),
        })
    return {"layouts": n, "mine_count": mine_count, "server_seed": seed, "client_seed": client, "house_edge_bp": edge,
            "tile_counts": tiles, "chi_square": chi_square(tiles, [n * mine_count / 25] * 25), "combos": combos}


# ---------------------------------------------------------------- report
def _verdict(replay: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    games = replay["games"].values()
    rounds = sum(g["rounds"] for g in games)
    hash_bad = sum(g["rounds"] - g["hash_ok"] for g in games)
    out_bad = sum(g["rounds"] - g["outcome_ok"] for g in games)
    bets = sum(g["bets"] for g in games)
    settle_bad = sum(g["bets"] - g["settled_ok"] for g in games)
    open_bad = sum(g["open_in_finished"] for g in games)
    wingo, avi, mines = stats["wingo"], stats["aviator"], stats["mines"]
    # z-scores: how many standard errors each simulated figure is from theory (|z| < 4.5 is normal noise)
    pick_z = max(abs(p["z"]) for p in wingo["picks"])
    surv_z = max(abs(s["z"]) for s in avi["survival"])
    mines_z = max(abs(c["z"]) for c in mines["combos"])
    checks = [
        _check("Seed commitments", hash_bad == 0, f"{rounds - hash_bad:,} of {rounds:,} revealed seeds hash to the value published before betting"),
        _check("Outcomes recomputed", out_bad == 0, f"{rounds - out_bad:,} of {rounds:,} stored results match the result recomputed from the seed"),
        _check("Bet settlement", settle_bad == 0, f"{bets - settle_bad:,} of {bets:,} settled bets were paid exactly by the rules"),
        _check("No stuck bets", open_bad == 0, f"{open_bad} bets still open inside finished rounds", warn_only=True),
        _check("WinGo numbers uniform", wingo["chi_square"]["p_value"] >= 0.001,
               f"chi-square p = {wingo['chi_square']['p_value']} over {wingo['rounds']:,} draws (above 0.001 = no detectable bias)", warn_only=True),
        _check("WinGo returns match odds", pick_z < 4.5, f"every bet type within {pick_z:.1f} standard errors of its theoretical return", warn_only=True),
        _check("Aviator crash distribution", surv_z < 4.5,
               f"survival curve within {surv_z:.1f} standard errors of the formula (largest gap {avi['max_survival_gap_pp']} pp) over {avi['rounds']:,} flights", warn_only=True),
        _check("Mines win chances", mines_z < 4.5, f"every mines/tiles combination within {mines_z:.1f} standard errors of the exact odds", warn_only=True),
        _check("Mines layouts uniform", mines["chi_square"]["p_value"] >= 0.001,
               f"chi-square p = {mines['chi_square']['p_value']} over {mines['layouts']:,} boards", warn_only=True),
    ]
    status = "fail" if any(c["status"] == "fail" for c in checks) else "warn" if any(c["status"] == "warn" for c in checks) else "pass"
    return {"status": status, "checks": checks, "rounds_replayed": rounds, "bets_replayed": bets}


async def _edge(db: AsyncSession, game_id: str) -> int:
    setting = (await db.execute(select(GameSetting).where(GameSetting.game_id == game_id))).scalar_one_or_none()
    return int(setting.house_edge_percent) if setting and setting.house_edge_percent is not None else 300


async def run_backtest(db: AsyncSession, days: int = 30, max_rounds: int = 3000, sim_scale: int = 1,
                       actor: Optional[str] = None) -> Dict[str, Any]:
    import asyncio

    started = time.perf_counter()
    replay = await historical_replay(db, days, max_rounds)
    avi_edge, mines_edge = await _edge(db, "aviator"), await _edge(db, "mines")
    scale = max(1, min(sim_scale, 5))

    def simulate() -> Dict[str, Any]:
        return {
            "wingo": wingo_statistics(100_000 * scale),
            "aviator": aviator_statistics(200_000 * scale, avi_edge),
            "mines": mines_statistics(20_000 * scale, mines_edge),
        }

    stats = await asyncio.to_thread(simulate)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_by": actor,
        "duration_s": round(time.perf_counter() - started, 1),
        "verdict": _verdict(replay, stats),
        "replay": replay,
        "statistics": stats,
    }
    await _store(db, report)
    return report


async def _store(db: AsyncSession, report: Dict[str, Any]) -> None:
    latest = await db.get(SystemSetting, LATEST_KEY)
    payload = json.dumps(report)
    if latest is None:
        db.add(SystemSetting(key=LATEST_KEY, value=payload, description="Latest algorithm backtest report"))
    else:
        latest.value = payload
    history_row = await db.get(SystemSetting, HISTORY_KEY)
    history = json.loads(history_row.value) if history_row else []
    games = report["replay"]["games"].values()
    wagered = sum(g["wagered"] for g in games)
    paid = sum(g["paid"] for g in games)
    history.insert(0, {
        "generated_at": report["generated_at"], "run_by": report["run_by"], "status": report["verdict"]["status"],
        "rounds": report["verdict"]["rounds_replayed"], "bets": report["verdict"]["bets_replayed"],
        "hold_pct": round((wagered - paid) / wagered * 100, 2) if wagered else None,
        "failed_checks": [c["name"] for c in report["verdict"]["checks"] if c["status"] != "pass"],
    })
    if history_row is None:
        db.add(SystemSetting(key=HISTORY_KEY, value=json.dumps(history[:30]), description="Earlier backtest runs"))
    else:
        history_row.value = json.dumps(history[:30])


async def latest_report(db: AsyncSession) -> Dict[str, Any]:
    latest = await db.get(SystemSetting, LATEST_KEY)
    history = await db.get(SystemSetting, HISTORY_KEY)
    return {
        "report": json.loads(latest.value) if latest else None,
        "history": json.loads(history.value) if history else [],
    }


__all__ = ["run_backtest", "latest_report", "chi_square", "historical_replay"]
