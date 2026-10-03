"""Mines solo game service implementing instant sessions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Set
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import RoundStatus
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.core.logging import get_logger
from app.games.base.state import RedisRoundStateManager
from app.games.mines.rules import (
    TOTAL_TILES,
    compute_mines_multiplier,
    compute_mines_multiplier_bp,
    derive_mine_positions,
)
from app.games.mines.schemas import MinesSessionResponse
from app.models.game import GameEntry, GameRound
from app.repositories.entry_repo import EntryRepository
from app.repositories.game_repo import GameRepository
from app.repositories.round_repo import RoundRepository
from app.services import risk_engine
from app.services.fairness_service import FairnessService
from app.services.wallet_service import WalletService

logger = get_logger("mines_service")


class MinesService:
    """Service handling solo Mines game sessions."""

    def __init__(self, session: AsyncSession, redis=None) -> None:
        self.session = session
        self.redis = redis
        self.entry_repo = EntryRepository(session)
        self.round_repo = RoundRepository(session)
        self.game_repo = GameRepository(session)
        self.fairness_svc = FairnessService(session)
        self.wallet_svc = WalletService(session)

    async def get_active_session(self, user_id: str) -> Optional[GameEntry]:
        """Fetch the user's active, in-progress Mines game entry."""
        stmt = (
            select(GameEntry)
            .join(GameRound, GameEntry.round_id == GameRound.id)
            .where(
                GameEntry.user_id == user_id,
                GameRound.game_id == "mines",
                GameEntry.status == "PLACED",
            )
            .order_by(desc(GameEntry.created_at))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def start_game(
        self,
        user_id: str,
        bet_amount: int,
        mine_count: int,
        idempotency_key: Optional[str] = None,
        client_seed: Optional[str] = None,
    ) -> MinesSessionResponse:
        """Initialize a new Mines session and lock player bet."""
        if not 1 <= mine_count <= 24:
            raise BadRequestException("mine_count must be between 1 and 24")
        if bet_amount <= 0:
            raise BadRequestException("bet_amount must be greater than zero")
        if idempotency_key:
            previous = await self.entry_repo.get_by_idempotency_key(idempotency_key)
            if previous:
                previous_round = await self.round_repo.get_by_id(previous.round_id)
                if (
                    previous.user_id != user_id
                    or not previous_round
                    or previous_round.game_id != "mines"
                ):
                    raise ConflictException("Idempotency key belongs to another action")
                return await self._response_for_entry(previous)

        # 1. Ensure no existing active session
        active = await self.get_active_session(user_id)
        if active:
            raise ConflictException("You already have an active Mines game session in progress")

        # 2. Validate limits
        settings = await self.game_repo.get_settings("mines")
        house_edge_bp = settings.house_edge_percent if settings else 300
        if settings:
            if bet_amount < settings.min_bet:
                raise BadRequestException(f"Minimum bet is {settings.min_bet} paise")
            if bet_amount > settings.max_bet:
                raise BadRequestException(f"Maximum bet is {settings.max_bet} paise")
        game = await self.game_repo.get_by_id("mines")
        if not game or not game.is_active:
            raise BadRequestException("Mines is currently disabled")

        decision = await risk_engine.enforce_bet(
            self.session,
            game_id="mines",
            user_id=user_id,
            requested_paise=bet_amount,
            game_min_bet=settings.min_bet if settings else 0,
            game_max_bet=settings.max_bet if settings else bet_amount,
            round_id=None,  # fresh solo round: no pool yet
        )
        if not decision.allowed:
            raise BadRequestException(risk_engine.limit_message(decision))

        # 3. Create provably fair seed commitment
        latest_round = await self.round_repo.get_latest_round("mines")
        round_no = (latest_round.round_no + 1) if latest_round else 1

        round_obj = await self.fairness_svc.create_round_seed(
            "mines", round_no, client_seed=client_seed
        )
        server_seed = round_obj.server_seed or ""
        server_seed_hash = round_obj.server_seed_hash
        effective_client_seed = round_obj.client_seed or ""

        # 4. Derive mine locations
        mine_positions: Set[int] = derive_mine_positions(
            server_seed=server_seed,
            client_seed=effective_client_seed,
            nonce=round_no,
            mine_count=mine_count,
        )

        # 5. Lock wager in wallet (atomic DB transaction with SELECT FOR UPDATE)
        idem_key = idempotency_key or f"mines:bet:{round_no}:{user_id}:{uuid.uuid4()}"
        round_id = round_obj.id

        await self.wallet_svc.place_bet(
            user_id=user_id,
            amount_paise=bet_amount,
            reference=f"mines:round:{round_id}:bet",
            idempotency_key=idem_key,
        )

        round_obj.status = RoundStatus.RUNNING.value
        round_obj.started_at = datetime.now(timezone.utc)

        # 7. Create Entry row (storing internal secret mines in selection)
        selection = {
            "mine_count": mine_count,
            "house_edge_bp": house_edge_bp,
            "revealed_tiles": [],
            "mines": list(mine_positions),
        }
        entry = await self.entry_repo.create_entry(
            round_id=round_id,
            user_id=user_id,
            bet_amount=bet_amount,
            idempotency_key=idem_key,
            selection=selection,
            status="PLACED",
        )

        next_mult = compute_mines_multiplier(1, mine_count, house_edge_bp)

        response = MinesSessionResponse(
            round_id=round_id,
            entry_id=entry.id,
            bet_amount=bet_amount,
            mine_count=mine_count,
            revealed_tiles=[],
            current_multiplier=1.0,
            next_multiplier=next_mult,
            current_payout=bet_amount,
            status="IN_PROGRESS",
            server_seed_hash=server_seed_hash,
        )
        if self.redis is not None:
            await RedisRoundStateManager(self.redis).set_round_state(
                game_id="mines",
                round_id=round_id,
                round_no=round_no,
                status=RoundStatus.RUNNING.value,
                server_seed_hash=server_seed_hash,
                started_at=round_obj.started_at,
                metadata={"bet_amount": bet_amount, "mine_count": mine_count},
            )
        await self._publish(round_id, "mines_started", response.model_dump())
        return response

    async def _response_for_entry(self, entry: GameEntry) -> MinesSessionResponse:
        round_obj = await self.round_repo.get_by_id(entry.round_id)
        if not round_obj:
            raise NotFoundException("Round record not found")
        selection = entry.selection or {}
        mine_count = int(selection.get("mine_count", 3))
        house_edge_bp = int(selection.get("house_edge_bp", 300))
        revealed = list(selection.get("revealed_tiles", []))
        ended = entry.status != "PLACED"
        multiplier_bp = int(entry.multiplier if entry.multiplier is not None else 100)
        return MinesSessionResponse(
            round_id=round_obj.id,
            entry_id=entry.id,
            bet_amount=entry.bet_amount,
            mine_count=mine_count,
            revealed_tiles=revealed,
            current_multiplier=multiplier_bp / 100,
            next_multiplier=(
                compute_mines_multiplier(len(revealed) + 1, mine_count, house_edge_bp)
                if not ended and len(revealed) < TOTAL_TILES - mine_count
                else None
            ),
            current_payout=(
                entry.payout_amount if ended else entry.bet_amount * multiplier_bp // 100
            ),
            status="IN_PROGRESS" if not ended else ("LOST" if entry.status == "LOST" else "WON"),
            server_seed_hash=round_obj.server_seed_hash,
            mines=sorted(selection.get("mines", [])) if ended else None,
            server_seed=round_obj.server_seed if ended else None,
        )

    async def _publish(self, round_id: str, event: str, data: dict) -> None:
        if self.redis is not None:
            await self.redis.publish(
                "game:mines",
                json.dumps({
                    "type": event,
                    "game_id": "mines",
                    "round_id": round_id,
                    "data": data,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }),
            )

    async def reveal_tile(self, user_id: str, tile_index: int) -> MinesSessionResponse:
        """Reveal a tile in the player's active session."""
        if not 0 <= tile_index < TOTAL_TILES:
            raise BadRequestException("tile_index must be between 0 and 24")
        entry = await self.get_active_session(user_id)
        if not entry:
            raise NotFoundException("No active Mines game found")

        selection = entry.selection or {}
        mine_count = selection.get("mine_count", 3)
        house_edge_bp = int(selection.get("house_edge_bp", 300))
        mines: List[int] = selection.get("mines", [])
        revealed: List[int] = list(selection.get("revealed_tiles", []))

        if tile_index in revealed:
            raise BadRequestException("Tile already revealed")

        round_obj = await self.round_repo.get_by_id(entry.round_id)
        if not round_obj:
            raise NotFoundException("Round record not found")

        # Check if stepped on a mine
        if tile_index in mines:
            # Player lost!
            revealed.append(tile_index)
            entry.selection = {**selection, "revealed_tiles": revealed}

            # Settle loss
            ref = f"mines:round:{round_obj.id}:loss"
            idem = f"mines:settle:{round_obj.id}:{entry.id}:loss"
            await self.wallet_svc.settle_loss(
                user_id=user_id,
                bet_amount_paise=entry.bet_amount,
                reference=ref,
                idempotency_key=idem,
            )

            await self.entry_repo.update_settlement(
                entry_id=entry.id,
                status="LOST",
                payout_amount=0,
                multiplier=0,
            )

            # Complete round and reveal provably fair seed
            await self.round_repo.complete_round(
                round_id=round_obj.id,
                server_seed=round_obj.server_seed or "",
                result_payload={
                    "mines": mines,
                    "mine_positions": sorted(mines),
                    "grid_size": TOTAL_TILES,
                    "mine_count": mine_count,
                    "hit_mine": tile_index,
                    "revealed": revealed,
                },
            )

            response = MinesSessionResponse(
                round_id=round_obj.id,
                entry_id=entry.id,
                bet_amount=entry.bet_amount,
                mine_count=mine_count,
                revealed_tiles=revealed,
                current_multiplier=0.0,
                next_multiplier=None,
                current_payout=0,
                status="LOST",
                server_seed_hash=round_obj.server_seed_hash,
                mines=mines,
                server_seed=round_obj.server_seed,
            )
            if self.redis is not None:
                await RedisRoundStateManager(self.redis).clear_round_state("mines")
            await self._publish(round_obj.id, "mines_bust", response.model_dump())
            return response

        # Safe tile revealed
        revealed.append(tile_index)
        entry.selection = {**selection, "revealed_tiles": revealed}

        safe_tiles_count = TOTAL_TILES - mine_count
        current_mult = compute_mines_multiplier(
            len(revealed), mine_count, house_edge_bp
        )
        multiplier_bp = compute_mines_multiplier_bp(
            len(revealed), mine_count, house_edge_bp
        )
        current_payout = entry.bet_amount * multiplier_bp // 100
        entry.multiplier = multiplier_bp
        entry.payout_amount = current_payout

        # Check if all safe tiles cleared (auto-win)
        if len(revealed) == safe_tiles_count:
            mult_bp = multiplier_bp
            ref = f"mines:round:{round_obj.id}:win"
            idem = f"mines:settle:{round_obj.id}:{entry.id}:win"
            await self.wallet_svc.settle_win(
                user_id=user_id,
                bet_amount_paise=entry.bet_amount,
                win_amount_paise=current_payout - entry.bet_amount,
                reference=ref,
                idempotency_key=idem,
            )

            await self.entry_repo.update_settlement(
                entry_id=entry.id,
                status="WON",
                payout_amount=current_payout,
                multiplier=mult_bp,
            )

            await self.round_repo.complete_round(
                round_id=round_obj.id,
                server_seed=round_obj.server_seed or "",
                result_payload={
                    "mines": mines,
                    "mine_positions": sorted(mines),
                    "grid_size": TOTAL_TILES,
                    "mine_count": mine_count,
                    "revealed": revealed,
                    "win": True,
                },
            )

            response = MinesSessionResponse(
                round_id=round_obj.id,
                entry_id=entry.id,
                bet_amount=entry.bet_amount,
                mine_count=mine_count,
                revealed_tiles=revealed,
                current_multiplier=current_mult,
                next_multiplier=None,
                current_payout=current_payout,
                status="WON",
                server_seed_hash=round_obj.server_seed_hash,
                mines=mines,
                server_seed=round_obj.server_seed,
            )
            if self.redis is not None:
                await RedisRoundStateManager(self.redis).clear_round_state("mines")
            await self._publish(round_obj.id, "mines_won", response.model_dump())
            return response

        # Still in progress
        await self.session.flush()
        next_mult = compute_mines_multiplier(
            len(revealed) + 1, mine_count, house_edge_bp
        )

        response = MinesSessionResponse(
            round_id=round_obj.id,
            entry_id=entry.id,
            bet_amount=entry.bet_amount,
            mine_count=mine_count,
            revealed_tiles=revealed,
            current_multiplier=current_mult,
            next_multiplier=next_mult,
            current_payout=current_payout,
            status="IN_PROGRESS",
            server_seed_hash=round_obj.server_seed_hash,
        )
        await self._publish(round_obj.id, "mines_tile_revealed", response.model_dump())
        return response

    async def cashout(self, user_id: str) -> MinesSessionResponse:
        """Cash out current accumulated winnings in active Mines game."""
        entry = await self.get_active_session(user_id)
        if not entry:
            raise NotFoundException("No active Mines game found")

        selection = entry.selection or {}
        mine_count = selection.get("mine_count", 3)
        house_edge_bp = int(selection.get("house_edge_bp", 300))
        mines: List[int] = selection.get("mines", [])
        revealed: List[int] = list(selection.get("revealed_tiles", []))

        if len(revealed) == 0:
            raise BadRequestException("Cannot cash out without revealing at least one tile")

        round_obj = await self.round_repo.get_by_id(entry.round_id)
        if not round_obj:
            raise NotFoundException("Round record not found")

        current_mult = compute_mines_multiplier(
            len(revealed), mine_count, house_edge_bp
        )
        mult_bp = compute_mines_multiplier_bp(
            len(revealed), mine_count, house_edge_bp
        )
        current_payout = entry.bet_amount * mult_bp // 100

        ref = f"mines:round:{round_obj.id}:cashout"
        idem = f"mines:settle:{round_obj.id}:{entry.id}:cashout"
        await self.wallet_svc.settle_win(
            user_id=user_id,
            bet_amount_paise=entry.bet_amount,
            win_amount_paise=current_payout - entry.bet_amount,
            reference=ref,
            idempotency_key=idem,
        )

        await self.entry_repo.update_settlement(
            entry_id=entry.id,
            status="WON",
            payout_amount=current_payout,
            multiplier=mult_bp,
        )

        await self.round_repo.complete_round(
            round_id=round_obj.id,
            server_seed=round_obj.server_seed or "",
            result_payload={
                "mines": mines,
                "mine_positions": sorted(mines),
                "grid_size": TOTAL_TILES,
                "mine_count": mine_count,
                "revealed": revealed,
                "cashed_out": True,
            },
        )

        response = MinesSessionResponse(
            round_id=round_obj.id,
            entry_id=entry.id,
            bet_amount=entry.bet_amount,
            mine_count=mine_count,
            revealed_tiles=revealed,
            current_multiplier=current_mult,
            next_multiplier=None,
            current_payout=current_payout,
            status="WON",
            server_seed_hash=round_obj.server_seed_hash,
            mines=mines,
            server_seed=round_obj.server_seed,
        )
        if self.redis is not None:
            await RedisRoundStateManager(self.redis).clear_round_state("mines")
        await self._publish(round_obj.id, "mines_cashed_out", response.model_dump())
        return response
