"""Partner payout methods, withdrawal requests and the finance queue (PRD §8).

Status flow: PENDING -> UNDER_REVIEW -> APPROVED -> PROCESSING -> COMPLETED,
or REJECTED / CANCELLED / FAILED. Money: request = AVAILABLE -> RESERVED
(WITHDRAWAL_RESERVE); paid = RESERVED out (WITHDRAWAL_PAID); reject / cancel /
fail = RESERVED -> AVAILABLE (WITHDRAWAL_RELEASE).
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate import ledger
from app.affiliate import settings as aff_settings
from app.affiliate.common import Actor, SYSTEM, audit, notify
from app.affiliate.constants import (
    OPEN_WITHDRAWAL_STATUSES,
    WITHDRAWAL_TRANSITIONS,
    ZERO,
    Bucket,
    LedgerType,
    MethodType,
    PartnerStatus,
    RecordStatus,
    WalletStatus,
    WithdrawalSource,
    WithdrawalStatus,
)
from app.affiliate.util import aware, mask_identifier, money, utcnow
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.models.affiliate import (
    AffAutoWithdrawalSetting,
    AffPartner,
    AffSettlementPeriod,
    AffWithdrawal,
    AffWithdrawalMethod,
    AffWithdrawalStatusHistory,
)
from app.security.field_crypto import decrypt_json, encrypt_json

_IDENTIFIER_RULES = {
    MethodType.EWALLET_EMAIL: ("email", lambda v: "@" in v and "." in v.split("@")[-1] and len(v) <= 254),
    MethodType.USDT_TRC20: ("TRC20 address", lambda v: v.startswith("T") and len(v) == 34 and v.isalnum()),
    MethodType.UPI: ("UPI id", lambda v: "@" in v and 3 <= len(v) <= 100),
    MethodType.BANK: ("account number / IBAN", lambda v: 6 <= len(v.replace(" ", "")) <= 40),
    MethodType.OTHER: ("payout identifier", lambda v: 3 <= len(v) <= 120),
}


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------


def _row_key(method_id: int) -> str:
    return f"aff-method:{method_id}"


def method_identifier(method: AffWithdrawalMethod) -> str:
    return decrypt_json(method.account_identifier_encrypted, _row_key(method.id))["identifier"]


async def add_method(db: AsyncSession, actor: Actor, partner: AffPartner, data: Dict[str, Any]) -> AffWithdrawalMethod:
    method_type = MethodType(data["type"])
    identifier = str(data["account_identifier"]).strip()
    what, valid = _IDENTIFIER_RULES[method_type]
    if not valid(identifier):
        raise BadRequestException(f"Enter a valid {what}")
    hours = int(await aff_settings.get(db, "method_cooldown_hours"))
    count = (await db.execute(
        select(func.count()).select_from(AffWithdrawalMethod).where(
            AffWithdrawalMethod.partner_id == partner.id, AffWithdrawalMethod.status == RecordStatus.ACTIVE)
    )).scalar_one()
    if count >= 10:
        raise BadRequestException("At most 10 payout methods")
    method = AffWithdrawalMethod(
        partner_id=partner.id, type=method_type, label=(data.get("label") or method_type.value.replace("_", " ").title())[:60],
        account_name=(data.get("account_name") or None), account_identifier_encrypted="pending",
        account_identifier_masked=mask_identifier(identifier), is_default=count == 0 or bool(data.get("is_default")),
        usable_after=utcnow() + timedelta(hours=hours),
    )
    db.add(method)
    await db.flush()
    method.account_identifier_encrypted = encrypt_json({"identifier": identifier}, _row_key(method.id))
    if data.get("metadata"):
        method.metadata_encrypted = encrypt_json(dict(data["metadata"]), _row_key(method.id) + ":meta")
    if method.is_default:
        await _single_default(db, partner.id, method.id)
    await audit(db, actor, "AFF_METHOD_ADDED", "aff_withdrawal_method", method.id,
                new={"partner_id": partner.id, "type": method_type.value, "masked": method.account_identifier_masked})
    await notify(db, partner.user_id, "Payout method added",
                 f"{method.label} ({method.account_identifier_masked}) can be used for payouts after {hours} hours. "
                 "If this wasn't you, contact support immediately.", "SECURITY")
    return method


async def _single_default(db: AsyncSession, partner_id: int, method_id: int) -> None:
    for other in (await db.execute(select(AffWithdrawalMethod).where(AffWithdrawalMethod.partner_id == partner_id))).scalars():
        other.is_default = other.id == method_id
    await db.flush()


async def update_method(db: AsyncSession, actor: Actor, partner: AffPartner, method_id: int, data: Dict[str, Any]) -> AffWithdrawalMethod:
    method = await _method(db, partner.id, method_id)
    old = {"label": method.label, "masked": method.account_identifier_masked, "status": method.status.value}
    if data.get("label"):
        method.label = data["label"][:60]
    if data.get("account_identifier"):
        identifier = str(data["account_identifier"]).strip()
        what, valid = _IDENTIFIER_RULES[MethodType(method.type)]
        if not valid(identifier):
            raise BadRequestException(f"Enter a valid {what}")
        method.account_identifier_encrypted = encrypt_json({"identifier": identifier}, _row_key(method.id))
        method.account_identifier_masked = mask_identifier(identifier)
        hours = int(await aff_settings.get(db, "method_cooldown_hours"))
        method.usable_after = utcnow() + timedelta(hours=hours)  # changed destination: cool down again
        method.verified = False
    if data.get("is_default"):
        await _single_default(db, partner.id, method.id)
    if data.get("status") == RecordStatus.ARCHIVED.value:
        open_wd = (await db.execute(select(AffWithdrawal.id).where(
            AffWithdrawal.withdrawal_method_id == method.id, AffWithdrawal.status.in_(OPEN_WITHDRAWAL_STATUSES)).limit(1))).first()
        if open_wd:
            raise ConflictException("This method has an open withdrawal")
        method.status = RecordStatus.ARCHIVED
        method.is_default = False
    await db.flush()
    await audit(db, actor, "AFF_METHOD_UPDATED", "aff_withdrawal_method", method.id, old=old,
                new={"label": method.label, "masked": method.account_identifier_masked, "status": method.status.value})
    return method


async def _method(db: AsyncSession, partner_id: int, method_id: int) -> AffWithdrawalMethod:
    method = await db.get(AffWithdrawalMethod, method_id)
    if method is None or method.partner_id != partner_id:
        raise NotFoundException("Payout method not found")
    return method


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


async def _history(db: AsyncSession, wd: AffWithdrawal, new: WithdrawalStatus, actor: Actor, note: Optional[str] = None) -> None:
    old = WithdrawalStatus(wd.status)
    if new not in WITHDRAWAL_TRANSITIONS.get(old, set()):
        raise ConflictException(f"Cannot move a withdrawal from {old.value} to {new.value}")
    db.add(AffWithdrawalStatusHistory(withdrawal_id=wd.id, from_status=old.value, to_status=new.value,
                                      changed_by=actor.user_id, note=(note or "")[:255] or None))
    wd.status = new
    await db.flush()


async def _check_can_withdraw(db: AsyncSession, partner: AffPartner, amount: Decimal, method: AffWithdrawalMethod) -> Decimal:
    if partner.status != PartnerStatus.ACTIVE:
        raise ForbiddenException("Your partner account is not active")
    if partner.payout_frozen:
        raise ForbiddenException("Payouts are frozen on this account; contact your manager")
    if method.status != RecordStatus.ACTIVE:
        raise BadRequestException("This payout method is archived")
    usable = aware(method.usable_after)
    if usable > utcnow():
        raise BadRequestException(f"New payout methods can be used from {usable:%d %b %Y %H:%M} UTC (security cool-down)")
    minimum = await aff_settings.get_decimal(db, "min_payout")
    if amount < minimum:
        raise BadRequestException(f"The minimum payout is {minimum:.2f} $")
    open_wd = (await db.execute(select(AffWithdrawal.id).where(
        AffWithdrawal.partner_id == partner.id, AffWithdrawal.status.in_(OPEN_WITHDRAWAL_STATUSES)).limit(1))).first()
    if open_wd:
        raise ConflictException("You already have a withdrawal in progress")
    fee = await aff_settings.get_decimal(db, "withdrawal_fee")
    if amount - fee <= ZERO:
        raise BadRequestException("The amount does not cover the withdrawal fee")
    return money(fee)


async def request_withdrawal(
    db: AsyncSession, actor: Actor, partner: AffPartner, *, amount: Any, method_id: Optional[int], idempotency_key: str,
    source: WithdrawalSource = WithdrawalSource.MANUAL,
) -> AffWithdrawal:
    amount = money(amount)
    if amount <= ZERO:
        raise BadRequestException("Enter an amount")
    key = f"{partner.id}:{idempotency_key}"
    existing = (await db.execute(select(AffWithdrawal).where(AffWithdrawal.idempotency_key == key))).scalar_one_or_none()
    if existing is not None:
        return existing
    if method_id is None:
        method = (await db.execute(select(AffWithdrawalMethod).where(
            AffWithdrawalMethod.partner_id == partner.id, AffWithdrawalMethod.is_default.is_(True),
            AffWithdrawalMethod.status == RecordStatus.ACTIVE))).scalar_one_or_none()
        if method is None:
            raise BadRequestException("Add a payout method first")
    else:
        method = await _method(db, partner.id, method_id)
    fee = await _check_can_withdraw(db, partner, amount, method)
    wallet = await ledger.lock_wallet(db, partner.id)
    if wallet.status != WalletStatus.ACTIVE:
        raise ForbiddenException("Your wallet is frozen")
    if money(wallet.available_balance) < amount:
        raise BadRequestException(f"Available balance is {money(wallet.available_balance):.2f} $")
    wd = AffWithdrawal(
        partner_id=partner.id, wallet_id=wallet.id, withdrawal_method_id=method.id, source=source, amount=amount, fee=fee,
        net_amount=amount - fee, currency="USD", status=WithdrawalStatus.PENDING, idempotency_key=key,
        destination_masked=method.account_identifier_masked, requested_at=utcnow(),
    )
    db.add(wd)
    await db.flush()
    db.add(AffWithdrawalStatusHistory(withdrawal_id=wd.id, from_status=None, to_status=WithdrawalStatus.PENDING.value,
                                      changed_by=actor.user_id, note=f"{source.value} request"))
    await ledger.move(db, wallet, entry_type=LedgerType.WITHDRAWAL_RESERVE, source=Bucket.AVAILABLE, target=Bucket.RESERVED,
                      amount=amount, key=f"wd:{wd.id}:reserve", reference_type="withdrawal", reference_id=wd.id,
                      description=f"Withdrawal #{wd.id} reserved", created_by=actor.user_id)
    await audit(db, actor, "AFF_WITHDRAWAL_REQUESTED", "aff_withdrawal", wd.id,
                new={"partner_id": partner.id, "amount": str(amount), "source": source.value, "method": method.account_identifier_masked})
    return wd


async def _lock(db: AsyncSession, withdrawal_id: int) -> AffWithdrawal:
    wd = (await db.execute(select(AffWithdrawal).where(AffWithdrawal.id == withdrawal_id).with_for_update())).scalar_one_or_none()
    if wd is None:
        raise NotFoundException("Withdrawal not found")
    return wd


async def _release(db: AsyncSession, wd: AffWithdrawal, actor: Actor, why: str) -> None:
    wallet = await ledger.lock_wallet(db, wd.partner_id)
    await ledger.move(db, wallet, entry_type=LedgerType.WITHDRAWAL_RELEASE, source=Bucket.RESERVED, target=Bucket.AVAILABLE,
                      amount=money(wd.amount), key=f"wd:{wd.id}:release", reference_type="withdrawal", reference_id=wd.id,
                      description=f"Withdrawal #{wd.id} {why}", created_by=actor.user_id)


async def cancel(db: AsyncSession, actor: Actor, partner: AffPartner, withdrawal_id: int) -> AffWithdrawal:
    wd = await _lock(db, withdrawal_id)
    if wd.partner_id != partner.id:
        raise NotFoundException("Withdrawal not found")
    if wd.status != WithdrawalStatus.PENDING:
        raise ConflictException("Only a pending withdrawal can be cancelled")
    await _history(db, wd, WithdrawalStatus.CANCELLED, actor, "Cancelled by partner")
    await _release(db, wd, actor, "cancelled")
    wd.processed_at = utcnow()
    await audit(db, actor, "AFF_WITHDRAWAL_CANCELLED", "aff_withdrawal", wd.id)
    return wd


async def transition(
    db: AsyncSession, actor: Actor, withdrawal_id: int, to: WithdrawalStatus, *, note: Optional[str] = None,
    external_reference: Optional[str] = None,
) -> AffWithdrawal:
    """Finance actions: UNDER_REVIEW, APPROVED, PROCESSING, COMPLETED (mark paid), REJECTED, FAILED."""
    wd = await _lock(db, withdrawal_id)
    partner = await db.get(AffPartner, wd.partner_id)
    if to in (WithdrawalStatus.REJECTED, WithdrawalStatus.FAILED) and not (note or "").strip():
        raise BadRequestException("Give a reason")
    if to == WithdrawalStatus.COMPLETED and not (external_reference or "").strip():
        raise BadRequestException("Enter the payment reference")
    if to in (WithdrawalStatus.APPROVED, WithdrawalStatus.COMPLETED) and partner is not None and partner.payout_frozen:
        raise ForbiddenException("Payouts are frozen for this partner")
    old = wd.status
    await _history(db, wd, to, actor, note)
    now = utcnow()
    if to == WithdrawalStatus.APPROVED:
        wd.approved_at, wd.approved_by = now, actor.user_id
    elif to == WithdrawalStatus.COMPLETED:
        if wd.approved_at is None:
            wd.approved_at, wd.approved_by = now, actor.user_id
        wd.processed_at = now
        wd.external_payment_reference = external_reference.strip()[:120]
        wallet = await ledger.lock_wallet(db, wd.partner_id)
        await ledger.post(db, wallet, entry_type=LedgerType.WITHDRAWAL_PAID, bucket=Bucket.RESERVED, delta=-money(wd.amount),
                          key=f"wd:{wd.id}:paid", reference_type="withdrawal", reference_id=wd.id,
                          description=f"Withdrawal #{wd.id} paid ({wd.external_payment_reference})", created_by=actor.user_id)
    elif to in (WithdrawalStatus.REJECTED, WithdrawalStatus.FAILED):
        wd.rejected_at = now
        wd.processed_at = now
        wd.rejection_reason = (note or "")[:255]
        await _release(db, wd, actor, to.value.lower())
    await audit(db, actor, f"AFF_WITHDRAWAL_{to.value}", "aff_withdrawal", wd.id, old={"status": old.value},
                new={"status": to.value, "note": note, "reference": external_reference})
    if partner is not None:
        messages = {
            WithdrawalStatus.APPROVED: ("Withdrawal approved", f"Your withdrawal of {money(wd.amount):.2f} $ was approved."),
            WithdrawalStatus.COMPLETED: ("Withdrawal paid", f"{money(wd.net_amount):.2f} $ was sent to {wd.destination_masked}."),
            WithdrawalStatus.REJECTED: ("Withdrawal rejected", f"Your withdrawal of {money(wd.amount):.2f} $ was rejected: {note}. The amount is back in your balance."),
            WithdrawalStatus.FAILED: ("Withdrawal failed", f"Your withdrawal of {money(wd.amount):.2f} $ failed: {note}. The amount is back in your balance."),
        }
        if to in messages:
            await notify(db, partner.user_id, *messages[to])
    return wd


async def history(db: AsyncSession, withdrawal_id: int) -> List[AffWithdrawalStatusHistory]:
    return list((await db.execute(select(AffWithdrawalStatusHistory).where(
        AffWithdrawalStatusHistory.withdrawal_id == withdrawal_id).order_by(AffWithdrawalStatusHistory.id))).scalars().all())


# ---------------------------------------------------------------------------
# Auto-withdrawal
# ---------------------------------------------------------------------------


async def get_auto(db: AsyncSession, partner_id: int) -> AffAutoWithdrawalSetting:
    row = await db.get(AffAutoWithdrawalSetting, partner_id)
    if row is None:
        row = AffAutoWithdrawalSetting(partner_id=partner_id, enabled=False, min_amount=await aff_settings.get_decimal(db, "min_payout"))
    return row


async def set_auto(db: AsyncSession, actor: Actor, partner: AffPartner, enabled: bool, method_id: Optional[int],
                   min_amount: Optional[Any]) -> AffAutoWithdrawalSetting:
    row = await db.get(AffAutoWithdrawalSetting, partner.id)
    old = None if row is None else {"enabled": row.enabled, "method_id": row.withdrawal_method_id, "min_amount": str(row.min_amount)}
    minimum = await aff_settings.get_decimal(db, "min_payout")
    threshold = money(min_amount) if min_amount not in (None, "") else minimum
    if threshold < minimum:
        raise BadRequestException(f"The minimum payout is {minimum:.2f} $")
    if enabled:
        if method_id is None:
            raise BadRequestException("Choose the payout method for auto-withdrawals")
        method = await _method(db, partner.id, method_id)
        if method.status != RecordStatus.ACTIVE:
            raise BadRequestException("This payout method is archived")
    if row is None:
        row = AffAutoWithdrawalSetting(partner_id=partner.id)
        db.add(row)
    row.enabled = enabled
    row.withdrawal_method_id = method_id
    row.min_amount = threshold
    await db.flush()
    await audit(db, actor, "AFF_AUTO_WITHDRAWAL", "aff_partner", partner.id, old=old,
                new={"enabled": enabled, "method_id": method_id, "min_amount": str(threshold)})
    return row


async def run_auto_withdrawals(db: AsyncSession, period: AffSettlementPeriod) -> int:
    """At period close: one AUTO withdrawal of the full available amount per eligible partner."""
    created = 0
    for setting in (await db.execute(select(AffAutoWithdrawalSetting).where(AffAutoWithdrawalSetting.enabled.is_(True)))).scalars().all():
        partner = await db.get(AffPartner, setting.partner_id)
        wallet = await ledger.get_wallet(db, setting.partner_id)
        available = money(wallet.available_balance).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        if partner is None or available < money(setting.min_amount) or setting.withdrawal_method_id is None:
            continue
        try:
            async with db.begin_nested():
                await request_withdrawal(db, SYSTEM, partner, amount=available, method_id=setting.withdrawal_method_id,
                                         idempotency_key=f"auto:{period.id}:{int(utcnow().timestamp())}", source=WithdrawalSource.AUTO)
            created += 1
        except Exception as exc:  # frozen, cool-down, open request: skip, tell the partner why
            await notify(db, partner.user_id, "Auto-withdrawal skipped", f"No automatic payout this period: {getattr(exc, 'message', exc)}")
    return created


# ---------------------------------------------------------------------------
# Finance export
# ---------------------------------------------------------------------------


async def export_csv(db: AsyncSession, actor: Actor, status: WithdrawalStatus) -> str:
    rows = (await db.execute(
        select(AffWithdrawal, AffWithdrawalMethod, AffPartner)
        .join(AffWithdrawalMethod, AffWithdrawalMethod.id == AffWithdrawal.withdrawal_method_id)
        .join(AffPartner, AffPartner.id == AffWithdrawal.partner_id)
        .where(AffWithdrawal.status == status).order_by(AffWithdrawal.requested_at)
    )).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["withdrawal_id", "partner_code", "amount_usd", "fee_usd", "net_usd", "method", "account_name", "destination", "requested_at"])
    for wd, method, partner in rows:
        writer.writerow([wd.id, partner.partner_code, f"{money(wd.amount):.2f}", f"{money(wd.fee):.2f}", f"{money(wd.net_amount):.2f}",
                         MethodType(method.type).value, method.account_name or "", method_identifier(method), wd.requested_at.isoformat()])
    await audit(db, actor, "AFF_WITHDRAWAL_EXPORT", "aff_withdrawal", None, new={"status": status.value, "rows": len(rows)})
    return out.getvalue()
