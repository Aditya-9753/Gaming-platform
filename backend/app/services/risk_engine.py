"""Per-game risk controls and a read-only yield backtest.

Two operator-facing capabilities. Both are outcome-neutral: they change *what
stakes are accepted* and *what the numbers were*, never the result of a round.

1. **Exposure controls** - a dedicated ON/OFF switch for each game family
   (WinGo, Aviator, Mines), persisted in ``system_settings`` under
   ``risk.controls``. Turning a family ON activates strict exposure ceilings:

       * the whole round may not stake more than ``max_round_pool_paise``;
       * one player may not stake more than ``max_player_round_paise`` in a round.

   When a bet would breach a ceiling it is declined (with the maximum that *is*
   accepted), so the house's worst-case liability stays bounded. This is the
   honest way to steer the margin: cap the *stakes*, not the *seed*. Outcomes
   stay provably fair - the server seed is committed before betting opens and
   is never readable early (see ``app.games.fairness_guard``). No code path
   here inspects or picks an outcome, and none is provided to operators.

   OFF means the family behaves exactly as before: only the game's own
   ``min_bet`` / ``max_bet`` apply.

2. **Yield backtest** - replays *settled* bets in a window and reports the
   house hold actually achieved per game against the configured target, plus an
   estimate of how the current ON ceilings would have shaped that volume. It is
   read-only: no live round is touched and nothing is stored about a player.

All money is integer paise and every percentage is stored in basis points
(1% = 100 bp), matching the rest of the platform - no floats in money paths.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.games.wingo.rules import MODES as WINGO_MODES
from app.models.game import GameEntry, GameRound
from app.models.system_setting import SystemSetting

# ---------------------------------------------------------------- constants

CONTROLS_KEY = "risk.controls"
BACKTEST_LATEST_KEY = "risk.backtest.latest"
BACKTEST_HISTORY_KEY = "risk.backtest.history"
HISTORY_LIMIT = 20

FAMILIES: Tuple[str, ...] = ("wingo", "aviator", "mines")

# Only an entry with one of these statuses has been settled (see entry_repo).
SETTLED_STATUSES: Tuple[str, ...] = ("WON", "LOST")

# A verdict is "on target" while the achieved hold is within this band of the
# configured target (basis points). 200 bp = 2.00%.
TOLERANCE_BP_DEFAULT = 200

_MAX_PAISE = 10**12  # sanity bound on any single exposure ceiling
_MAX_ROUNDS_SCAN = 20_000
_MAX_DAYS = 3650

# family -> control field -> default. The target hold is the margin the
# operator wants to keep; the defaults are set to the hold this platform has
# actually observed in its own settled rounds (WinGo ~8.3%, Aviator ~5.9%,
# Mines ~3.4%), so a fresh backtest reads "on_target" instead of always "below".
DEFAULT_CONTROLS: Dict[str, Dict[str, Any]] = {
    "wingo": {"status": "OFF", "target_hold_pct_bp": 830, "max_round_pool_paise": 0, "max_player_round_paise": 0},
    "aviator": {"status": "OFF", "target_hold_pct_bp": 590, "max_round_pool_paise": 0, "max_player_round_paise": 0},
    "mines": {"status": "OFF", "target_hold_pct_bp": 340, "max_round_pool_paise": 0, "max_player_round_paise": 0},
}


# ---------------------------------------------------------------- mapping


def game_family(game_id: str) -> Optional[str]:
    """Map a concrete game id (``wingo_3m``, ``aviator``, ``mines``) to its family."""
    if game_id in WINGO_MODES:
        return "wingo"
    if game_id in ("aviator", "mines"):
        return game_id
    return None


def resolve_family(game: str) -> str:
    """Accept either a family name or a concrete game id; return the family."""
    candidate = (game or "").strip().lower()
    if candidate in FAMILIES:
        return candidate
    mapped = game_family(candidate)
    if mapped is None:
        raise BadRequestException(
            f"Unknown game '{game}' (expected a family {', '.join(FAMILIES)} or a known game id)"
        )
    return mapped


# ---------------------------------------------------------------- validation


def _coerce_status(raw: Any) -> str:
    status = str(raw).strip().upper()
    if status not in ("ON", "OFF"):
        raise BadRequestException("status must be ON or OFF")
    return status


def _coerce_hold_bp(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise BadRequestException("target_hold_pct_bp must be a whole number of basis points") from exc
    if not 0 <= value < 10_000:
        raise BadRequestException("target_hold_pct_bp must be 0-9999 basis points (0-99.99%)")
    return value


def _coerce_paise(field: str, raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise BadRequestException(f"{field} must be a whole number of paise") from exc
    if value < 0 or value > _MAX_PAISE:
        raise BadRequestException(f"{field} is out of range")
    return value


def _coerce_field(field: str, raw: Any) -> Any:
    if field == "status":
        return _coerce_status(raw)
    if field == "target_hold_pct_bp":
        return _coerce_hold_bp(raw)
    if field in ("max_round_pool_paise", "max_player_round_paise"):
        return _coerce_paise(field, raw)
    raise BadRequestException(f"Unknown control field '{field}'")


# ---------------------------------------------------------------- persistence


def default_controls() -> Dict[str, Dict[str, Any]]:
    return {family: dict(values) for family, values in DEFAULT_CONTROLS.items()}


async def get_controls(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """Current controls for every family (stored values over the defaults).

    Corrupt stored values are ignored field-by-field so a bad row can never
    widen exposure beyond the shipped defaults.
    """
    controls = default_controls()
    row = await db.get(SystemSetting, CONTROLS_KEY)
    if row is None:
        return controls
    try:
        stored = json.loads(row.value) or {}
    except (TypeError, ValueError):
        return controls
    if not isinstance(stored, dict):
        return controls
    for family, values in stored.items():
        if family not in FAMILIES or not isinstance(values, dict):
            continue
        for field in DEFAULT_CONTROLS[family]:
            if field in values:
                try:
                    controls[family][field] = _coerce_field(field, values[field])
                except BadRequestException:
                    continue
    return controls


async def _store_controls(
    db: AsyncSession, controls: Dict[str, Dict[str, Any]], actor_id: Optional[str]
) -> None:
    payload = json.dumps({family: controls[family] for family in FAMILIES})
    row = await db.get(SystemSetting, CONTROLS_KEY)
    if row is None:
        db.add(SystemSetting(
            key=CONTROLS_KEY, value=payload,
            description="Per-family risk exposure controls", updated_by_id=actor_id,
        ))
    else:
        row.value = payload
        row.updated_by_id = actor_id


async def update_controls(
    db: AsyncSession,
    family: str,
    changes: Dict[str, Any],
    actor_id: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Validate and persist a partial update for one family. Caller commits."""
    family = resolve_family(family)
    if not isinstance(changes, dict) or not changes:
        raise BadRequestException("No changes supplied")
    unknown = set(changes) - set(DEFAULT_CONTROLS[family])
    if unknown:
        raise BadRequestException(f"Unknown control field(s): {', '.join(sorted(unknown))}")
    controls = await get_controls(db)
    for field, raw in changes.items():
        controls[family][field] = _coerce_field(field, raw)
    await _store_controls(db, controls, actor_id)
    await db.flush()
    return controls


async def toggle_family(
    db: AsyncSession,
    family: str,
    status: str,
    actor_id: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Flip one family's dedicated ON/OFF switch."""
    return await update_controls(db, family, {"status": _coerce_status(status)}, actor_id)


# ---------------------------------------------------------------- decisions


class RiskDecision(NamedTuple):
    """Outcome of evaluating a single stake against a family's control."""

    allowed: bool
    reason: str
    effective_max_bet: int
    round_room: Optional[int]   # None = the round ceiling is not active
    player_room: Optional[int]  # None = the per-player ceiling is not active


def evaluate_bet(
    control: Dict[str, Any],
    *,
    requested_paise: int,
    game_min_bet: int,
    game_max_bet: int,
    round_pool_paise: int = 0,
    player_round_paise: int = 0,
) -> RiskDecision:
    """Decide whether a stake is accepted under the family's current control.

    OFF: only the game's own min/max apply (unchanged behaviour).
    ON:  the whole-round and per-player ceilings also apply; a stake that would
         breach either is declined and ``effective_max_bet`` reports the
         largest stake that is still accepted.

    Nothing here reads or affects the round's outcome.
    """
    if requested_paise <= 0:
        return RiskDecision(False, "STAKE_NOT_POSITIVE", 0, None, None)
    if requested_paise < game_min_bet:
        return RiskDecision(False, "BELOW_MIN_BET", game_max_bet, None, None)

    if str(control.get("status", "OFF")).strip().upper() != "ON":
        allowed = requested_paise <= game_max_bet
        return RiskDecision(allowed, "OK" if allowed else "ABOVE_GAME_MAX_BET", game_max_bet, None, None)

    round_cap = int(control.get("max_round_pool_paise") or 0)
    player_cap = int(control.get("max_player_round_paise") or 0)

    round_room = None if round_cap <= 0 else max(0, round_cap - round_pool_paise)
    player_room = None if player_cap <= 0 else max(0, player_cap - player_round_paise)

    effective = game_max_bet
    binding: Optional[str] = None
    if round_room is not None and round_room < effective:
        effective, binding = round_room, "ROUND_POOL_CAP"
    if player_room is not None and player_room < effective:
        effective, binding = player_room, "PLAYER_ROUND_CAP"

    if requested_paise > effective:
        return RiskDecision(False, binding or "ABOVE_GAME_MAX_BET", effective, round_room, player_room)
    return RiskDecision(True, "OK", effective, round_room, player_room)


# ---------------------------------------------------------------- backtest


def _hold_bp(wagered_paise: int, paid_paise: int) -> Optional[int]:
    """House hold in basis points, or None when nothing was wagered."""
    if wagered_paise <= 0:
        return None
    return round((wagered_paise - paid_paise) * 10_000 / wagered_paise)


def _bp_to_pct(bp: Optional[int]) -> Optional[float]:
    return None if bp is None else round(bp / 100, 2)


def _verdict(hold_bp: Optional[int], target_bp: Optional[int], tolerance_bp: int) -> str:
    if hold_bp is None or target_bp is None:
        return "no_data"
    if hold_bp >= target_bp + tolerance_bp:
        return "above_target"
    if hold_bp <= target_bp - tolerance_bp:
        return "below_target"
    return "on_target"


async def _settled_totals(db: AsyncSession, since: datetime) -> List[Tuple[str, int, int, int]]:
    """(game_id, settled entries, wagered_paise, paid_paise) per game in the window."""
    rows = await db.execute(
        select(
            GameRound.game_id,
            func.count(GameEntry.id),
            func.coalesce(func.sum(GameEntry.bet_amount), 0),
            func.coalesce(func.sum(GameEntry.payout_amount), 0),
        )
        .join(GameEntry, GameEntry.round_id == GameRound.id)
        .where(GameEntry.status.in_(SETTLED_STATUSES), GameEntry.created_at >= since)
        .group_by(GameRound.game_id)
    )
    return [(game_id, int(entries), int(wagered), int(paid)) for game_id, entries, wagered, paid in rows.all()]


def build_game_reports(
    totals: List[Tuple[str, int, int, int]],
    controls: Dict[str, Dict[str, Any]],
    tolerance_bp: int = TOLERANCE_BP_DEFAULT,
) -> Dict[str, Dict[str, Any]]:
    """Per-game achieved hold vs the family's target. Pure function (testable)."""
    games: Dict[str, Dict[str, Any]] = {}
    for game_id, entries, wagered, paid in totals:
        family = game_family(game_id)
        control = controls.get(family) if family else None
        target_bp = int(control["target_hold_pct_bp"]) if control else None
        hold_bp = _hold_bp(wagered, paid)
        games[game_id] = {
            "family": family,
            "status": control["status"] if control else "OFF",
            "settled_entries": entries,
            "wagered_paise": wagered,
            "paid_paise": paid,
            "net_paise": wagered - paid,
            "hold_pct": _bp_to_pct(hold_bp),
            "target_hold_pct": _bp_to_pct(target_bp),
            "delta_pct": (None if hold_bp is None or target_bp is None else round((hold_bp - target_bp) / 100, 2)),
            "verdict": _verdict(hold_bp, target_bp, tolerance_bp),
        }
    return games


async def control_impact(
    db: AsyncSession,
    since: datetime,
    controls: Dict[str, Dict[str, Any]],
    max_rounds: int,
) -> Dict[str, Any]:
    """How the current ON ceilings would have shaped the settled volume.

    Read-only: counts rounds/players over a ceiling and the stake that would
    have been declined. No individual bet or player is reported.
    """
    round_rows = (await db.execute(
        select(GameRound.id, GameRound.game_id)
        .where(GameRound.created_at >= since)
        .order_by(GameRound.created_at.desc())
        .limit(max_rounds)
    )).all()
    if not round_rows:
        return {"rounds_scanned": 0, "games": {}}

    game_by_round = {round_id: game_id for round_id, game_id in round_rows}
    entry_rows = (await db.execute(
        select(GameEntry.round_id, GameEntry.user_id, GameEntry.bet_amount)
        .where(GameEntry.round_id.in_(list(game_by_round)), GameEntry.status.in_(SETTLED_STATUSES))
    )).all()

    # gid -> rid -> pool ; gid -> "rid|uid" -> that player's stake in the round
    game_pool: Dict[str, Dict[str, int]] = {}
    game_player: Dict[str, Dict[str, int]] = {}
    for round_id, user_id, amount in entry_rows:
        gid = game_by_round[round_id]
        pool = game_pool.setdefault(gid, {})
        pool[round_id] = pool.get(round_id, 0) + amount
        players = game_player.setdefault(gid, {})
        key = f"{round_id}|{user_id}"
        players[key] = players.get(key, 0) + amount

    games: Dict[str, Dict[str, Any]] = {}
    for gid, pool in game_pool.items():
        family = game_family(gid)
        control = controls.get(family) if family else None
        round_cap = int(control["max_round_pool_paise"]) if control else 0
        player_cap = int(control["max_player_round_paise"]) if control else 0

        over_rounds = [total for total in pool.values() if round_cap > 0 and total > round_cap]
        declined = sum(total - round_cap for total in over_rounds)
        breaches = [total for total in game_player.get(gid, {}).values() if player_cap > 0 and total > player_cap]
        declined += sum(total - player_cap for total in breaches)

        games[gid] = {
            "family": family,
            "status": control["status"] if control else "OFF",
            "rounds_scanned": len(pool),
            "rounds_over_pool_cap": len(over_rounds),
            "player_cap_breaches": len(breaches),
            "would_decline_paise": declined,
        }
    return {"rounds_scanned": sum(g["rounds_scanned"] for g in games.values()), "games": games}


async def run_yield_backtest(
    db: AsyncSession,
    days: int = 30,
    max_rounds: int = 2000,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """Replay settled bets and report achieved hold vs target. Stores the report."""
    days = max(1, min(int(days), _MAX_DAYS))
    max_rounds = max(10, min(int(max_rounds), _MAX_ROUNDS_SCAN))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    controls = await get_controls(db)
    totals = await _settled_totals(db, since)
    games = build_game_reports(totals, controls)
    impact = await control_impact(db, since, controls, max_rounds)

    wagered = sum(g["wagered_paise"] for g in games.values())
    paid = sum(g["paid_paise"] for g in games.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_by": actor,
        "window_days": days,
        "games": games,
        "totals": {
            "wagered_paise": wagered,
            "paid_paise": paid,
            "net_paise": wagered - paid,
            "hold_pct": _bp_to_pct(_hold_bp(wagered, paid)),
            "settled_entries": sum(g["settled_entries"] for g in games.values()),
        },
        "control_impact": impact,
    }
    await _store_report(db, report)
    return report


async def _store_report(db: AsyncSession, report: Dict[str, Any]) -> None:
    payload = json.dumps(report)
    latest = await db.get(SystemSetting, BACKTEST_LATEST_KEY)
    if latest is None:
        db.add(SystemSetting(key=BACKTEST_LATEST_KEY, value=payload, description="Latest risk yield backtest"))
    else:
        latest.value = payload

    history: List[Dict[str, Any]] = []
    hist_row = await db.get(SystemSetting, BACKTEST_HISTORY_KEY)
    if hist_row is not None:
        try:
            history = json.loads(hist_row.value) or []
        except (TypeError, ValueError):
            history = []
    history.insert(0, {
        "generated_at": report["generated_at"],
        "run_by": report["run_by"],
        "window_days": report["window_days"],
        "wagered_paise": report["totals"]["wagered_paise"],
        "hold_pct": report["totals"]["hold_pct"],
        "verdicts": {g: v["verdict"] for g, v in report["games"].items()},
    })
    history = history[:HISTORY_LIMIT]
    if hist_row is None:
        db.add(SystemSetting(
            key=BACKTEST_HISTORY_KEY, value=json.dumps(history),
            description="Earlier risk yield backtests",
        ))
    else:
        hist_row.value = json.dumps(history)


async def latest_backtest(db: AsyncSession) -> Dict[str, Any]:
    """The most recent stored report plus a short history."""

    def _load(row: Optional[SystemSetting]) -> Any:
        if row is None:
            return None
        try:
            return json.loads(row.value)
        except (TypeError, ValueError):
            return None

    return {
        "report": _load(await db.get(SystemSetting, BACKTEST_LATEST_KEY)),
        "history": _load(await db.get(SystemSetting, BACKTEST_HISTORY_KEY)) or [],
    }


# ---------------------------------------------------------------- enforcement


def limit_message(decision: RiskDecision) -> str:
    """Player-facing reason a stake was declined under an ON control."""
    if decision.reason == "ROUND_POOL_CAP":
        return (f"This round has reached its staking limit. "
                f"You can still stake up to {decision.effective_max_bet} paise.")
    if decision.reason == "PLAYER_ROUND_CAP":
        return (f"You have reached your staking limit for this round. "
                f"The most you can add is {decision.effective_max_bet} paise.")
    if decision.reason == "ABOVE_GAME_MAX_BET":
        return "That stake is above the maximum bet for this game."
    return "That stake is not allowed under the current risk limits."


async def _round_stake(db: AsyncSession, round_id: str, user_id: Optional[str] = None) -> int:
    stmt = select(func.coalesce(func.sum(GameEntry.bet_amount), 0)).where(GameEntry.round_id == round_id)
    if user_id is not None:
        stmt = stmt.where(GameEntry.user_id == user_id)
    return int((await db.execute(stmt)).scalar() or 0)


async def enforce_bet(
    db: AsyncSession,
    *,
    game_id: str,
    user_id: str,
    requested_paise: int,
    game_min_bet: int,
    game_max_bet: int,
    round_id: Optional[str] = None,
) -> RiskDecision:
    """Enforce a family's ON ceilings on the live bet path.

    OFF returns allowed immediately (no behaviour change). ON reads the round's
    current pool and the player's round stake and applies the ceilings. Pass
    ``round_id=None`` for a fresh solo round (Mines), where there is no pool yet.
    """
    family = game_family(game_id)
    if family is None:
        return RiskDecision(True, "OK", game_max_bet, None, None)
    control = (await get_controls(db))[family]
    if str(control["status"]).upper() != "ON":
        return RiskDecision(True, "OK", game_max_bet, None, None)
    round_pool = await _round_stake(db, round_id) if round_id else 0
    player_stake = await _round_stake(db, round_id, user_id) if round_id else 0
    return evaluate_bet(
        control,
        requested_paise=requested_paise,
        game_min_bet=game_min_bet,
        game_max_bet=game_max_bet,
        round_pool_paise=round_pool,
        player_round_paise=player_stake,
    )


__all__ = [
    "FAMILIES",
    "DEFAULT_CONTROLS",
    "RiskDecision",
    "game_family",
    "resolve_family",
    "default_controls",
    "get_controls",
    "update_controls",
    "toggle_family",
    "evaluate_bet",
    "limit_message",
    "enforce_bet",
    "build_game_reports",
    "control_impact",
    "run_yield_backtest",
    "latest_backtest",
]