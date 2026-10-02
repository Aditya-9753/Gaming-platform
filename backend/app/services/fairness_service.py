"""Fairness service: seed lifecycle for provably-fair rounds.

Responsibilities:
- create_round_seed: generate server_seed + hash, persist to DB.
- reveal_seed: called AFTER round is settled; exposes server_seed.
- verify_round: recompute the outcome from revealed seeds and confirm it
  matches the stored result.  Only works on COMPLETED rounds.
- Active round seeds are NEVER revealed: only the commitment hash is returned.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import GameRoundLifecycle, RoundStatus
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.models.game import GameRound
from app.utils.rng import (
    generate_server_seed,
    hash_server_seed,
    verify_seed_commitment,
)

logger = get_logger("fairness_service")


class FairnessService:
    """Manages the provably-fair seed lifecycle for game rounds."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    # ------------------------------------------------------------------
    # Seed creation  (called when a round is created, before betting opens)
    # ------------------------------------------------------------------

    async def create_round_seed(
        self,
        game_id: str,
        round_no: int,
        client_seed: Optional[str] = None,
    ) -> GameRound:
        """Generate a new server_seed, commit its hash, and persist a new round.

        The server_seed is stored in the DB but NEVER returned to the client
        until the round is settled (only the hash is public).

        Args:
            game_id:     The game this round belongs to.
            round_no:    Sequential round number (unique per game).
            client_seed: Optional public client seed (default: round UUID).

        Returns:
            The persisted GameRound with server_seed_hash populated.
        """
        server_seed = generate_server_seed(32)
        server_seed_hash = hash_server_seed(server_seed)
        round_id = str(uuid.uuid4())
        cs = client_seed or round_id  # default client_seed is the round UUID itself

        game_round = GameRound(
            id=round_id,
            game_id=game_id,
            round_no=round_no,
            status=RoundStatus.SCHEDULED.value,
            server_seed_hash=server_seed_hash,
            server_seed=server_seed,   # stored encrypted-at-rest in prod DB
            client_seed=cs,
            result=None,
        )
        self._db.add(game_round)
        await self._db.flush()
        logger.info(
            "Round seed created",
            game_id=game_id,
            round_no=round_no,
            round_id=round_id,
        )
        return game_round

    # ------------------------------------------------------------------
    # Seed reveal  (called internally when round settles)
    # ------------------------------------------------------------------

    async def reveal_seed(self, round_id: str) -> GameRound:
        """Mark that the seed is now revealable (round must be COMPLETED).

        Does NOT change the stored seed — simply validates the round status.
        The seed is already in the DB; the API layer decides whether to expose it.

        Raises:
            NotFoundException: if round doesn't exist.
            ForbiddenException: if round is not yet settled.
        """
        game_round = await self._get_round(round_id)

        if game_round.status not in {
            RoundStatus.COMPLETED.value,
            GameRoundLifecycle.HISTORY.value,
        }:
            raise ForbiddenException(
                "Server seed can only be revealed after the round is settled"
            )

        logger.info("Seed reveal requested", round_id=round_id)
        return game_round

    # ------------------------------------------------------------------
    # Verification  (player-facing: recompute and confirm)
    # ------------------------------------------------------------------

    async def verify_round(self, round_id: str) -> Dict[str, Any]:
        """Recompute the round outcome and confirm it matches the stored result.

        Only works for COMPLETED rounds.

        Returns a dict with:
          - round_id, game_id, round_no
          - server_seed_hash  (public commitment)
          - server_seed       (revealed)
          - client_seed
          - nonce             (= round_no, used in derivation)
          - stored_result     (what the server stored)
          - recomputed_result (what the verifier gets from the seeds)
          - hash_valid        (True if SHA256(server_seed) == server_seed_hash)
          - result_matches    (True if recomputed == stored)

        Raises:
            NotFoundException: round not found.
            ForbiddenException: round not yet settled.
        """
        game_round = await self._get_round(round_id)

        if game_round.status not in {
            RoundStatus.COMPLETED.value,
            GameRoundLifecycle.HISTORY.value,
        }:
            raise ForbiddenException(
                "Round verification is only available after settlement"
            )

        if not game_round.server_seed:
            raise BadRequestException("Server seed not available for this round")

        # 1. Verify commitment
        hash_valid = verify_seed_commitment(
            game_round.server_seed, game_round.server_seed_hash
        )

        # 2. Recompute the outcome for this game type
        recomputed = self._recompute_result(game_round)

        # 3. Compare with stored result
        stored = game_round.result or {}
        result_matches = self._results_match(stored, recomputed)

        logger.info(
            "Round verified",
            round_id=round_id,
            hash_valid=hash_valid,
            result_matches=result_matches,
        )

        return {
            "round_id": game_round.id,
            "game_id": game_round.game_id,
            "round_no": game_round.round_no,
            "server_seed_hash": game_round.server_seed_hash,
            "server_seed": game_round.server_seed,
            "client_seed": game_round.client_seed or "",
            "nonce": game_round.round_no,
            "stored_result": stored,
            "recomputed_result": recomputed,
            "hash_valid": hash_valid,
            "result_matches": result_matches,
        }

    # ------------------------------------------------------------------
    # Safe public view  (for active rounds — hash only, no seed)
    # ------------------------------------------------------------------

    async def get_round_commitment(self, round_id: str) -> Dict[str, Any]:
        """Return the public commitment for any round (active or settled).

        For active rounds: only server_seed_hash is returned.
        For settled rounds: also returns server_seed and verification data.
        """
        game_round = await self._get_round(round_id)
        settled = game_round.status in {
            RoundStatus.COMPLETED.value,
            GameRoundLifecycle.HISTORY.value,
        }

        base = {
            "round_id": game_round.id,
            "game_id": game_round.game_id,
            "round_no": game_round.round_no,
            "status": game_round.status,
            "server_seed_hash": game_round.server_seed_hash,
            "client_seed": game_round.client_seed if settled else None,
            "seed_revealed": settled,
        }

        if settled:
            base["server_seed"] = game_round.server_seed
        else:
            base["server_seed"] = None  # NEVER expose active seed

        return base

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _get_round(self, round_id: str) -> GameRound:
        result = await self._db.execute(
            select(GameRound).where(GameRound.id == round_id)
        )
        game_round = result.scalar_one_or_none()
        if not game_round:
            raise NotFoundException(f"Round {round_id} not found")
        return game_round

    def _recompute_result(self, game_round: GameRound) -> Dict[str, Any]:
        """Dispatch to the correct game-type rules module."""
        game_id = game_round.game_id.lower()
        server_seed = game_round.server_seed or ""
        client_seed = game_round.client_seed or game_round.id
        nonce = game_round.round_no

        if "aviator" in game_id:
            from app.games.aviator.rules import (
                compute_crash_point,
                crash_x100_to_float,
                format_crash,
            )
            crash_x100 = compute_crash_point(
                server_seed,
                client_seed,
                nonce,
                int((game_round.result or {}).get("house_edge_bp", 300)),
            )
            stored_crash = (game_round.result or {}).get("crash_point")
            crash_value = (
                format_crash(crash_x100)
                if isinstance(stored_crash, str)
                else crash_x100_to_float(crash_x100)
            )
            return {
                "crash_point_x100": crash_x100,
                "crash_point": crash_value,
            }

        elif "color" in game_id or "colour" in game_id:
            from app.games.color.rules import compute_colour
            payout_multipliers = (game_round.result or {}).get("payout_multipliers")
            outcome = compute_colour(
                server_seed,
                client_seed,
                nonce,
                payout_multipliers=payout_multipliers,
            )
            return {
                "winning_colour": outcome.colour.value,
                "slot": outcome.slot,
                "payout_x100": outcome.payout_x100,
            }

        elif "mines" in game_id:
            # Mines: the mine positions are a shuffled grid
            from app.utils.rng import derive_shuffled_indices
            stored = game_round.result or {}
            grid_size = stored.get("grid_size", 25)
            mine_count = stored.get("mine_count", 5)
            shuffled = derive_shuffled_indices(server_seed, client_seed, nonce, grid_size)
            mine_positions = sorted(shuffled[:mine_count])
            return {
                "mine_positions": mine_positions,
                "grid_size": grid_size,
                "mine_count": mine_count,
            }

        # Generic fallback: just derive a float
        from app.utils.rng import derive_float
        r = derive_float(server_seed, client_seed, nonce)
        return {"random_float": r}

    @staticmethod
    def _results_match(stored: Dict[str, Any], recomputed: Dict[str, Any]) -> bool:
        """Return True if all recomputed keys match the stored result."""
        for key, val in recomputed.items():
            if key not in stored:
                return False
            if stored[key] != val:
                return False
        return True
