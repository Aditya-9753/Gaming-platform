"""Fair Hold Analyzer: what the house actually kept vs what the published odds imply.

Nothing here touches a live round. ``analysis`` reads settled bets and
compares the realised hold with the hold the payout table / house edge
predicts. ``simulate`` replays the *real* provably-fair functions (the same
HMAC-SHA256 code the engines use) with a fresh random server seed, so an
admin can see what changing a payout or edge setting would do before changing
it for everyone. The server seed of each simulation is returned so the run
can be reproduced.
"""

from __future__ import annotations

import math
import secrets
from datetime import datetime, timedelta, timezone
from math import comb
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Float, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.games.aviator.rules import CRASH_FORMULA_V1, CURRENT_CRASH_FORMULA, compute_crash_point
from app.games.mines.rules import compute_mines_multiplier_bp, derive_mine_positions
from app.games.simulated_players import BOT_NAMES
from app.games.wingo.rules import (
    BET_COLOR, BET_NUMBER, BET_SIZE, MODES, compute_outcome, number_colours, number_size,
    payout_x100, payouts_from_config, WingoOutcome,
)
from app.models.game import Game, GameEntry, GameRound, GameSetting
from app.models.role import Role
from app.models.user import User

MAX_SIM_ROUNDS = 100_000
SETTLED = ("WON", "LOST")
WINGO_PICKS: List[Tuple[str, str]] = (
    [(BET_COLOR, c) for c in ("GREEN", "RED", "VIOLET")]
    + [(BET_SIZE, s) for s in ("BIG", "SMALL")]
    + [(BET_NUMBER, str(n)) for n in range(10)]
)


# ---------------------------------------------------------------- expected values
def wingo_ev(bet_type: str, value: str, payouts: Dict[str, int]) -> Optional[float]:
    """Expected return per unit stake for one WinGo pick (each number 0-9 has p = 1/10)."""
    try:
        total = sum(payout_x100(bet_type, value, WingoOutcome(n, number_colours(n), number_size(n)), payouts) for n in range(10))
    except (KeyError, ValueError):
        return None
    return total / 100 / 10


def aviator_win_probability(cashout_x100: int, house_edge_bp: int, formula: int = CURRENT_CRASH_FORMULA) -> float:
    """P(crash >= cashout) for the engine's formula (v1 adds the legacy instant-crash rule)."""
    if cashout_x100 <= 100:
        return 1.0
    if cashout_x100 > 10_000:
        return 0.0
    p_not_instant = 1.0
    if formula == CRASH_FORMULA_V1 and house_edge_bp:
        p_not_instant = 1 - 1 / (10_000 // house_edge_bp)
    return p_not_instant * min(1.0, (10_000 - house_edge_bp) / 10_000 * 100 / cashout_x100)


def aviator_rtp(house_edge_bp: int, cashout_x100: int = 200, formula: int = CURRENT_CRASH_FORMULA) -> float:
    return aviator_win_probability(cashout_x100, house_edge_bp, formula) * cashout_x100 / 100


def mines_rtp(mine_count: int, reveal: int, house_edge_bp: int) -> float:
    p_win = comb(25 - mine_count, reveal) / comb(25, reveal)
    return p_win * compute_mines_multiplier_bp(reveal, mine_count, house_edge_bp) / 100


# ---------------------------------------------------------------- analysis
async def _settings(db: AsyncSession) -> Dict[str, GameSetting]:
    return {s.game_id: s for s in (await db.execute(select(GameSetting))).scalars().all()}


def _edge_bp(setting: Optional[GameSetting], default: int = 300) -> int:
    return int(setting.house_edge_percent) if setting and setting.house_edge_percent is not None else default


async def analysis(db: AsyncSession, days: int = 7, include_bots: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    settings = await _settings(db)
    names = {g.id: g.name for g in (await db.execute(select(Game))).scalars().all()}

    player = [Role.name == "USER"]
    if not include_bots:
        player.append(User.username.notin_(BOT_NAMES))
    won = GameEntry.status == "WON"
    ratio = case((won, cast(GameEntry.payout_amount, Float) / GameEntry.bet_amount), else_=0.0)
    pick_type = GameEntry.selection["type"].as_string()
    pick_value = GameEntry.selection["value"].as_string()
    rows = (await db.execute(
        select(
            GameRound.game_id, pick_type, pick_value,
            func.count(GameEntry.id),
            func.coalesce(func.sum(GameEntry.bet_amount), 0),
            func.coalesce(func.sum(case((won, GameEntry.payout_amount), else_=0)), 0),
            func.coalesce(func.sum(ratio), 0.0),
            func.coalesce(func.sum(ratio * ratio), 0.0),
            func.avg(cast(GameEntry.selection["house_edge_bp"].as_string(), Float)),
        )
        .select_from(GameEntry)
        .join(GameRound, GameRound.id == GameEntry.round_id)
        .join(User, User.id == GameEntry.user_id).join(Role, Role.id == User.role_id)
        .where(and_(*player), GameEntry.status.in_(SETTLED), GameEntry.created_at >= since, GameEntry.bet_amount > 0)
        .group_by(GameRound.game_id, pick_type, pick_value)
    )).all()

    games: Dict[str, Dict[str, Any]] = {}
    for game_id, ptype, pvalue, n, wagered, paid, s_r, s_r2, mines_edge in rows:
        g = games.setdefault(game_id, {"bets": 0, "wagered": 0, "paid": 0, "s_r": 0.0, "s_r2": 0.0,
                                       "expected_paid": 0.0, "expected_known": True, "basis": ""})
        g["bets"] += int(n)
        g["wagered"] += int(wagered)
        g["paid"] += int(paid)
        g["s_r"] += float(s_r)
        g["s_r2"] += float(s_r2)
        if game_id in MODES:
            payouts = payouts_from_config((settings.get(game_id).config if settings.get(game_id) else None))
            ev = wingo_ev(str(ptype or ""), str(pvalue or ""), payouts)
            if ev is None:
                g["expected_known"] = False
            else:
                g["expected_paid"] += int(wagered) * ev
            g["basis"] = "payout table, every number 1 in 10"
        elif game_id == "aviator":
            edge = _edge_bp(settings.get("aviator"))
            # Any cash-out target returns the same share in the long run; 2.00x is used as reference
            g["expected_paid"] += int(wagered) * aviator_rtp(edge, 200)
            g["basis"] = f"house edge {edge / 100:.2f}% (applied once)"
        elif game_id == "mines":
            edge = int(mines_edge) if mines_edge is not None else _edge_bp(settings.get("mines"))
            g["expected_paid"] += int(wagered) * (1 - edge / 10_000)
            g["basis"] = f"house edge {edge / 100:.2f}% on every multiplier"
        else:
            g["expected_known"] = False
            g["basis"] = "no fixed edge model"

    out = []
    total = {"bets": 0, "wagered": 0, "paid": 0, "expected_paid": 0.0}
    for game_id, g in sorted(games.items()):
        n, w, p = g["bets"], g["wagered"], g["paid"]
        hold = (w - p) / w * 100 if w else 0.0
        expected = (w - g["expected_paid"]) / w * 100 if (w and g["expected_known"]) else None
        mean = g["s_r"] / n if n else 0.0
        sd = math.sqrt(max(0.0, g["s_r2"] / n - mean * mean)) if n else 0.0
        band = 1.96 * sd / math.sqrt(n) * 100 if n else None
        out.append({
            "game_id": game_id,
            "name": names.get(game_id, game_id),
            "bets": n,
            "wagered": w,
            "paid": p,
            "house": w - p,
            "actual_hold_pct": round(hold, 2),
            "expected_hold_pct": round(expected, 2) if expected is not None else None,
            "band_pct": round(band, 2) if band is not None else None,
            "within_band": (abs(hold - expected) <= band) if (expected is not None and band is not None) else None,
            "basis": g["basis"],
        })
        total["bets"] += n
        total["wagered"] += w
        total["paid"] += p
        if g["expected_known"]:
            total["expected_paid"] += g["expected_paid"]
    return {
        "generated_at": now.isoformat(),
        "days": days,
        "include_bots": include_bots,
        "games": out,
        "total": {
            "bets": total["bets"], "wagered": total["wagered"], "paid": total["paid"],
            "house": total["wagered"] - total["paid"],
            "actual_hold_pct": round((total["wagered"] - total["paid"]) / total["wagered"] * 100, 2) if total["wagered"] else 0.0,
        },
        "note": "Short-term hold swings around the expected value; the band is the approximate 95% range for this many bets.",
    }


# ---------------------------------------------------------------- simulation
async def wingo_bet_mix(db: AsyncSession, days: int = 30) -> List[Tuple[str, str, float]]:
    """Share of stake per WinGo pick over recent real bets (uniform if there are none)."""
    pick_type = GameEntry.selection["type"].as_string()
    pick_value = GameEntry.selection["value"].as_string()
    rows = (await db.execute(
        select(pick_type, pick_value, func.sum(GameEntry.bet_amount))
        .join(GameRound, GameRound.id == GameEntry.round_id)
        .where(GameRound.game_id.in_(list(MODES)), GameEntry.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
        .group_by(pick_type, pick_value)
    )).all()
    valid = {(t, v) for t, v in WINGO_PICKS}
    mix = [(str(t), str(v), float(a)) for t, v, a in rows if (str(t), str(v)) in valid and a]
    total = sum(a for *_x, a in mix)
    if not total:
        return [(t, v, 1 / len(WINGO_PICKS)) for t, v in WINGO_PICKS]
    return [(t, v, a / total) for t, v, a in mix]


def _series_point(i: int, wagered: float, paid: float) -> Dict[str, Any]:
    return {"round": i, "hold_pct": round((wagered - paid) / wagered * 100, 3) if wagered else 0.0}


def run_simulation(params: Dict[str, Any], mix: Optional[List[Tuple[str, str, float]]] = None) -> Dict[str, Any]:
    """CPU-bound; call through a thread. Uses the engines' own provably-fair functions."""
    game = params["game"]
    rounds = max(100, min(int(params.get("rounds", 10_000)), MAX_SIM_ROUNDS))
    server_seed = secrets.token_hex(32)
    client_seed = "hold-simulation"
    step = max(1, rounds // 60)
    series: List[Dict[str, Any]] = []
    wagered = paid = 0.0
    extra: Dict[str, Any] = {}

    if game == "wingo":
        payouts = payouts_from_config({"payouts": params.get("payouts") or {}})
        mix = mix or [(t, v, 1 / len(WINGO_PICKS)) for t, v in WINGO_PICKS]
        expected_rtp = sum(share * (wingo_ev(t, v, payouts) or 0) for t, v, share in mix)
        counts = [0] * 10
        for i in range(rounds):
            outcome = compute_outcome(server_seed, client_seed, i)
            counts[outcome.number] += 1
            wagered += 1
            paid += sum(share * payout_x100(t, v, outcome, payouts) / 100 for t, v, share in mix)
            if (i + 1) % step == 0:
                series.append(_series_point(i + 1, wagered, paid))
        extra = {
            "number_counts": counts,
            "payouts": {k: v / 100 for k, v in payouts.items()},
            "bet_mix": [{"type": t, "value": v, "share": round(s, 4)} for t, v, s in mix],
        }
    elif game == "aviator":
        edge = int(params.get("house_edge_bp", 300))
        cashout = int(round(float(params.get("cashout_at", 2.0)) * 100))
        if not 0 <= edge < 10_000 or not 101 <= cashout <= 10_000:
            raise ValueError("Edge must be 0-99.99% and cash-out 1.01x-100x")
        expected_rtp = aviator_rtp(edge, cashout)
        wins = 0
        for i in range(rounds):
            crash = compute_crash_point(server_seed, client_seed, i, edge, CURRENT_CRASH_FORMULA)
            wagered += 1
            if crash >= cashout:
                wins += 1
                paid += cashout / 100
            if (i + 1) % step == 0:
                series.append(_series_point(i + 1, wagered, paid))
        extra = {"cashout_at": cashout / 100, "house_edge_bp": edge, "win_rate_pct": round(wins / rounds * 100, 2)}
    elif game == "mines":
        edge = int(params.get("house_edge_bp", 300))
        mine_count = int(params.get("mine_count", 3))
        reveal = int(params.get("reveal", 3))
        if not 1 <= mine_count <= 24 or not 1 <= reveal <= 25 - mine_count or not 0 <= edge < 10_000:
            raise ValueError("Check mine count, tiles opened and edge")
        multiplier = compute_mines_multiplier_bp(reveal, mine_count, edge) / 100
        expected_rtp = mines_rtp(mine_count, reveal, edge)
        picks = set(range(reveal))  # any fixed set of tiles has the same odds
        wins = 0
        for i in range(rounds):
            mines = derive_mine_positions(server_seed, client_seed, i, mine_count)
            wagered += 1
            if not (mines & picks):
                wins += 1
                paid += multiplier
            if (i + 1) % step == 0:
                series.append(_series_point(i + 1, wagered, paid))
        extra = {"multiplier": multiplier, "mine_count": mine_count, "reveal": reveal, "house_edge_bp": edge,
                 "win_rate_pct": round(wins / rounds * 100, 2)}
    else:
        raise ValueError("Game must be wingo, aviator or mines")

    return {
        "game": game,
        "rounds": rounds,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "simulated_hold_pct": round((wagered - paid) / wagered * 100, 3),
        "expected_hold_pct": round((1 - expected_rtp) * 100, 3),
        "series": series,
        **extra,
    }


__all__ = ["analysis", "run_simulation", "wingo_bet_mix", "wingo_ev", "aviator_rtp", "mines_rtp"]
