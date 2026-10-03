"""Teen Patti wager placement against the server-controlled betting deadline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Optional

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GameRoundLifecycle
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.games.teen_patti.rules import GAME_ID, normalise_side
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository
from app.services.wallet_service import WalletService

logger = get_logger("teen_patti_service")


class TeenPattiBetRequest(BaseModel):
    round_id: str
    amount: int = Field(..., gt=0, description="Stake in paise")
    side: str = Field(..., description="A or B")


class TeenPattiBetResponse(BaseModel):
    entry_id: str
    round_id: str
    round_no: int
    bet_amount: int
    side: str
    status: str


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class TeenPattiService:
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

    async def place_bet(
        self, user_id: str, payload: TeenPattiBetRequest, idempotency_key: Optional[str]
    ) -> TeenPattiBetResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise BadRequestException("Idempotency-Key header is required")
        try:
            side = normalise_side(payload.side)
        except ValueError as exc:
            raise BadRequestException(str(exc)) from exc

        previous = await self.entry_repo.get_by_idempotency_key(idempotency_key)
        if previous:
            if (
                previous.user_id != user_id
                or previous.round_id != payload.round_id
                or previous.bet_amount != payload.amount
                or (previous.selection or {}).get("value") != side
            ):
                raise ConflictException("Idempotency key was used for a different bet")
            prev_round = await self.round_repo.get_by_id(previous.round_id)
            return TeenPattiBetResponse(
                entry_id=previous.id, round_id=previous.round_id, round_no=prev_round.round_no if prev_round else 0,
                bet_amount=previous.bet_amount, side=side, status=previous.status,
            )

        game = await self.game_repo.get_by_id(GAME_ID)
        if not game or not game.is_active:
            raise ForbiddenException("Teen Patti is currently disabled")
        if not game.settings:
            raise BadRequestException("Teen Patti settings are not configured")

        round_obj = await self.round_repo.get_by_id(payload.round_id)
        if not round_obj or round_obj.game_id != GAME_ID:
            raise NotFoundException("Teen Patti round not found")
        if round_obj.status != GameRoundLifecycle.OPEN.value:
            raise BadRequestException("Betting is closed for this round")
        close_at = _parse((round_obj.result or {}).get("betting_closes_at"))
        if close_at is None or self.clock() >= close_at:
            raise BadRequestException("Betting is closed for this round")
        if payload.amount < game.settings.min_bet:
            raise BadRequestException(f"Minimum bet is ₹{game.settings.min_bet / 100:g}")
        if payload.amount > game.settings.max_bet:
            raise BadRequestException(f"Maximum bet is ₹{game.settings.max_bet / 100:g}")

        try:
            entry = await self.entry_repo.create_entry(
                round_id=payload.round_id,
                user_id=user_id,
                bet_amount=payload.amount,
                idempotency_key=idempotency_key,
                selection={"type": "SIDE", "value": side},
                status="PLACED",
            )
        except IntegrityError:
            await self.session.rollback()
            raise ConflictException("Idempotency key was already used")
        await self.wallet_svc.place_bet(
            user_id=user_id,
            amount_paise=payload.amount,
            reference=f"{GAME_ID}:round:{payload.round_id}:bet",
            idempotency_key=idempotency_key,
        )
        await self.session.commit()

        if self.redis is not None:
            try:
                await self.redis.publish(
                    f"game:{GAME_ID}",
                    json.dumps({
                        "v": 1,
                        "type": "bet_placed",
                        "game_id": GAME_ID,
                        "round_id": payload.round_id,
                        "data": {"bet_amount": payload.amount, "side": side},
                        "ts": self.clock().isoformat(),
                    }),
                )
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("Failed to publish Teen Patti bet", error=str(exc))
        return TeenPattiBetResponse(
            entry_id=entry.id, round_id=entry.round_id, round_no=round_obj.round_no,
            bet_amount=entry.bet_amount, side=side, status=entry.status,
        )
