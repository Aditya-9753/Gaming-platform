"""Aviator wager placement and server-timed cashouts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.core.logging import get_logger
from app.games.aviator.rules import (
    compute_crash_point,
    crash_elapsed_seconds,
    crash_x100_to_float,
    elapsed_since,
    multiplier_x100_at,
)
from app.games.aviator.schemas import AviatorBetResponse, AviatorCashoutResponse
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository
from app.services import risk_engine
from app.services.wallet_service import WalletService

logger = get_logger("aviator_service")


class AviatorService:
    """Places bets and validates cashout strictly against server timestamps."""

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

    async def _player(self, user_id: str) -> str:
        from app.models.user import User
        from app.utils.validators import mask_username

        user = await self.session.get(User, user_id)
        return mask_username(user.username if user else "")

    async def _publish(self, event: str, round_id: str, data: dict) -> None:
        if self.redis is None:
            return
        envelope = {
            "v": 1,
            "type": event,
            "game_id": "aviator",
            "round_id": round_id,
            "data": data,
            "ts": self.clock().isoformat(),
        }
        try:
            await self.redis.publish("game:aviator", json.dumps(envelope))
        except Exception as exc:
            logger.warning("Failed to publish Aviator event", event=event, error=str(exc))

    async def _enabled_game_settings(self, require_active: bool = True):
        game = await self.game_repo.get_by_id("aviator")
        if not game or (require_active and not game.is_active):
            raise ForbiddenException("Aviator is currently disabled")
        if not game.settings:
            raise BadRequestException("Aviator game settings are not configured")
        return game.settings

    @staticmethod
    def _datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    async def place_bet(
        self,
        user_id: str,
        round_id: str,
        amount: int,
        auto_cashout: Optional[float] = None,
        idempotency_key: Optional[str] = None,
    ) -> AviatorBetResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise BadRequestException("Idempotency-Key header is required")
        previous = await self.entry_repo.get_by_idempotency_key(idempotency_key)
        if previous:
            if (
                previous.user_id != user_id
                or previous.round_id != round_id
                or previous.bet_amount != amount
                or (previous.selection or {}).get("auto_cashout") != auto_cashout
            ):
                raise ConflictException("Idempotency key was used for a different bet")
            return AviatorBetResponse(
                entry_id=previous.id,
                round_id=previous.round_id,
                bet_amount=previous.bet_amount,
                status=previous.status,
                auto_cashout=auto_cashout,
            )

        settings = await self._enabled_game_settings()
        round_obj = await self.round_repo.get_by_id(round_id)
        if not round_obj or round_obj.game_id != "aviator":
            raise NotFoundException("Aviator round not found")
        if round_obj.status != GameRoundLifecycle.BETTING_OPEN.value:
            raise BadRequestException("Betting is closed for this round")

        close_at = self._datetime((round_obj.result or {}).get("betting_closes_at"))
        if close_at is None and round_obj.started_at is not None:
            started_at = round_obj.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            duration = float((settings.config or {}).get("betting_duration_sec", 6))
            close_at = started_at + timedelta(seconds=duration)
        if close_at is None:
            raise BadRequestException("Round betting deadline is unavailable")
        if self.clock() >= close_at:
            raise BadRequestException("Betting is closed for this round")
        if amount < settings.min_bet:
            raise BadRequestException(f"Minimum bet is {settings.min_bet} paise")
        if amount > settings.max_bet:
            raise BadRequestException(f"Maximum bet is {settings.max_bet} paise")
        if auto_cashout is not None and not 1.01 <= auto_cashout <= 100:
            raise BadRequestException("Auto-cashout must be between 1.01x and 100x")

        decision = await risk_engine.enforce_bet(
            self.session,
            game_id="aviator",
            user_id=user_id,
            requested_paise=amount,
            game_min_bet=settings.min_bet,
            game_max_bet=settings.max_bet,
            round_id=round_id,
        )
        if not decision.allowed:
            raise BadRequestException(risk_engine.limit_message(decision))

        selection = {"auto_cashout": auto_cashout} if auto_cashout is not None else {}
        try:
            entry = await self.entry_repo.create_entry(
                round_id=round_id,
                user_id=user_id,
                bet_amount=amount,
                idempotency_key=idempotency_key,
                selection=selection,
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
                and (previous.selection or {}).get("auto_cashout") == auto_cashout
            ):
                return AviatorBetResponse(
                    entry_id=previous.id,
                    round_id=previous.round_id,
                    bet_amount=previous.bet_amount,
                    status=previous.status,
                    auto_cashout=auto_cashout,
                )
            raise ConflictException("Idempotency key was already used")
        await self.wallet_svc.place_bet(
            user_id=user_id,
            amount_paise=amount,
            reference=f"aviator:round:{round_id}:bet",
            idempotency_key=idempotency_key,
        )
        await self.session.commit()
        await self._publish(
            "bet_placed",
            round_id,
            {
                "entry_id": entry.id,
                "player": await self._player(user_id),
                "bet_amount": amount,
                "auto_cashout": auto_cashout,
            },
        )
        logger.info("Aviator bet placed", round_id=round_id, amount=amount)
        return AviatorBetResponse(
            entry_id=entry.id,
            round_id=round_id,
            bet_amount=amount,
            status=entry.status,
            auto_cashout=auto_cashout,
        )

    async def cashout(
        self,
        user_id: str,
        round_id: str,
        entry_id: str,
        idempotency_key: str,
        automatic: bool = False,
    ) -> AviatorCashoutResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise BadRequestException("Idempotency-Key header is required")
        settings = await self._enabled_game_settings(require_active=False)
        round_obj = await self.round_repo.get_by_id(round_id)
        if not round_obj or round_obj.game_id != "aviator":
            raise NotFoundException("Aviator round not found")
        if round_obj.status != RoundStatus.RUNNING.value:
            raise BadRequestException("Cannot cash out: round is not running")

        entry = await self.entry_repo.get_by_id_for_update(entry_id)
        if not entry or entry.round_id != round_id:
            raise NotFoundException("Bet entry not found for this round")
        if entry.user_id != user_id:
            raise ForbiddenException("Cannot cash out another player's bet")
        selection = dict(entry.selection or {})
        recovering_cashout = (
            entry.status == "CASHING_OUT"
            and selection.get("cashout_idempotency_key") == idempotency_key
        )
        if entry.status == "WON":
            if (
                selection.get("cashout_idempotency_key") == idempotency_key
            ):
                return AviatorCashoutResponse(
                    entry_id=entry.id,
                    round_id=round_id,
                    multiplier=(entry.multiplier or 100) / 100,
                    payout_amount=entry.payout_amount,
                    status=entry.status,
                )
            raise ConflictException(f"Bet is already {entry.status}")
        if not recovering_cashout and entry.status != "PLACED":
            raise ConflictException(f"Bet is already {entry.status}")
        if recovering_cashout:
            multiplier_x100 = int(selection["cashout_multiplier_x100"])
            payout = int(selection["cashout_payout"])
        else:
            if not round_obj.started_at:
                raise BadRequestException("Round start time is unavailable")
            parameters = round_obj.result or {}
            growth_rate = float(parameters.get("growth_rate", config_value(settings, "growth_rate", 0.08)))
            growth_power = float(parameters.get("growth_power", config_value(settings, "growth_power", 1.3)))
            growth_model = str(parameters.get("growth_model", "power"))
            house_edge_bp = int(parameters.get("house_edge_bp", settings.house_edge_percent))
            crash_x100 = compute_crash_point(
                round_obj.server_seed or "",
                round_obj.client_seed or round_obj.id,
                round_obj.round_no,
                house_edge_bp,
            )
            elapsed = elapsed_since(round_obj.started_at, self.clock())
            current_x100 = min(
                multiplier_x100_at(elapsed, growth_rate, growth_power, growth_model),
                crash_x100,
            )
            if elapsed >= crash_elapsed_seconds(crash_x100, growth_rate, growth_power, growth_model):
                raise BadRequestException("The plane has crashed")

            auto_target = selection.get("auto_cashout") if automatic else None
            if automatic:
                if auto_target is None or current_x100 < int(round(float(auto_target) * 100)):
                    raise ConflictException("Auto-cashout target has not been reached")
                multiplier_x100 = int(round(float(auto_target) * 100))
            else:
                multiplier_x100 = current_x100
            payout = entry.bet_amount * multiplier_x100 // 100
            selection.update(
                {
                    "cashout_idempotency_key": idempotency_key,
                    "cashout_multiplier_x100": multiplier_x100,
                    "cashout_payout": payout,
                }
            )
            entry.selection = selection
            entry.status = "CASHING_OUT"
            await self.session.flush()

        cashout_key = f"aviator:cashout:{round_id}:{entry_id}"
        await self.wallet_svc.settle_win(
            user_id=user_id,
            bet_amount_paise=entry.bet_amount,
            win_amount_paise=payout - entry.bet_amount,
            reference=f"aviator:round:{round_id}:cashout",
            idempotency_key=cashout_key,
        )
        await self.entry_repo.update_settlement(
            entry_id=entry.id,
            status="WON",
            payout_amount=payout,
            multiplier=multiplier_x100,
        )
        await self.session.commit()
        multiplier = crash_x100_to_float(multiplier_x100)
        await self._publish(
            "cashout",
            round_id,
            {
                "entry_id": entry.id,
                "player": await self._player(user_id),
                "bet_amount": entry.bet_amount,
                "multiplier": multiplier,
                "payout": payout,
                "automatic": automatic,
            },
        )
        return AviatorCashoutResponse(
            entry_id=entry.id,
            round_id=round_id,
            multiplier=multiplier,
            payout_amount=payout,
            status="WON",
        )


def config_value(settings, key: str, default: Any) -> Any:
    """Read one optional parameter from the game's JSON configuration."""
    return (settings.config or {}).get(key, default)
