"""Player payments API (deposit, UTR, payout accounts, withdrawals) and the provider webhook."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PermissionCode
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.payment import Deposit, PaymentAccount, Withdrawal
from app.schemas.payment import (
    BeneficiaryCreate,
    DepositCreate,
    PinSet,
    UtrSubmit,
    WithdrawalCreate,
    beneficiary_out,
    deposit_out,
    withdrawal_out,
)
from app.services import platform_settings
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])

_deposit_user = require_permission(PermissionCode.PAYMENT_DEPOSIT)
_withdraw_user = require_permission(PermissionCode.PAYMENT_WITHDRAW)


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _idem(key: Optional[str]) -> str:
    key = (key or "").strip()
    if not 8 <= len(key) <= 100:
        raise BadRequestException("Idempotency-Key header (8-100 chars) is required")
    return key


async def _deposit_view(db: AsyncSession, dep: Deposit, with_qr: bool = False) -> Dict[str, Any]:
    account = await db.get(PaymentAccount, dep.payment_account_id)
    return deposit_out(dep, account, with_qr=with_qr)


async def _page(db: AsyncSession, model, user_id: str, page: int, page_size: int):
    total = (await db.execute(select(func.count(model.id)).where(model.user_id == user_id))).scalar_one()
    rows = (await db.execute(
        select(model).where(model.user_id == user_id).order_by(model.created_at.desc())
        .limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()
    return rows, int(total)


@router.get("/config")
async def payment_config(
    current_user: CurrentUser = Depends(_deposit_user), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    s = await platform_settings.get_all(db)
    return {
        "enabled": s["payments_enabled"],
        "deposit_min_paise": s["deposit_min_paise"],
        "deposit_max_paise": s["deposit_max_paise"],
        "deposit_expiry_minutes": s["deposit_expiry_minutes"],
        "unique_paise": s["deposit_unique_paise"],
    }


# ------------------------------------------------------------------ deposits


@router.post("/deposits", status_code=201)
async def create_deposit(
    body: DepositCreate,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: CurrentUser = Depends(_deposit_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    dep = await PaymentService(db).create_deposit(current_user.id, body.amount_paise, _idem(idempotency_key), _ip(request))
    return await _deposit_view(db, dep, with_qr=True)


@router.get("/deposits")
async def my_deposits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(_deposit_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await PaymentService(db).expire_stale_deposits()
    rows, total = await _page(db, Deposit, current_user.id, page, page_size)
    return {"items": [deposit_out(d) for d in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/deposits/{deposit_id}")
async def my_deposit(
    deposit_id: str, current_user: CurrentUser = Depends(_deposit_user), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Also the "check status" call: expires overdue intents and re-tries matching bank credits."""
    svc = PaymentService(db)
    dep = await svc.refresh_deposit(await svc.get_user_deposit(current_user.id, deposit_id))
    return await _deposit_view(db, dep, with_qr=True)


@router.post("/deposits/{deposit_id}/utr")
async def submit_utr(
    deposit_id: str, body: UtrSubmit, request: Request,
    current_user: CurrentUser = Depends(_deposit_user), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    dep = await PaymentService(db).submit_utr(current_user.id, deposit_id, body.utr, _ip(request))
    return await _deposit_view(db, dep, with_qr=True)


@router.post("/deposits/{deposit_id}/cancel")
async def cancel_deposit(
    deposit_id: str, request: Request,
    current_user: CurrentUser = Depends(_deposit_user), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    dep = await PaymentService(db).cancel_deposit(current_user.id, deposit_id, _ip(request))
    return deposit_out(dep)


# ------------------------------------------------------------------ PIN + payout accounts


@router.post("/pin", status_code=204)
async def set_pin(
    body: PinSet, current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db)
) -> None:
    await PaymentService(db).set_pin(current_user.id, body.pin, body.password)


@router.get("/beneficiaries")
async def list_beneficiaries(
    current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    return [beneficiary_out(b) for b in await PaymentService(db).list_beneficiaries(current_user.id)]


@router.post("/beneficiaries", status_code=201)
async def add_beneficiary(
    body: BeneficiaryCreate, current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    data = body.model_dump(exclude={"pin"})
    return beneficiary_out(await PaymentService(db).add_beneficiary(current_user.id, data, body.pin))


@router.delete("/beneficiaries/{beneficiary_id}", status_code=204)
async def remove_beneficiary(
    beneficiary_id: str, current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db)
) -> None:
    await PaymentService(db).remove_beneficiary(current_user.id, beneficiary_id)


# ------------------------------------------------------------------ withdrawals


@router.get("/withdrawals/eligibility")
async def withdrawal_eligibility(
    current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await PaymentService(db).eligibility(current_user.id)


@router.post("/withdrawals", status_code=201)
async def request_withdrawal(
    body: WithdrawalCreate,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: CurrentUser = Depends(_withdraw_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    wd = await PaymentService(db).request_withdrawal(
        current_user.id, body.amount_paise, body.beneficiary_id, body.pin, _idem(idempotency_key), _ip(request)
    )
    return withdrawal_out(wd)


@router.get("/withdrawals")
async def my_withdrawals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(_withdraw_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    rows, total = await _page(db, Withdrawal, current_user.id, page, page_size)
    return {"items": [withdrawal_out(w) for w in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/withdrawals/{withdrawal_id}")
async def my_withdrawal(
    withdrawal_id: str, current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    wd = await db.get(Withdrawal, withdrawal_id)
    if wd is None or wd.user_id != current_user.id:
        raise NotFoundException("Withdrawal not found")
    return withdrawal_out(wd)


@router.post("/withdrawals/{withdrawal_id}/cancel")
async def cancel_withdrawal(
    withdrawal_id: str, request: Request,
    current_user: CurrentUser = Depends(_withdraw_user), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return withdrawal_out(await PaymentService(db).cancel_withdrawal(current_user.id, withdrawal_id, _ip(request)))


# ------------------------------------------------------------------ provider webhook (no user JWT)


@router.post("/webhook/{provider}")
async def provider_webhook(provider: str, request: Request, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Signed bank/provider credit notifications.

    Headers: ``X-Webhook-Timestamp`` (unix seconds) and ``X-Webhook-Signature`` =
    hex HMAC-SHA256(secret, f"{timestamp}." + raw body). Body (JSON):
    ``{"event_id", "type": "payment.credit"|"payment.failed"|"payment.reversed",
    "utr", "amount_paise", "reference", "remark", "account_vpa", "payer_name", "payer_vpa", "reason"}``.
    """
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    return await PaymentService(db).handle_webhook(provider, body, headers, _ip(request))
