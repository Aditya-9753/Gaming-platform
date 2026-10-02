"""Mock-provider coverage for Cricket winner markets and settlement."""

from __future__ import annotations

import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.games.cricket.market_service import CricketMarketService
from app.games.cricket.providers.base import CricketMatch
from app.games.cricket.providers.mock import MockCricketDataProvider
from app.games.cricket.providers.external_api import ExternalCricketDataProvider
from app.models.cricket import CricketPrediction
from app.models.game import Game, GameSetting
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet


@pytest.mark.asyncio
async def test_mock_cricket_provider_prediction_and_auto_settlement():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockCricketDataProvider(
        [
            CricketMatch(
                match_id="match-42",
                home_team="Falcons",
                away_team="Tigers",
                status="SCHEDULED",
            )
        ]
    )
    async with factory() as session:
        role = Role(id=1, name="USER")
        session.add(role)
        await session.flush()
        user = User(
            id="cricket-player",
            username="cricket-player",
            email="cricket@example.test",
            password_hash="unused",
            role_id=role.id,
            is_active=True,
        )
        session.add(user)
        session.add(Wallet(user_id=user.id, balance=10_000, locked_balance=0))
        session.add(Game(id="cricket", name="Cricket", type="SPORTS"))
        session.add(
            GameSetting(
                game_id="cricket",
                min_bet=100,
                max_bet=5_000,
                config={"winner_odds_bp": {"Falcons": 200, "Tigers": 250}},
            )
        )
        await session.commit()

        service = CricketMarketService(session, provider)
        matches = await service.list_matches()
        assert matches[0].id == "match-42"

        prediction = await service.place_prediction(
            user_id=user.id,
            match_id="match-42",
            selection="HOME",
            stake=1_000,
            idempotency_key="cricket-winner-1",
        )
        replay = await service.place_prediction(
            user_id=user.id,
            match_id="match-42",
            selection="HOME",
            stake=1_000,
            idempotency_key="cricket-winner-1",
        )
        assert replay.id == prediction.id
        provider.update(
            CricketMatch(
                match_id="match-42",
                home_team="Falcons",
                away_team="Tigers",
                status="COMPLETED",
                winner="Falcons",
            )
        )
        assert await service.sync_and_settle() == 1
        persisted = await session.get(CricketPrediction, prediction.id)
        assert persisted.status == "WON"
        assert persisted.payout == 2_000
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == user.id))
        ).scalar_one()
        assert wallet.balance == 11_000
        assert wallet.locked_balance == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_abandoned_match_refunds_stake():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    provider = MockCricketDataProvider(
        [CricketMatch("abandoned-1", "Falcons", "Tigers", "SCHEDULED")]
    )
    async with factory() as session:
        role = Role(id=1, name="USER")
        session.add(role)
        await session.flush()
        user = User(
            id="cricket-refund",
            username="cricket-refund",
            email="refund@example.test",
            password_hash="unused",
            role_id=role.id,
            is_active=True,
        )
        session.add_all(
            [
                user,
                Wallet(user_id=user.id, balance=5_000, locked_balance=0),
                Game(id="cricket", name="Cricket", type="SPORTS"),
                GameSetting(game_id="cricket", min_bet=100, max_bet=5_000, config={}),
            ]
        )
        await session.commit()
        service = CricketMarketService(session, provider)
        await service.list_matches()
        await service.place_prediction(
            user_id=user.id,
            match_id="abandoned-1",
            selection="AWAY",
            stake=500,
            idempotency_key="cricket-abandon-bet",
        )
        provider.update(
            CricketMatch(
                "abandoned-1",
                "Falcons",
                "Tigers",
                "ABANDONED",
                abandoned=True,
            )
        )
        assert await service.sync_and_settle() == 1
        prediction = (
            await session.execute(
                select(CricketPrediction).where(
                    CricketPrediction.idempotency_key == "cricket-abandon-bet"
                )
            )
        ).scalar_one()
        wallet = (
            await session.execute(select(Wallet).where(Wallet.user_id == user.id))
        ).scalar_one()
        assert prediction.status == "REFUNDED"
        assert wallet.balance == 5_000
        assert wallet.locked_balance == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_external_provider_caches_match_list_response():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "id": "external-1",
                        "home_team": "Falcons",
                        "away_team": "Tigers",
                        "status": "SCHEDULED",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ExternalCricketDataProvider(
            "https://scores.example.test/api",
            client=client,
            cache_ttl_seconds=10,
        )
        first = await provider.list_matches()
        second = await provider.list_matches()

    assert calls == 1
    assert first[0].match_id == second[0].match_id == "external-1"
