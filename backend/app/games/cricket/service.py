"""Cricket game service for wagers and outcomes."""

from __future__ import annotations

import uuid
from typing import Optional
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RoundStatus
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.games.cricket.rules import BallOutcomeType
from app.games.cricket.schemas import CricketBetResponse
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository
from app.services.wallet_service import WalletService

logger = get_logger("cricket_service")


class CricketService:
    """Service handling player wagers for Cricket."""

    def __init__(self, session: AsyncSession, redis: Optional[Redis] = None) -> None:
        self.session = session
        self.redis = redis
        self.entry_repo = EntryRepository(session)
        self.round_repo = RoundRepository(session)
        self.game_repo = GameRepository(session)
        self.wallet_svc = WalletService(session)

    async def place_bet(
        self,
        user_id: str,
        round_id: str,
        amount: int,
        prediction: BallOutcomeType,
        idempotency_key: Optional[str] = None,
    ) -> CricketBetResponse:
        """Place a ball delivery wager during betting window."""
        round_obj = await self.round_repo.get_by_id(round_id)
        if not round_obj or round_obj.game_id != "cricket":
            raise NotFoundException("Cricket round not found")

        if round_obj.status != RoundStatus.BETTING.value:
            raise BadRequestException(
                f"Betting is closed for this delivery (status: {round_obj.status})"
            )

        settings = await self.game_repo.get_settings("cricket")
        if settings:
            if amount < settings.min_bet:
                raise BadRequestException(f"Minimum bet is {settings.min_bet} paise")
            if amount > settings.max_bet:
                raise BadRequestException(f"Maximum bet is {settings.max_bet} paise")

        idem_key = idempotency_key or f"cricket:bet:{round_id}:{user_id}:{uuid.uuid4()}"

        # Deduct/lock virtual credits in wallet
        reference = f"cricket:round:{round_id}:bet"
        await self.wallet_svc.place_bet(
            user_id=user_id,
            amount=amount,
            reference=reference,
            idempotency_key=idem_key,
        )

        # Record entry
        selection = {"prediction": prediction.value}
        entry = await self.entry_repo.create_entry(
            round_id=round_id,
            user_id=user_id,
            bet_amount=amount,
            idempotency_key=idem_key,
            selection=selection,
            status="PLACED",
        )

        logger.info(
            "Cricket bet placed",
            user_id=user_id,
            round_id=round_id,
            amount=amount,
            prediction=prediction.value,
        )

        return CricketBetResponse(
            entry_id=entry.id,
            round_id=entry.round_id,
            bet_amount=entry.bet_amount,
            prediction=prediction.value,
            status=entry.status,
        )
