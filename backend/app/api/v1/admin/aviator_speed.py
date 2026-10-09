"""Super admin: Aviator speed control (growth rate, betting time, break between rounds).

Changes are stored in the Aviator game settings and apply from the next round; a round that
is already flying keeps the rate it was published with. Speed never affects where a round
crashes (that comes from the seeds), only how quickly the multiplier gets there.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.superadmin import _audit, require_superadmin
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import BadRequestException, NotFoundException
from app.games.aviator.rules import DEFAULT_EXP_GROWTH_RATE, GROWTH_MODEL_EXPONENTIAL
from app.repositories.game_repo import GameRepository

router = APIRouter(prefix="/admin/aviator", tags=["Super Admin"])

# Keys only the super admin may change (also enforced on the generic game-settings endpoint)
SPEED_KEYS = ("exp_growth_rate", "growth_model", "growth_rate", "growth_power", "betting_duration_sec", "intermission_sec")

MIN_RATE, MAX_RATE = 0.02, 0.5          # 2x in ~34.7 s ... ~1.4 s
MIN_BETTING, MAX_BETTING = 3.0, 30.0
MIN_BREAK, MAX_BREAK = 1.0, 15.0
DEFAULT_BETTING, DEFAULT_BREAK = 6.0, 2.0

PRESETS = [
    {"id": "relaxed", "label": "Relaxed", "rate": 0.045},
    {"id": "normal", "label": "Normal", "rate": 0.06},
    {"id": "fast", "label": "Fast", "rate": 0.09},
    {"id": "very_fast", "label": "Very fast", "rate": 0.13},
    {"id": "turbo", "label": "Turbo", "rate": 0.2},
]


def _seconds_to(rate: float) -> Dict[str, float]:
    return {f"{m}x": round(math.log(m) / rate, 1) for m in (2, 5, 10, 100)}


def _view(config: Dict[str, Any]) -> Dict[str, Any]:
    rate = float(config.get("exp_growth_rate", DEFAULT_EXP_GROWTH_RATE))
    return {
        "exp_growth_rate": rate,
        "seconds_to": _seconds_to(rate),
        "betting_duration_sec": float(config.get("betting_duration_sec", DEFAULT_BETTING)),
        "intermission_sec": float(config.get("intermission_sec", DEFAULT_BREAK)),
        "growth_model": config.get("growth_model", GROWTH_MODEL_EXPONENTIAL),
        "presets": [{**p, "seconds_to": _seconds_to(p["rate"])} for p in PRESETS],
        "limits": {"rate": [MIN_RATE, MAX_RATE], "betting_duration_sec": [MIN_BETTING, MAX_BETTING],
                   "intermission_sec": [MIN_BREAK, MAX_BREAK]},
    }


class SpeedUpdate(BaseModel):
    exp_growth_rate: Optional[float] = Field(None, description="Growth per second (m = e^(rate·t))")
    seconds_to_2x: Optional[float] = Field(None, description="Alternative to exp_growth_rate")
    betting_duration_sec: Optional[float] = None
    intermission_sec: Optional[float] = None


async def _settings(db: AsyncSession):
    settings = await GameRepository(db).get_settings("aviator")
    if settings is None:
        raise NotFoundException("Aviator settings are not configured")
    return settings


@router.get("/speed")
async def get_speed(actor: CurrentUser = Depends(require_superadmin), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return _view((await _settings(db)).config or {})


@router.put("/speed")
async def set_speed(payload: SpeedUpdate, request: Request, actor: CurrentUser = Depends(require_superadmin),
                    db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    settings = await _settings(db)
    old = dict(settings.config or {})
    config = dict(old)

    rate = payload.exp_growth_rate
    if payload.seconds_to_2x is not None:
        if not math.isfinite(payload.seconds_to_2x) or payload.seconds_to_2x <= 0:
            raise BadRequestException("Seconds to 2x must be positive")
        rate = math.log(2) / payload.seconds_to_2x
    if rate is not None:
        if not math.isfinite(rate) or not MIN_RATE <= rate <= MAX_RATE:
            raise BadRequestException(
                f"Speed must give 2x between {math.log(2) / MAX_RATE:.1f} and {math.log(2) / MIN_RATE:.1f} seconds")
        config["exp_growth_rate"] = round(rate, 4)
        config["growth_model"] = GROWTH_MODEL_EXPONENTIAL
    if payload.betting_duration_sec is not None:
        if not MIN_BETTING <= payload.betting_duration_sec <= MAX_BETTING:
            raise BadRequestException(f"Betting time must be {MIN_BETTING:.0f}-{MAX_BETTING:.0f} seconds")
        config["betting_duration_sec"] = round(payload.betting_duration_sec, 1)
    if payload.intermission_sec is not None:
        if not MIN_BREAK <= payload.intermission_sec <= MAX_BREAK:
            raise BadRequestException(f"Break between rounds must be {MIN_BREAK:.0f}-{MAX_BREAK:.0f} seconds")
        config["intermission_sec"] = round(payload.intermission_sec, 1)

    if config == old:
        return _view(config)
    settings.config = config  # new dict so the JSON column is marked changed
    await _audit(db, actor, "AVIATOR_SPEED_CHANGED", "GAME", "aviator",
                 {"old": {k: old.get(k) for k in SPEED_KEYS}, "new": {k: config.get(k) for k in SPEED_KEYS}}, request)
    await db.commit()
    return _view(config)
