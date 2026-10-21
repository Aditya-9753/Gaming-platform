"""Wallet API router — GET /wallet, GET /wallet/transactions, POST /wallet/daily-claim, POST /wallet/promo."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PermissionCode
from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.exceptions import BadRequestException, NotFoundException
from app.middleware.rate_limit import rate_limit_dependency
from app.repositories.wallet_repo import WalletRepository
from app.schemas.wallet import (
    DailyClaimResponse,
    WalletResponse,
    WalletTransactionResponse,
)
from app.services.daily_credit_service import DailyCreditService
from app.services.wallet_service import WalletService
from app.utils.pagination import PaginationParams, PagedResponse, make_page

router = APIRouter(prefix="/wallet", tags=["Wallet"])


# ---------------------------------------------------------------------------
# GET /wallet — current user's balance
# ---------------------------------------------------------------------------


@router.get("", response_model=WalletResponse)
async def get_my_wallet(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.WALLET_READ)),
    db: AsyncSession = Depends(get_db),
) -> WalletResponse:
    """Return the authenticated user's current virtual-credit balance."""
    repo = WalletRepository(db)
    wallet = await repo.get_by_user_id(current_user.id)
    if not wallet:
        raise NotFoundException("Wallet not found — please contact support")
    return WalletResponse.from_orm(wallet)


# ---------------------------------------------------------------------------
# GET /wallet/transactions — paginated ledger history
# ---------------------------------------------------------------------------


@router.get("/transactions", response_model=PagedResponse[WalletTransactionResponse])
async def get_transactions(
    type: Optional[str] = Query(None, description="Filter by transaction type (BET, WIN, …)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.WALLET_READ)),
    db: AsyncSession = Depends(get_db),
) -> PagedResponse[WalletTransactionResponse]:
    """Return the paginated, filterable transaction history for the current user."""
    repo = WalletRepository(db)
    wallet = await repo.get_by_user_id(current_user.id)
    if not wallet:
        raise NotFoundException("Wallet not found")

    params = PaginationParams(page=page, page_size=page_size)
    rows, total = await repo.get_transactions(
        wallet.id,
        tx_type=type.upper() if type else None,
        limit=params.limit,
        offset=params.offset,
    )
    items = [WalletTransactionResponse.model_validate(r) for r in rows]
    return make_page(items, total, params)


# ---------------------------------------------------------------------------
# POST /wallet/daily-claim — faucet
# ---------------------------------------------------------------------------


@router.post("/daily-claim", response_model=DailyClaimResponse, status_code=200)
async def daily_claim(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.WALLET_CLAIM)),
    db: AsyncSession = Depends(get_db),
) -> DailyClaimResponse:
    """Claim the daily virtual-credit bonus (once per 24 hours)."""
    import uuid

    idempotency_key = f"daily-claim-{current_user.id}-{request.headers.get('Idempotency-Key', str(uuid.uuid4()))}"

    svc = WalletService(db)
    tx = await svc.daily_claim(current_user.id, idempotency_key)

    daily_svc = DailyCreditService(db)
    cooldown = await daily_svc.get_cooldown_remaining(current_user.id)

    return DailyClaimResponse(
        message="Daily credits claimed successfully!",
        transaction=WalletTransactionResponse.model_validate(tx),
        new_balance=tx.balance_after,
        cooldown_remaining_seconds=cooldown,
    )


# ---------------------------------------------------------------------------
# POST /wallet/promo — redeem a bonus promo code
# ---------------------------------------------------------------------------


class PromoRedeemRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=32)


@router.post(
    "/promo",
    dependencies=[Depends(rate_limit_dependency("wallet:promo", max_requests=10, window_seconds=600))],
)
async def redeem_promo(
    payload: PromoRedeemRequest,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.WALLET_CLAIM)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add a promo code's bonus to the wallet (each code once per player)."""
    from app.services import promo_service

    result = await promo_service.redeem(db, current_user.id, payload.code)
    await db.commit()
    return result
