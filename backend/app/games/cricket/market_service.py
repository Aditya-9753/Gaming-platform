"""Winner-only Cricket prediction markets with wallet-backed settlement."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.games.cricket.providers.base import CricketDataProvider, CricketMatch
from app.models.cricket import CricketMatchRecord, CricketPrediction
from app.models.game import GameSetting
from app.services.wallet_service import WalletService


class CricketMarketService:
    def __init__(
        self,
        session: AsyncSession,
        provider: CricketDataProvider,
        redis=None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.redis = redis
        self.wallet = WalletService(session)

    async def _sync(self, match: CricketMatch) -> CricketMatchRecord:
        record = await self.session.get(CricketMatchRecord, match.match_id)
        if record is None:
            record = CricketMatchRecord(
                id=match.match_id,
                home_team=match.home_team,
                away_team=match.away_team,
                status=match.status,
                home_score=match.home_score,
                away_score=match.away_score,
                winner=match.winner,
                abandoned=match.abandoned,
                metadata_json=match.metadata,
            )
            self.session.add(record)
        else:
            record.home_team = match.home_team
            record.away_team = match.away_team
            record.status = match.status
            record.home_score = match.home_score
            record.away_score = match.away_score
            record.winner = match.winner
            record.abandoned = match.abandoned
            record.metadata_json = match.metadata
        return record

    async def list_matches(self) -> list[CricketMatchRecord]:
        matches = await self.provider.list_matches()
        result = [await self._sync(match) for match in matches]
        await self.session.commit()
        return result

    async def get_match(self, match_id: str) -> CricketMatchRecord:
        match = await self.provider.get_match(match_id)
        if match is not None:
            record = await self._sync(match)
            await self.session.commit()
            return record
        record = await self.session.get(CricketMatchRecord, match_id)
        if record is None:
            raise NotFoundException("Cricket match not found")
        return record

    async def place_prediction(
        self,
        *,
        user_id: str,
        match_id: str,
        selection: str,
        stake: int,
        idempotency_key: str,
    ) -> CricketPrediction:
        if selection not in {"HOME", "AWAY"}:
            raise BadRequestException("selection must be HOME or AWAY")
        existing = (
            await self.session.execute(
                select(CricketPrediction).where(
                    CricketPrediction.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing:
            if (
                existing.user_id != user_id
                or existing.match_id != match_id
                or existing.selection != selection
                or existing.stake != stake
            ):
                raise ConflictException("Idempotency key was used for another prediction")
            return existing

        match = await self.get_match(match_id)
        if match.status not in {"SCHEDULED", "UPCOMING", "NOT_STARTED"}:
            raise BadRequestException("Winner market is closed for this match")
        settings = await self._settings()
        minimum = settings.min_bet if settings else 100
        maximum = settings.max_bet if settings else 100_000
        if not minimum <= stake <= maximum:
            raise BadRequestException(
                f"Stake must be between {minimum} and {maximum} paise"
            )
        odds = (await self.winner_odds(match.home_team, match.away_team))[selection]
        if odds < 100 or odds > 100_000:
            raise BadRequestException("Configured winner odds must be 100..100000 basis points")

        prediction_id = str(uuid.uuid4())
        await self.wallet.place_bet(
            user_id=user_id,
            amount_paise=stake,
            idempotency_key=idempotency_key,
            reference=f"cricket:{match_id}:{prediction_id}",
        )
        prediction = CricketPrediction(
            id=prediction_id,
            match_id=match_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            selection=selection,
            stake=stake,
            odds_bp=odds,
        )
        self.session.add(prediction)
        await self.session.commit()
        await self._publish(match_id, "market_update", {"selection": selection})
        return prediction

    async def _settings(self) -> Optional[GameSetting]:
        # GameSetting's primary key is an integer id; look it up by game_id.
        return (
            await self.session.execute(
                select(GameSetting).where(GameSetting.game_id == "cricket")
            )
        ).scalar_one_or_none()

    async def winner_odds(self, home_team: str, away_team: str) -> dict[str, int]:
        """Configured payout odds (basis points, 200 = 2.00x) for HOME / AWAY."""
        settings = await self._settings()
        config = (settings.config or {}) if settings else {}
        odds_map = config.get("winner_odds_bp", {})
        return {
            "HOME": int(odds_map.get(home_team, config.get("home_odds_bp", 200))),
            "AWAY": int(odds_map.get(away_team, config.get("away_odds_bp", 200))),
        }

    async def list_user_predictions(self, user_id: str, limit: int = 20) -> list[tuple[CricketPrediction, CricketMatchRecord]]:
        rows = await self.session.execute(
            select(CricketPrediction, CricketMatchRecord)
            .join(CricketMatchRecord, CricketMatchRecord.id == CricketPrediction.match_id)
            .where(CricketPrediction.user_id == user_id)
            .order_by(CricketPrediction.created_at.desc())
            .limit(limit)
        )
        return [(prediction, match) for prediction, match in rows.all()]

    async def settle_match(
        self,
        match_id: str,
        winner: Optional[str] = None,
        abandoned: bool = False,
        source: str = "PROVIDER",
    ) -> int:
        match = await self.session.get(CricketMatchRecord, match_id)
        if match is None:
            match = await self.get_match(match_id)
        if not abandoned and (not winner or winner not in {match.home_team, match.away_team}):
            raise BadRequestException("Winner must exactly match one of the participating teams")
        match.winner = winner
        match.abandoned = abandoned
        match.status = "ABANDONED" if abandoned else "COMPLETED"
        await self.session.flush()
        predictions = (
            await self.session.execute(
                select(CricketPrediction).where(
                    CricketPrediction.match_id == match_id,
                    CricketPrediction.status == "PLACED",
                )
            )
        ).scalars().all()
        for prediction in predictions:
            reference = f"cricket:{match_id}:prediction:{prediction.id}:{source}"
            if abandoned:
                await self.wallet.refund(
                    user_id=prediction.user_id,
                    amount_paise=prediction.stake,
                    reference=reference,
                    idempotency_key=f"cricket:settle:{prediction.id}:refund",
                )
                prediction.status = "REFUNDED"
                prediction.payout = prediction.stake
            elif prediction.selection == ("HOME" if winner == match.home_team else "AWAY"):
                payout = prediction.stake * prediction.odds_bp // 100
                await self.wallet.settle_win(
                    user_id=prediction.user_id,
                    bet_amount_paise=prediction.stake,
                    win_amount_paise=payout - prediction.stake,
                    reference=reference,
                    idempotency_key=f"cricket:settle:{prediction.id}:win",
                )
                prediction.status = "WON"
                prediction.payout = payout
            else:
                await self.wallet.settle_loss(
                    user_id=prediction.user_id,
                    bet_amount_paise=prediction.stake,
                    reference=reference,
                    idempotency_key=f"cricket:settle:{prediction.id}:loss",
                )
                prediction.status = "LOST"
                prediction.payout = 0
        await self.session.commit()
        await self._publish(match_id, "market_settled", {"winner": winner, "abandoned": abandoned})
        return len(predictions)

    async def sync_and_settle(self) -> int:
        settled = 0
        for match in await self.provider.list_matches():
            record = await self._sync(match)
            await self.session.commit()
            if match.abandoned or (match.status in {"COMPLETED", "FINISHED"} and match.winner):
                settled += await self.settle_match(
                    match.match_id, winner=match.winner, abandoned=match.abandoned
                )
            elif match.status in {"LIVE", "IN_PROGRESS"}:
                await self._publish(
                    match.match_id,
                    "live_score",
                    {
                        "home_score": record.home_score,
                        "away_score": record.away_score,
                        "status": record.status,
                    },
                )
        return settled

    async def _publish(self, match_id: str, event_type: str, data: dict) -> None:
        if self.redis is not None:
            await self.redis.publish(
                "game:cricket",
                json.dumps(
                    {
                        "type": event_type,
                        "game_id": "cricket",
                        "match_id": match_id,
                        "data": data,
                    }
                ),
            )


_cricapi_singleton = None


def get_cricket_provider() -> CricketDataProvider:
    settings = get_settings()
    if settings.CRICAPI_KEY:
        # One shared instance so its cache protects the daily API quota
        global _cricapi_singleton
        if _cricapi_singleton is None:
            from app.games.cricket.providers.cricapi import CricApiProvider

            _cricapi_singleton = CricApiProvider(
                settings.CRICAPI_KEY,
                live_refresh=settings.CRICAPI_LIVE_REFRESH_SECONDS,
                schedule_refresh=settings.CRICAPI_SCHEDULE_REFRESH_SECONDS,
            )
        return _cricapi_singleton
    if settings.CRICKET_DATA_URL:
        from app.games.cricket.providers.external_api import ExternalCricketDataProvider

        return ExternalCricketDataProvider(
            settings.CRICKET_DATA_URL,
            api_key=settings.CRICKET_DATA_API_KEY,
        )
    # No real feed configured: run the clearly labelled simulated Virtual League
    # (also in production) instead of disabling Cricket entirely.
    from app.games.cricket.providers.simulated import SimulatedCricketDataProvider

    return SimulatedCricketDataProvider(secret=settings.JWT_SECRET)
