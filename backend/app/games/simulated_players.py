"""Simulated players: bot accounts that genuinely play so lobbies feel alive.

Bots place real (virtual-credit) wagers through the same services as people,
so every number they produce — live bet feeds, leaderboards, round totals —
comes from actual settled bets rather than fabricated figures.

Enabled by SIMULATED_PLAYERS (auto: on outside production). Bot accounts get
an unguessable random password, so nobody can sign in as them.
"""

from __future__ import annotations

import asyncio
import random
import secrets
import uuid
from typing import Dict, List, Set

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import TransactionType, UserRole
from app.core.logging import get_logger
from app.core.security import hash_password
from app.games.base.state import RedisRoundStateManager
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet

logger = get_logger("simulated_players")

BOT_NAMES: List[str] = [
    "Rahul_King", "Priya_07", "AceVikram", "LuckyAman", "Sneha_Wins", "Rohit4567", "KaranXP",
    "Neha_Star", "Arjun_Pro", "Simran22", "DeepakBoss", "Ankit_Gamer", "Pooja_Luck", "Vivek_99",
    "Riya_Rocks", "SahilJet", "Manish_77", "Kavya_Q", "Aditya_GG", "Ishaan_Fly", "Tanya_Ace",
    "Harsh_Max", "Meera_Gold", "Yash_Turbo", "Nikhil_08", "Ayesha_Win", "Kunal_Pilot", "Divya_Sky",
    "Sameer_X", "Pallavi_R", "Gaurav_Hit", "Ritika_M", "Abhishek_7", "Shreya_Bet", "Varun_Zoom",
    "Anjali_Star", "Mohit_Strike", "Komal_Joy", "Raj_Thunder", "Sonia_Lucky",
]

START_BALANCE = 200_000      # ₹2,000
TOPUP_BELOW = 20_000         # top up when under ₹200
TOPUP_AMOUNT = 150_000


def _amount(low_rupees: int, high_rupees: int) -> int:
    """Human-looking stake in paise (₹10, ₹50, ₹120 …)."""
    rupees = random.choice([10, 20, 50, 100, 100, 200, 500]) if random.random() < 0.7 else random.randint(low_rupees, high_rupees)
    return max(1, rupees) * 100


async def ensure_bots(session: AsyncSession) -> List[str]:
    """Create any missing bot accounts; returns their user ids."""
    role = (await session.execute(select(Role).where(Role.name == UserRole.USER.value))).scalar_one_or_none()
    if role is None:
        return []
    existing = {
        u.username: u.id
        for u in (await session.execute(select(User).where(User.username.in_(BOT_NAMES)))).scalars()
    }
    for name in BOT_NAMES:
        if name in existing:
            continue
        user = User(
            id=str(uuid.uuid4()),
            username=name,
            email=None,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role_id=role.id,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        session.add(Wallet(id=str(uuid.uuid4()), user_id=user.id, balance=START_BALANCE, locked_balance=0, currency="VIRTUAL"))
        existing[name] = user.id
    await session.commit()
    return list(existing.values())


class SimulatedPlayers:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], redis: Redis, game_ids: List[str]) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.state = RedisRoundStateManager(redis)
        self.game_ids = game_ids
        self.bots: List[str] = []
        self._served: Dict[str, Set[str]] = {}  # game_id -> round ids already handled
        self._tasks: Set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _topup(self) -> None:
        from app.services.wallet_service import WalletService

        async with self.session_factory() as session:
            wallets = (await session.execute(select(Wallet).where(Wallet.user_id.in_(self.bots)))).scalars().all()
            low = [w.user_id for w in wallets if w.balance - w.locked_balance < TOPUP_BELOW]
        for user_id in low:
            async with self.session_factory() as session:
                await WalletService(session).credit_bonus(
                    user_id=user_id,
                    amount_paise=TOPUP_AMOUNT,
                    idempotency_key=f"bot-topup:{uuid.uuid4()}",
                    reference="SIMULATED_PLAYER_TOPUP",
                    description="Simulated player top-up",
                    tx_type=TransactionType.BONUS,
                )
                await session.commit()

    async def _aviator(self, round_id: str) -> None:
        from app.games.aviator.service import AviatorService

        for bot in random.sample(self.bots, k=random.randint(4, 10)):
            await asyncio.sleep(random.uniform(0.1, 0.6))
            target = round(random.choice([1.2, 1.5, 1.8, 2.0, 2.0, 2.5, 3.0, 5.0, 10.0]) * random.uniform(0.9, 1.1), 2)
            try:
                async with self.session_factory() as session:
                    await AviatorService(session, redis=self.redis).place_bet(
                        user_id=bot, round_id=round_id, amount=_amount(10, 800),
                        auto_cashout=max(1.01, min(target, 100.0)), idempotency_key=f"bot:{round_id}:{bot}",
                    )
            except Exception as exc:
                logger.debug("Bot aviator bet skipped", error=str(exc))
                return  # betting closed — stop for this round

    async def _wingo(self, game_id: str, round_id: str) -> None:
        from app.games.wingo.service import WingoBetRequest, WingoService

        for bot in random.sample(self.bots, k=random.randint(2, 7)):
            await asyncio.sleep(random.uniform(0.2, 1.0))
            kind = random.choice(["COLOR", "COLOR", "SIZE", "SIZE", "NUMBER"])
            value = (
                random.choice(["GREEN", "RED", "GREEN", "RED", "VIOLET"]) if kind == "COLOR"
                else random.choice(["BIG", "SMALL"]) if kind == "SIZE"
                else str(random.randint(0, 9))
            )
            try:
                async with self.session_factory() as session:
                    await WingoService(session, redis=self.redis).place_bet(
                        bot,
                        WingoBetRequest(game_id=game_id, round_id=round_id, amount=_amount(10, 300), bet_type=kind, value=value),
                        f"bot:{round_id}:{bot}",
                    )
            except Exception as exc:
                logger.debug("Bot wingo bet skipped", error=str(exc))
                return

    async def _mines(self) -> None:
        from app.games.mines.service import MinesService

        bot = random.choice(self.bots)
        try:
            async with self.session_factory() as session:
                service = MinesService(session, redis=self.redis)
                if await service.get_active_session(bot):
                    return
                await service.start_game(bot, _amount(10, 300), random.choice([1, 3, 3, 5, 10]), idempotency_key=f"bot-mines:{uuid.uuid4()}")
                await session.commit()
                tiles = random.sample(range(25), random.randint(1, 5))
                for tile in tiles:
                    state = await service.reveal_tile(bot, tile)
                    await session.commit()
                    if state.status != "IN_PROGRESS":
                        return
                await service.cashout(bot)
                await session.commit()
        except Exception as exc:
            logger.debug("Bot mines game skipped", error=str(exc))

    async def run(self) -> None:
        async with self.session_factory() as session:
            self.bots = await ensure_bots(session)
        if not self.bots:
            return
        logger.info("Simulated players active", bots=len(self.bots))
        tick = 0
        while True:
            try:
                if tick % 20 == 0:
                    await self._topup()
                for game_id in self.game_ids:
                    snapshot = await self.state.get_round_state(game_id)
                    if not snapshot or snapshot.status not in ("BETTING_OPEN", "OPEN"):
                        continue
                    served = self._served.setdefault(game_id, set())
                    if snapshot.round_id in served:
                        continue
                    served.add(snapshot.round_id)
                    if len(served) > 50:
                        served.clear()
                        served.add(snapshot.round_id)
                    if game_id == "aviator":
                        self._spawn(self._aviator(snapshot.round_id))
                    else:
                        self._spawn(self._wingo(game_id, snapshot.round_id))
                if random.random() < 0.08:
                    self._spawn(self._mines())
            except asyncio.CancelledError:
                for task in list(self._tasks):
                    task.cancel()
                raise
            except Exception as exc:
                logger.warning("Simulated players tick failed", error=str(exc))
            tick += 1
            await asyncio.sleep(1.5)
