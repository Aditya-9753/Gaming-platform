"""Super-admin risk controls and yield backtesting API.

Mounted under ``/api/v1/admin/risk`` alongside the existing read-only exposure
monitor (``/admin/risk/live``). These endpoints change *what stakes are
accepted* and report achieved house margin; they never affect a round's result
(see ``app.services.risk_engine`` and ``app.games.fairness_guard``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import of_request as client_ip_of
from app.api.v1.admin.superadmin import require_superadmin
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models.game import Game
from app.repositories.audit_repo import AuditRepository
from app.services import risk_engine

router = APIRouter(prefix="/admin/risk", tags=["Risk Controls"])

NOTES = {
    "on": "Strict exposure ceilings active: whole-round and per-player stake caps are enforced. Stakes, not outcomes, are controlled.",
    "off": "Standard game limits only (min/max bet). No extra ceilings.",
    "fairness": "Outcomes stay provably fair: the server seed is committed before betting opens and is never readable early.",
}


def _ip(request: Request) -> Optional[str]:
    return client_ip_of(request)


async def _audit(
    db: AsyncSession,
    actor: CurrentUser,
    action: str,
    target_id: str,
    details: Dict[str, Any],
    request: Request,
) -> None:
    await AuditRepository(db).create_log(
        action=action, target_type="SYSTEM", actor_id=actor.id,
        target_id=target_id, details=details, ip_address=_ip(request),
    )


async def _matrix(db: AsyncSession, controls: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Game -> family -> switch, for the control matrix. Falls back to families."""
    game_ids = (await db.execute(select(Game.id))).scalars().all()
    rows: List[Dict[str, Any]] = []
    present: set[str] = set()
    for game_id in game_ids:
        family = risk_engine.game_family(game_id)
        if family is None:
            continue
        present.add(family)
        rows.append({"game_id": game_id, "family": family, "status": controls[family]["status"]})
    for family in risk_engine.FAMILIES:
        if family not in present:
            rows.append({"game_id": family, "family": family, "status": controls[family]["status"]})
    return rows


# =====================================================================
# Exposure controls
# =====================================================================


@router.get("/controls")
async def get_controls(
    _: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Current per-family exposure controls plus the game -> family matrix."""
    controls = await risk_engine.get_controls(db)
    return {
        "families": controls,
        "matrix": await _matrix(db, controls),
        "notes": NOTES,
        "backtester": "always_active",
    }


class ToggleRequest(BaseModel):
    game: str = Field(..., min_length=1, max_length=50, description="Family (wingo/aviator/mines) or a game id")
    status: str = Field(..., pattern="(?i)^(on|off)$")


@router.post("/controls/toggle")
async def toggle_control(
    payload: ToggleRequest,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Flip one family's dedicated ON/OFF switch."""
    family = risk_engine.resolve_family(payload.game)
    controls = await risk_engine.toggle_family(db, family, payload.status, actor_id=actor.id)
    await _audit(db, actor, "RISK_CONTROL_TOGGLE", f"risk.{family}",
                 {"family": family, "status": controls[family]["status"]}, request)
    await db.commit()
    return {
        "status": "SUCCESS",
        "family": family,
        "current_mode": controls[family]["status"],
        "control": controls[family],
    }


class UpdateRequest(BaseModel):
    family: str = Field(..., min_length=1, max_length=50)
    changes: Dict[str, Any] = Field(..., description="Fields to change (target_hold_pct_bp, max_round_pool_paise, max_player_round_paise)")


@router.post("/controls/update")
async def update_control(
    payload: UpdateRequest,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Adjust one family's ceilings / target hold (validated server-side)."""
    family = risk_engine.resolve_family(payload.family)
    controls = await risk_engine.update_controls(db, family, payload.changes, actor_id=actor.id)
    await _audit(db, actor, "RISK_CONTROL_UPDATE", f"risk.{family}",
                 {"family": family, "changes": payload.changes}, request)
    await db.commit()
    return {"status": "SUCCESS", "family": family, "control": controls[family]}


# =====================================================================
# Yield backtest — super admin only (read-only replay)
# =====================================================================


class RiskBacktestRequest(BaseModel):
    days: int = Field(30, ge=1, le=3650)
    max_rounds: int = Field(2000, ge=10, le=20000)


@router.post("/backtest")
async def run_backtest(
    payload: RiskBacktestRequest,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Replay settled bets and report achieved hold vs target per game."""
    report = await risk_engine.run_yield_backtest(
        db, days=payload.days, max_rounds=payload.max_rounds, actor=actor.username
    )
    await _audit(db, actor, "RISK_BACKTEST_RUN", "risk.backtest",
                 {"window_days": payload.days, "wagered_paise": report["totals"]["wagered_paise"],
                  "hold_pct": report["totals"]["hold_pct"]}, request)
    await db.commit()
    return report


@router.get("/backtest/latest")
async def latest_backtest(
    _: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """The most recent stored yield backtest plus a short history."""
    return await risk_engine.latest_backtest(db)