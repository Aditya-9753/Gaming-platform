"""Staff payments API.

Visibility: the super admin, auditors and support read everything; an admin
reads (and acts on) deposits paid into their *own* QR collection accounts,
and sees the withdrawal queue with masked payout details. Only the super
admin completes or rejects withdrawals. Every money-moving action needs a
fresh step-up code (``X-Step-Up-Token``) and is written to the audit log.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PermissionCode
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.payment import BankCredit, Deposit, PaymentAccount, PaymentStatusHistory, Withdrawal
from app.models.user import User
from app.schemas.payment import (
    AccountCreate,
    AccountReview,
    AccountUpdate,
    CreditAssign,
    DepositConfirm,
    ReasonBody,
    StatementImport,
    StepUpVerify,
    WithdrawalComplete,
    WithdrawalInitiate,
    WithdrawalReject,
    account_out,
    credit_out,
    deposit_out,
    history_out,
    withdrawal_out,
)
from app.services import platform_settings, step_up
from app.services.payment_service import (
    MATCHABLE_DEPOSIT_STATES,
    OPEN_WITHDRAWAL_STATES,
    Actor,
    PaymentService,
    utcnow,
)

router = APIRouter(prefix="/admin/payments", tags=["Admin Payments"])

_read = require_permission(PermissionCode.PAYMENT_READ)
_manage = require_permission(PermissionCode.PAYMENT_MANAGE)


def _actor(user: CurrentUser, request: Request, mfa: Optional[str] = None) -> Actor:
    return Actor(id=user.id, role=user.role.upper(), kind="ADMIN",
                 ip=request.client.host if request.client else None, mfa=mfa)


def _stepped(user: CurrentUser, request: Request, token: Optional[str]) -> Actor:
    return _actor(user, request, step_up.require(user, token))


async def _names(db: AsyncSession, ids: Iterable[Optional[str]]) -> Dict[str, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(wanted)))
    return dict(rows.all())


async def _account_scope(db: AsyncSession, actor: Actor) -> Optional[List[str]]:
    """None = every account; otherwise the ids this admin owns."""
    return None if actor.sees_all else await PaymentService(db).owned_account_ids(actor)


def _search_filters(model, q: str, extra: Iterable = ()):
    term = q.strip()
    like = f"%{term}%"
    user_ids = select(User.id).where(User.username.ilike(like))
    return [or_(model.id == term, model.user_id.in_(user_ids), *extra)]


# ================================================================== step-up


@router.post("/step-up/send")
async def step_up_send(current_user: CurrentUser = Depends(_read)) -> Dict[str, Any]:
    return await step_up.send_email_code(current_user._user)


@router.post("/step-up")
async def step_up_verify(body: StepUpVerify, current_user: CurrentUser = Depends(_read)) -> Dict[str, Any]:
    return await step_up.verify_and_issue(current_user._user, body.code)


# ================================================================== overview


@router.get("/summary")
async def summary(request: Request, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    actor = _actor(current_user, request)
    svc = PaymentService(db)
    await svc.expire_stale_deposits()
    scope = await _account_scope(db, actor)
    dep_filter = [] if scope is None else [Deposit.payment_account_id.in_(scope or [""])]
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    by_state = dict((await db.execute(
        select(Deposit.state, func.count(Deposit.id)).where(*dep_filter).group_by(Deposit.state)
    )).all())
    credited_today, credited_count = (await db.execute(
        select(func.coalesce(func.sum(Deposit.credited_amount_paise), 0), func.count(Deposit.id))
        .where(*dep_filter, Deposit.state == "CREDITED", Deposit.credited_at >= day_start)
    )).one()
    oldest_dep = (await db.execute(
        select(func.min(Deposit.created_at)).where(*dep_filter, Deposit.state.in_(("UTR_SUBMITTED", "MANUAL_REVIEW")))
    )).scalar_one()
    credit_filter = [] if scope is None else [BankCredit.payment_account_id.in_(scope or [""])]
    unmatched = (await db.execute(
        select(func.count(BankCredit.id)).where(*credit_filter, BankCredit.status == "UNMATCHED")
    )).scalar_one()

    wd_open, wd_open_amount, wd_oldest = (await db.execute(
        select(func.count(Withdrawal.id), func.coalesce(func.sum(Withdrawal.amount_paise), 0), func.min(Withdrawal.created_at))
        .where(Withdrawal.state.in_(OPEN_WITHDRAWAL_STATES))
    )).one()
    paid_today, paid_count = (await db.execute(
        select(func.coalesce(func.sum(Withdrawal.amount_paise), 0), func.count(Withdrawal.id))
        .where(Withdrawal.state == "COMPLETED", Withdrawal.completed_at >= day_start)
    )).one()
    per_admin = []
    if actor.is_super:
        per_admin = [
            {"admin": name, "completed_today": int(count)}
            for name, count in (await db.execute(
                select(User.username, func.count(Withdrawal.id)).join(User, User.id == Withdrawal.completed_by)
                .where(Withdrawal.completed_at >= day_start).group_by(User.username)
            )).all()
        ]
    accounts_pending = 0
    if actor.is_super:
        accounts_pending = (await db.execute(
            select(func.count(PaymentAccount.id)).where(PaymentAccount.status == "PENDING_APPROVAL")
        )).scalar_one()
    return {
        "scope": "all" if scope is None else "own_accounts",
        "is_super": actor.is_super,
        "deposits": {
            "by_state": {k: int(v) for k, v in by_state.items()},
            "needs_review": int(by_state.get("UTR_SUBMITTED", 0)) + int(by_state.get("MANUAL_REVIEW", 0)),
            "awaiting_payment": int(by_state.get("PENDING", 0)),
            "credited_today_paise": int(credited_today),
            "credited_today_count": int(credited_count),
            "oldest_review_at": oldest_dep.isoformat() if oldest_dep else None,
            "unmatched_bank_credits": int(unmatched),
        },
        "withdrawals": {
            "open_count": int(wd_open),
            "open_paise": int(wd_open_amount),
            "oldest_open_at": wd_oldest.isoformat() if wd_oldest else None,
            "paid_today_paise": int(paid_today),
            "paid_today_count": int(paid_count),
            "completed_per_admin_today": per_admin,
        },
        "accounts_pending_approval": int(accounts_pending),
    }


@router.get("/lookup")
async def lookup(
    request: Request, q: str = Query(..., min_length=3, max_length=60),
    current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Find anything by deposit id/reference, UTR (player-entered or bank), withdrawal id or payout UTR."""
    actor = _actor(current_user, request)
    scope = await _account_scope(db, actor)
    term = q.strip()
    up = term.upper().replace(" ", "")
    dep_q = select(Deposit).where(or_(Deposit.id == term, Deposit.reference == up, Deposit.user_utr == up))
    credit_q = select(BankCredit).where(or_(BankCredit.utr == up, BankCredit.id == term, BankCredit.deposit_id == term))
    if scope is not None:
        dep_q = dep_q.where(Deposit.payment_account_id.in_(scope or [""]))
        credit_q = credit_q.where(BankCredit.payment_account_id.in_(scope or [""]))
    deposits = (await db.execute(dep_q.limit(20))).scalars().all()
    credits = (await db.execute(credit_q.limit(20))).scalars().all()
    withdrawals = (await db.execute(
        select(Withdrawal).where(or_(Withdrawal.id == term, Withdrawal.payout_reference == up)).limit(20)
    )).scalars().all()
    accounts = {a.id: a for a in (await db.execute(
        select(PaymentAccount).where(PaymentAccount.id.in_({d.payment_account_id for d in deposits} or {""}))
    )).scalars().all()}
    names = await _names(db, [d.user_id for d in deposits] + [w.user_id for w in withdrawals]
                         + [a.owner_id for a in accounts.values()] + [c.created_by for c in credits])
    hv = (await platform_settings.get_all(db))["withdrawal_high_value_paise"]
    return {
        "deposits": [deposit_out(d, accounts.get(d.payment_account_id), admin=True, names=names) for d in deposits],
        "bank_credits": [credit_out(c, names=names) for c in credits],
        "withdrawals": [withdrawal_out(w, admin=True, names=names, high_value_paise=hv) for w in withdrawals],
    }


@router.get("/integrity")
async def integrity(request: Request, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    if not _actor(current_user, request).is_super and current_user.role.upper() != "AUDITOR":
        raise ForbiddenException("Super admin or auditor only")
    return await PaymentService(db).integrity_report()


# ================================================================== collection accounts (QR)


@router.get("/accounts")
async def list_accounts(request: Request, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    actor = _actor(current_user, request)
    stmt = select(PaymentAccount).order_by(PaymentAccount.created_at.desc())
    if not actor.sees_all:
        stmt = stmt.where(PaymentAccount.owner_id == actor.id)
    accounts = (await db.execute(stmt)).scalars().all()
    load = await PaymentService(db).account_load([a.id for a in accounts])
    names = await _names(db, [a.owner_id for a in accounts] + [a.approved_by for a in accounts])
    return [account_out(a, names=names, load=load.get(a.id)) for a in accounts]


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, request: Request, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    actor = _actor(current_user, request)
    account = await db.get(PaymentAccount, account_id)
    if account is None or (not actor.sees_all and account.owner_id != actor.id):
        raise NotFoundException("Collection account not found")
    names = await _names(db, [account.owner_id, account.approved_by])
    load = await PaymentService(db).account_load([account.id])
    return account_out(account, names=names, load=load.get(account.id), include_image=True)


@router.post("/accounts", status_code=201)
async def create_account(
    body: AccountCreate, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    account = await PaymentService(db).create_account(_stepped(current_user, request, x_step_up_token), body.model_dump())
    return account_out(account, names={current_user.id: current_user.username})


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: str, body: AccountUpdate, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    account = await PaymentService(db).update_account(
        _stepped(current_user, request, x_step_up_token), account_id, body.model_dump(exclude_unset=True)
    )
    return account_out(account, names=await _names(db, [account.owner_id, account.approved_by]))


@router.post("/accounts/{account_id}/review")
async def review_account(
    account_id: str, body: AccountReview, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    account = await PaymentService(db).review_account(
        _stepped(current_user, request, x_step_up_token), account_id, body.approve, body.note
    )
    return account_out(account, names=await _names(db, [account.owner_id, account.approved_by]))


# ================================================================== deposits


@router.get("/deposits")
async def list_deposits(
    request: Request,
    status: Optional[str] = Query(None, description="PENDING | SUCCESS | REJECTED | REVIEW"),
    q: Optional[str] = Query(None, max_length=60),
    account_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: CurrentUser = Depends(_read),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _actor(current_user, request)
    await PaymentService(db).expire_stale_deposits()
    filters = []
    scope = await _account_scope(db, actor)
    if scope is not None:
        filters.append(Deposit.payment_account_id.in_(scope or [""]))
    if status:
        status = status.upper()
        if status == "REVIEW":
            filters.append(Deposit.state.in_(("UTR_SUBMITTED", "MANUAL_REVIEW")))
        else:
            filters.append(Deposit.status == status)
    if account_id:
        filters.append(Deposit.payment_account_id == account_id)
    if q:
        up = q.strip().upper().replace(" ", "")
        filters += _search_filters(Deposit, q, (Deposit.reference == up, Deposit.user_utr == up))
    total = (await db.execute(select(func.count(Deposit.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Deposit).where(*filters).order_by(Deposit.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()
    accounts = {a.id: a for a in (await db.execute(
        select(PaymentAccount).where(PaymentAccount.id.in_({d.payment_account_id for d in rows} or {""}))
    )).scalars().all()}
    names = await _names(db, [d.user_id for d in rows] + [d.verified_by for d in rows] + [a.owner_id for a in accounts.values()])
    return {
        "items": [deposit_out(d, accounts.get(d.payment_account_id), admin=True, names=names) for d in rows],
        "total": int(total), "page": page, "page_size": page_size,
    }


async def _deposit_detail(db: AsyncSession, actor: Actor, deposit_id: str) -> Dict[str, Any]:
    dep = await db.get(Deposit, deposit_id)
    if dep is None:
        raise NotFoundException("Deposit not found")
    account = await db.get(PaymentAccount, dep.payment_account_id)
    if not actor.sees_all and (account is None or account.owner_id != actor.id):
        raise NotFoundException("Deposit not found")
    history = (await db.execute(
        select(PaymentStatusHistory).where(PaymentStatusHistory.entity_id == dep.id).order_by(PaymentStatusHistory.created_at)
    )).scalars().all()
    credit = await db.get(BankCredit, dep.bank_credit_id) if dep.bank_credit_id else None
    # Unmatched credits on the same account that could be this payment (same amount, or this UTR)
    candidates = (await db.execute(
        select(BankCredit).where(
            BankCredit.status == "UNMATCHED",
            or_(BankCredit.payment_account_id == dep.payment_account_id, BankCredit.payment_account_id.is_(None)),
            or_(BankCredit.amount_paise == dep.amount_paise, BankCredit.utr == (dep.user_utr or "-")),
        ).limit(10)
    )).scalars().all() if dep.state in MATCHABLE_DEPOSIT_STATES else []
    names = await _names(db, [dep.user_id, dep.verified_by, account.owner_id if account else None]
                         + [h.actor_id for h in history] + ([credit.created_by] if credit else []))
    out = deposit_out(dep, account, admin=True, names=names)
    out["history"] = history_out(list(history), names)
    out["bank_credit"] = credit_out(credit, names=names) if credit else None
    out["candidate_credits"] = [credit_out(c, names=names) for c in candidates]
    out["can_act"] = actor.is_super or (account is not None and account.owner_id == actor.id)
    return out


@router.get("/deposits/{deposit_id}")
async def get_deposit(deposit_id: str, request: Request, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await _deposit_detail(db, _actor(current_user, request), deposit_id)


@router.post("/deposits/{deposit_id}/recheck")
async def recheck_deposit(deposit_id: str, request: Request, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Status check: re-run automatic matching against bank credits on file."""
    actor = _actor(current_user, request)
    await _deposit_detail(db, actor, deposit_id)  # visibility check
    svc = PaymentService(db)
    await svc.refresh_deposit(await db.get(Deposit, deposit_id))
    return await _deposit_detail(db, actor, deposit_id)


@router.post("/deposits/{deposit_id}/confirm")
async def confirm_deposit(
    deposit_id: str, body: DepositConfirm, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _stepped(current_user, request, x_step_up_token)
    await PaymentService(db).confirm_deposit(actor, deposit_id, body.utr, body.amount_paise, body.note)
    return await _deposit_detail(db, actor, deposit_id)


@router.post("/deposits/{deposit_id}/reject")
async def reject_deposit(
    deposit_id: str, body: ReasonBody, request: Request,
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _actor(current_user, request)
    await PaymentService(db).reject_deposit(actor, deposit_id, body.reason)
    return await _deposit_detail(db, actor, deposit_id)


@router.post("/deposits/{deposit_id}/reverse")
async def reverse_deposit(
    deposit_id: str, body: ReasonBody, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _stepped(current_user, request, x_step_up_token)
    await PaymentService(db).reverse_deposit(actor, deposit_id, body.reason)
    return await _deposit_detail(db, actor, deposit_id)


# ================================================================== bank credits


@router.get("/bank-credits")
async def list_credits(
    request: Request,
    status: Optional[str] = Query("UNMATCHED"),
    account_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(_read),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _actor(current_user, request)
    filters = []
    scope = await _account_scope(db, actor)
    if scope is not None:
        filters.append(BankCredit.payment_account_id.in_(scope or [""]))
    if status and status.upper() != "ALL":
        filters.append(BankCredit.status == status.upper())
    if account_id:
        filters.append(BankCredit.payment_account_id == account_id)
    total = (await db.execute(select(func.count(BankCredit.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(BankCredit).where(*filters).order_by(BankCredit.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()
    labels = dict((await db.execute(
        select(PaymentAccount.id, PaymentAccount.label).where(PaymentAccount.id.in_({c.payment_account_id for c in rows if c.payment_account_id} or {""}))
    )).all())
    names = await _names(db, [c.created_by for c in rows])
    return {"items": [credit_out(c, names=names, labels=labels) for c in rows], "total": int(total), "page": page, "page_size": page_size}


@router.post("/bank-credits/import")
async def import_credits(
    body: StatementImport, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _stepped(current_user, request, x_step_up_token)
    return await PaymentService(db).import_credits(actor, body.account_id, [line.model_dump() for line in body.lines])


@router.post("/bank-credits/{credit_id}/assign")
async def assign_credit(
    credit_id: str, body: CreditAssign, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _stepped(current_user, request, x_step_up_token)
    await PaymentService(db).assign_credit(actor, credit_id, body.deposit_id)
    return await _deposit_detail(db, actor, body.deposit_id)


@router.post("/bank-credits/{credit_id}/ignore")
async def ignore_credit(
    credit_id: str, body: ReasonBody, request: Request,
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    credit = await PaymentService(db).ignore_credit(_actor(current_user, request), credit_id, body.reason)
    return credit_out(credit)


# ================================================================== withdrawals


@router.get("/withdrawals")
async def list_withdrawals(
    request: Request,
    status: Optional[str] = Query("PENDING", description="PENDING | COMPLETED | REJECTED | ALL"),
    q: Optional[str] = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: CurrentUser = Depends(_read),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    filters = []
    if status and status.upper() != "ALL":
        filters.append(Withdrawal.status == status.upper())
    if q:
        filters += _search_filters(Withdrawal, q, (Withdrawal.payout_reference == q.strip().upper(),))
    total = (await db.execute(select(func.count(Withdrawal.id)).where(*filters))).scalar_one()
    order = Withdrawal.created_at.asc() if (status or "").upper() == "PENDING" else Withdrawal.created_at.desc()
    rows = (await db.execute(
        select(Withdrawal).where(*filters).order_by(order).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()
    names = await _names(db, [w.user_id for w in rows] + [w.initiated_by for w in rows] + [w.completed_by for w in rows] + [w.rejected_by for w in rows])
    hv = (await platform_settings.get_all(db))["withdrawal_high_value_paise"]
    return {
        "items": [withdrawal_out(w, admin=True, names=names, high_value_paise=hv) for w in rows],
        "total": int(total), "page": page, "page_size": page_size,
    }


async def _withdrawal_detail(db: AsyncSession, withdrawal_id: str) -> Dict[str, Any]:
    wd = await db.get(Withdrawal, withdrawal_id)
    if wd is None:
        raise NotFoundException("Withdrawal not found")
    history = (await db.execute(
        select(PaymentStatusHistory).where(PaymentStatusHistory.entity_id == wd.id).order_by(PaymentStatusHistory.created_at)
    )).scalars().all()
    names = await _names(db, [wd.user_id, wd.initiated_by, wd.completed_by, wd.rejected_by] + [h.actor_id for h in history])
    hv = (await platform_settings.get_all(db))["withdrawal_high_value_paise"]
    out = withdrawal_out(wd, admin=True, names=names, high_value_paise=hv)
    out["history"] = history_out(list(history), names)
    # Player context for the reviewer
    since = utcnow() - timedelta(days=30)
    deposited, dep_count = (await db.execute(
        select(func.coalesce(func.sum(Deposit.credited_amount_paise), 0), func.count(Deposit.id))
        .where(Deposit.user_id == wd.user_id, Deposit.state == "CREDITED")
    )).one()
    withdrawn = (await db.execute(
        select(func.coalesce(func.sum(Withdrawal.amount_paise), 0)).where(Withdrawal.user_id == wd.user_id, Withdrawal.state == "COMPLETED")
    )).scalar_one()
    recent = (await db.execute(
        select(func.count(Withdrawal.id)).where(Withdrawal.user_id == wd.user_id, Withdrawal.created_at >= since)
    )).scalar_one()
    out["player"] = {
        "lifetime_deposited_paise": int(deposited), "deposit_count": int(dep_count),
        "lifetime_withdrawn_paise": int(withdrawn), "withdrawals_30d": int(recent),
        **(await PaymentService(db)._turnover(wd.user_id)),
    }
    return out


@router.get("/withdrawals/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: str, current_user: CurrentUser = Depends(_read), db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await _withdrawal_detail(db, withdrawal_id)


@router.post("/withdrawals/{withdrawal_id}/payout-details")
async def payout_details(
    withdrawal_id: str, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Unmasked bank account / UPI id for paying out (super admin, step-up, audited)."""
    return await PaymentService(db).payout_details(_stepped(current_user, request, x_step_up_token), withdrawal_id)


@router.post("/withdrawals/{withdrawal_id}/initiate")
async def initiate_withdrawal(
    withdrawal_id: str, body: WithdrawalInitiate, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    actor = _stepped(current_user, request, x_step_up_token)
    await PaymentService(db).initiate_withdrawal(actor, withdrawal_id, body.note, body.expected_version)
    return await _withdrawal_detail(db, withdrawal_id)


@router.post("/withdrawals/{withdrawal_id}/complete")
async def complete_withdrawal(
    withdrawal_id: str, body: WithdrawalComplete, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if current_user.role.upper() != "SUPERADMIN":
        raise ForbiddenException("Only the super admin can complete a withdrawal")
    actor = _stepped(current_user, request, x_step_up_token)
    await PaymentService(db).complete_withdrawal(actor, withdrawal_id, body.payout_reference, body.expected_version, body.note)
    return await _withdrawal_detail(db, withdrawal_id)


@router.post("/withdrawals/{withdrawal_id}/reject")
async def reject_withdrawal(
    withdrawal_id: str, body: WithdrawalReject, request: Request,
    x_step_up_token: Optional[str] = Header(None, alias="X-Step-Up-Token"),
    current_user: CurrentUser = Depends(_manage), db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if current_user.role.upper() != "SUPERADMIN":
        raise ForbiddenException("Only the super admin can reject a withdrawal")
    actor = _stepped(current_user, request, x_step_up_token)
    await PaymentService(db).reject_withdrawal(actor, withdrawal_id, body.reason, body.expected_version)
    return await _withdrawal_detail(db, withdrawal_id)
