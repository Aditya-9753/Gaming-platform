"""Regression coverage for recovering rounds after an engine process crash."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.games.base.recovery import EngineRecoveryService
from app.models.game import GameRound


@pytest.mark.asyncio
async def test_engine_crash_mid_round_refunds_and_clears_state():
    round_obj = GameRound(
        id="crashed-round",
        game_id="aviator",
        round_no=17,
        status="RUNNING",
        server_seed_hash="commitment",
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [round_obj]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    service = EngineRecoveryService(session_factory, redis=MagicMock())
    service.settlement_mgr.refund_round = AsyncMock()
    service.state_mgr.clear_round_state = AsyncMock()

    recovered = await service.recover_orphaned_rounds()

    assert recovered == 1
    service.settlement_mgr.refund_round.assert_awaited_once_with(
        round_id="crashed-round",
        reason="ENGINE_STARTUP_RECOVERY",
    )
    service.state_mgr.clear_round_state.assert_awaited_once_with("aviator")
