"""Color Prediction wager placement."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

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
from app.games.color.rules import ColourResult, round_timing_seconds
from app.games.color.schemas import ColorBetResponse
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository
from app.services.wallet_service import WalletService

logger = get_logger("color_service")


class ColorService:
    """Places color bets against the server-controlled OPEN deadline."""

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

    async def _publish(self, event: str, round_id: str, data: dict) -> None:
        if self.redis is None:
            return
        envelope = {
            "v": 1,
            "type": event,
            "game_id": "color",
            "round_id": round_id,
            "data": data,
            "ts": self.clock().isoformat(),
        }
        try:
            await self.redis.publish("game:color", json.dumps(envelope))
        except Exception as exc:
            logger.warning("Failed to publish Color event", event=event, error=str(exc))

    async def place_bet(
        self,
        user_id: str,
        round_id: str,
        amount: int,
        colour: ColourResult,
        idempotency_key: Optional[str] = None,
    ) -> ColorBetResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise BadRequestException("Idempotency-Key header is required")
        previous = await self.entry_repo.get_by_idempotency_key(idempotency_key)
        if previous:
            if (
                previous.user_id != user_id
                or previous.round_id != round_id
                or previous.bet_amount != amount
                or (previous.selection or {}).get("colour") != colour.value
            ):
                raise ConflictException("Idempotency key was used for a different bet")
            return ColorBetResponse(
                entry_id=previous.id,
                round_id=previous.round_id,
                bet_amount=previous.bet_amount,
                colour=colour.value,
                status=previous.status,
            )

        game = await self.game_repo.get_by_id("color")
        if not game or not game.is_active:
            raise ForbiddenException("Color Prediction is currently disabled")
        if not game.settings:
            raise BadRequestException("Color Prediction settings are not configured")

        round_obj = await self.round_repo.get_by_id(round_id)
        if not round_obj or round_obj.game_id != "color":
            raise NotFoundException("Color round not found")
        if round_obj.status != GameRoundLifecycle.OPEN.value:
            raise BadRequestException("Betting is closed for this round")
        close_at = parse_timestamp((round_obj.result or {}).get("betting_closes_at"))
        if close_at is None and round_obj.started_at is not None:
            timer_seconds, lock_before_end = round_timing_seconds(
                game.settings.config
            )
            started_at = round_obj.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            close_at = started_at + timedelta(
                seconds=timer_seconds - lock_before_end
            )
        if close_at is None:
            raise BadRequestException("Round betting deadline is unavailable")
        if self.clock() >= close_at:
            raise BadRequestException("Betting is closed for this round")
        if amount < game.settings.min_bet:
            raise BadRequestException(f"Minimum bet is {game.settings.min_bet} paise")
        if amount > game.settings.max_bet:
            raise BadRequestException(f"Maximum bet is {game.settings.max_bet} paise")

        try:
            entry = await self.entry_repo.create_entry(
                round_id=round_id,
                user_id=user_id,
                bet_amount=amount,
                idempotency_key=idempotency_key,
                selection={"colour": colour.value},
                status="PLACED",
            )
        except IntegrityError:
            await self.session.rollback()
            previous = await self.entry_repo.get_by_idempotency_key(idempotency_key)
            if (
                previous
                and previous.user_id == user_id
                and previous.round_id == round_id
                and previous.bet_amount == amount
                and (previous.selection or {}).get("colour") == colour.value
            ):
                return ColorBetResponse(
                    entry_id=previous.id,
                    round_id=previous.round_id,
                    bet_amount=previous.bet_amount,
                    colour=colour.value,
                    status=previous.status,
                )
            raise ConflictException("Idempotency key was already used")
        await self.wallet_svc.place_bet(
            user_id=user_id,
            amount_paise=amount,
            reference=f"color:round:{round_id}:bet",
            idempotency_key=idempotency_key,
        )
        await self.session.commit()
        await self._publish(
            "bet_placed",
            round_id,
            {"bet_amount": amount, "colour": colour.value},
        )
        logger.info("Color bet placed", round_id=round_id, colour=colour.value)
        return ColorBetResponse(
            entry_id=entry.id,
            round_id=round_id,
            bet_amount=amount,
            colour=colour.value,
            status=entry.status,
        )


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse a persisted UTC deadline consistently across database backends."""
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
