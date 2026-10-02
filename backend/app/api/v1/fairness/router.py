"""Provably-fair verification API endpoints.

GET /rounds/{round_id}/commitment  — public seed hash for any round
GET /rounds/{round_id}/verify      — full verification (settled rounds only)

Security rules enforced:
- Active / in-progress rounds: only server_seed_hash is returned, never the seed.
- Seed is exposed only when round.status == COMPLETED.
- No auth required — provably-fair verification must be publicly accessible
  so any observer (not just the player) can audit round outcomes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.fairness import RoundCommitmentResponse, RoundVerifyResponse
from app.services.fairness_service import FairnessService

router = APIRouter(prefix="/rounds", tags=["Provably Fair"])


@router.get("/{round_id}/commitment", response_model=RoundCommitmentResponse)
async def get_round_commitment(
    round_id: str,
    db: AsyncSession = Depends(get_db),
) -> RoundCommitmentResponse:
    """Return the server-seed commitment for a round.

    For **active** rounds: only ``server_seed_hash`` is returned.
    ``server_seed`` is ``null`` — it is NEVER exposed until after settlement.

    For **settled** rounds: both the hash and the seed are returned so players
    can verify independently.
    """
    svc = FairnessService(db)
    data = await svc.get_round_commitment(round_id)
    return RoundCommitmentResponse(**data)


@router.get("/{round_id}/verify", response_model=RoundVerifyResponse)
async def verify_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
) -> RoundVerifyResponse:
    """Provably-fair verification for a completed round.

    Returns:
    - ``server_seed_hash``: the pre-game public commitment.
    - ``server_seed``: revealed after settlement.
    - ``client_seed`` + ``nonce``: the derivation inputs.
    - ``recomputed_result``: outcome derived from seeds (anyone can reproduce).
    - ``hash_valid``: SHA-256(server_seed) == server_seed_hash.
    - ``result_matches``: recomputed outcome == stored outcome.

    Raises **403** if the round is not yet settled (active round seed protection).
    Raises **404** if the round does not exist.
    """
    svc = FairnessService(db)
    data = await svc.verify_round(round_id)
    return RoundVerifyResponse(**data)
