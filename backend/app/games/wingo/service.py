"""WinGo wager placement against the server-controlled betting deadline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GameRoundLifecycle
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.core.logging import get_logger
from app.games.wingo.rules import MODES, normalise_selection
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository
from app.services.wallet_service import WalletService

logger = get_logger("wingo_service")


class WingoBetRequest(BaseModel):
    game_id: str = Field(..., description="wingo_30s | wingo_1m | wingo_3m | wingo_5m")
    round_id: str
    amount: int = Field(..., gt=0, description="Total stake in paise (base x quantity)")
    bet_type: str = Field(..., description="COLOR | NUMBER | SIZE")
    value: str = Field(..., description="GREEN/RED/VIOLET, 0-9, or BIG/SMALL")


class WingoBetResponse(BaseModel):
    entry_id: str
    round_id: str
    game_id: str
    period: Optional[str] = None
    bet_amount: int
    bet_type: str
    value: str
    status: str


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class WingoService:
    def __init__(
        self,
        session: AsyncSession,
        redis: Optional[Redis] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.session = session
        self.redis = redis
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.entry_repo = EntryRepository(session)
        self.round_repo = RoundRepository(session)
        self.game_repo = GameRepository(session)
        self.wallet_svc = WalletService(session)

    def _response(self, entry, game_id: str, period: Optional[str]) -> WingoBetResponse:
        selection: Dict[str, Any] = entry.selection or {}
        return WingoBetResponse(
            entry_id=entry.id,
            round_id=entry.round_id,
            game_id=game_id,
            period=period,
            bet_amount=entry.bet_amount,
            bet_type=selection.get("type", ""),
            value=selection.get("value", ""),
            status=entry.status,
        )

    async def place_bet(
        self, user_id: str, payload: WingoBetRequest, idempotency_key: Optional[str]
    ) -> WingoBetResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise BadRequestException("Idempotency-Key header is required")
        if payload.game_id not in MODES:
            raise BadRequestException("Unknown WinGo mode")
        try:
            bet_type, value = normalise_selection(payload.bet_type, payload.value)
        except ValueError as exc:
            raise BadRequestException(str(exc)) from exc
        selection = {"type": bet_type, "value": value}

        previous = await self.entry_repo.get_by_idempotency_key(idempotency_key)
        if previous:
            if (
                previous.user_id != user_id
                or previous.round_id != payload.round_id
                or previous.bet_amount != payload.amount
                or (previous.selection or {}).get("type") != bet_type
                or (previous.selection or {}).get("value") != value
            ):
                raise ConflictException("Idempotency key was used for a different bet")
            return self._response(previous, payload.game_id, (previous.selection or {}).get("period"))

        game = await self.game_repo.get_by_id(payload.game_id)
        if not game or not game.is_active:
            raise ForbiddenException(f"{MODES[payload.game_id][2]} is currently disabled")
        if not game.settings:
            raise BadRequestException("WinGo settings are not configured")

        round_obj = await self.round_repo.get_by_id(payload.round_id)
        if not round_obj or round_obj.game_id != payload.game_id:
            raise NotFoundException("WinGo period not found")
        if round_obj.status != GameRoundLifecycle.OPEN.value:
            raise BadRequestException("Betting is closed for this period")
        close_at = _parse((round_obj.result or {}).get("betting_closes_at"))
        if close_at is None or self.clock() >= close_at:
            raise BadRequestException("Betting is closed for this period")
        if payload.amount < game.settings.min_bet:
            raise BadRequestException(f"Minimum bet is ₹{game.settings.min_bet / 100:g}")
        if payload.amount > game.settings.max_bet:
            raise BadRequestException(f"Maximum bet is ₹{game.settings.max_bet / 100:g}")

        period = (round_obj.result or {}).get("period")
        selection["period"] = period
        try:
            entry = await self.entry_repo.create_entry(
                round_id=payload.round_id,
                user_id=user_id,
                bet_amount=payload.amount,
                idempotency_key=idempotency_key,
                selection=selection,
                status="PLACED",
            )
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException("Idempotency key was already used")
        await self.wallet_svc.place_bet(
            user_id=user_id,
            amount_paise=payload.amount,
            reference=f"{payload.game_id}:round:{payload.round_id}:bet",
            idempotency_key=idempotency_key,
        )
        await self.session.commit()

        if self.redis is not None:
            try:
                await self.redis.publish(
                    f"game:{payload.game_id}",
                    json.dumps(
                        {
                            "v": 1,
                            "type": "bet_placed",
                            "game_id": payload.game_id,
                            "round_id": payload.round_id,
                            "data": {"bet_amount": payload.amount, "bet_type": bet_type, "value": value},
                            "ts": self.clock().isoformat(),
                        }
                    ),
                )
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("Failed to publish WinGo bet", error=str(exc))
        return self._response(entry, payload.game_id, period)
