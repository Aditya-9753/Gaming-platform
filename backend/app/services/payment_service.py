"""Deposits and withdrawals: state machines, ledger movements, matching, controls.

Rules (enforced here, never in a client):

* Clients never send a status. Every state change goes through
  ``_move_deposit`` / ``_move_withdrawal`` which check the transition table
  and write a ``payment_status_history`` row in the same DB transaction.
* A deposit is credited only against a ``BankCredit`` (provider webhook,
  imported bank statement line, or an admin confirming the credit in the
  bank account behind *their own* QR). A UTR typed by the player is only a
  lookup hint. ``bank_credits.utr`` and ``deposits.bank_credit_id`` are
  UNIQUE, so one bank credit can never fund two deposits.
* Withdrawals hold the money at request time (balance -> pending_withdrawal,
  WITHDRAWAL_HOLD). Only a super admin, with a fresh step-up code, completes
  (WITHDRAWAL_SETTLE + unique payout UTR) or rejects (WITHDRAWAL_RELEASE).
* Deposit / Withdrawal rows carry a version column used by SQLAlchemy as an
  optimistic lock, on top of SELECT ... FOR UPDATE.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import io
import json
import random
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import get_settings
from app.core.constants import TransactionStatus, TransactionType, UserRole
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    InsufficientBalanceException,
    NotFoundException,
    RateLimitException,
    ServiceUnavailableException,
    UnauthorizedException,
)
from app.core.logging import get_logger, get_request_id
from app.core.rate_limit import check_rate_limit, is_locked_out, record_failed_login, reset_failed_attempts
from app.core.security import hash_password, verify_password
from app.models.game import GameEntry
from app.models.payment import (
    BankCredit,
    Beneficiary,
    Deposit,
    PaymentAccount,
    PaymentStatusHistory,
    PaymentWebhookEvent,
    Withdrawal,
)
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.audit_repo import AuditRepository
from app.security import field_crypto
from app.services import platform_settings

logger = get_logger("payment_service")

# --------------------------------------------------------------------------- states

DEPOSIT_STATUS = {
    "PENDING": "PENDING",
    "UTR_SUBMITTED": "PENDING",
    "MANUAL_REVIEW": "PENDING",
    "CREDITED": "SUCCESS",
    "FAILED": "REJECTED",
    "EXPIRED": "REJECTED",
    "CANCELLED": "REJECTED",
    "REVERSED": "REJECTED",
}
DEPOSIT_TRANSITIONS: Dict[Optional[str], set] = {
    None: {"PENDING"},
    "PENDING": {"UTR_SUBMITTED", "MANUAL_REVIEW", "CREDITED", "FAILED", "EXPIRED", "CANCELLED"},
    "UTR_SUBMITTED": {"UTR_SUBMITTED", "MANUAL_REVIEW", "CREDITED", "FAILED"},
    "MANUAL_REVIEW": {"UTR_SUBMITTED", "CREDITED", "FAILED"},
    # A late payment that the bank proves arrived can still be credited
    "EXPIRED": {"UTR_SUBMITTED", "MANUAL_REVIEW", "CREDITED", "FAILED"},
    "CREDITED": {"REVERSED"},
}
OPEN_DEPOSIT_STATES = ("PENDING", "UTR_SUBMITTED", "MANUAL_REVIEW")
MATCHABLE_DEPOSIT_STATES = OPEN_DEPOSIT_STATES + ("EXPIRED",)

WITHDRAWAL_STATUS = {
    "AWAITING_APPROVAL": "PENDING",
    "PAYOUT_INITIATED": "PENDING",
    "COMPLETED": "COMPLETED",
    "REJECTED": "REJECTED",
    "CANCELLED": "REJECTED",
}
WITHDRAWAL_TRANSITIONS: Dict[Optional[str], set] = {
    None: {"AWAITING_APPROVAL"},
    "AWAITING_APPROVAL": {"PAYOUT_INITIATED", "COMPLETED", "REJECTED", "CANCELLED"},
    "PAYOUT_INITIATED": {"COMPLETED", "REJECTED"},
}
OPEN_WITHDRAWAL_STATES = ("AWAITING_APPROVAL", "PAYOUT_INITIATED")

# Roles that may read every payment; other staff only see deposits on their own QR accounts
SEE_ALL_ROLES = {UserRole.SUPERADMIN.value, UserRole.AUDITOR.value, UserRole.SUPPORT.value}

_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERENCE_RE = re.compile(r"RD[A-HJ-NP-Z2-9]{10}")
UTR_RE = re.compile(r"^[A-Z0-9]{6,40}$")
VPA_RE = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT_RE = re.compile(r"^\d{9,18}$")
PIN_RE = re.compile(r"^\d{4,6}$")
_QR_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
_WEAK_PINS = {"0000", "1111", "1234", "4321", "000000", "111111", "123456", "654321", "123123"}
MAX_QR_IMAGE_CHARS = 600_000
MAX_ACTIVE_BENEFICIARIES = 3
MAX_OPEN_DEPOSITS = 3
_UNWAGERED_STATUSES = ("REFUNDED", "VOID", "VOIDED", "CANCELLED")


@dataclass
class Actor:
    """Who is acting: a player, a staff member, the system or a payment provider."""

    id: Optional[str]
    role: str
    kind: str  # USER | ADMIN | SYSTEM | PROVIDER
    ip: Optional[str] = None
    mfa: Optional[str] = None

    @property
    def is_super(self) -> bool:
        return self.role.upper() == UserRole.SUPERADMIN.value

    @property
    def sees_all(self) -> bool:
        return self.role.upper() in SEE_ALL_ROLES


SYSTEM = Actor(id=None, role="SYSTEM", kind="SYSTEM")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_utr(value: str) -> str:
    utr = re.sub(r"[\s\-]", "", (value or "")).upper()
    if not UTR_RE.match(utr):
        raise BadRequestException("Enter a valid UTR / transaction reference (6-40 letters or digits)")
    return utr


def rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


def mask_tail(value: str, keep: int = 4) -> str:
    return f"{'•' * 4}{value[-keep:]}" if len(value) > keep else value


def mask_vpa(vpa: str) -> str:
    name, _, handle = vpa.partition("@")
    return f"{name[:2]}{'•' * max(2, len(name) - 2)}@{handle}"


def upi_link(account: PaymentAccount, amount_paise: int, reference: str, display_name: Optional[str] = None) -> str:
    """UPI intent. ``display_name`` replaces the account's payee name (players see the brand, not a person)."""
    return (
        f"upi://pay?pa={quote(account.upi_id, safe='@.')}&pn={quote(display_name or account.payee_name)}"
        f"&am={amount_paise / 100:.2f}&cu=INR&tn={reference}&tr={reference}"
    )


def qr_data_url(text: str, label: Optional[str] = None) -> Optional[str]:
    """SVG QR code as a data URL (pure Python; None if the qrcode package is missing).

    With ``label`` the brand name is drawn in a badge at the centre and as a caption
    underneath. High error correction keeps the code scannable with the badge on it.
    """
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_H
    except ImportError:  # pragma: no cover - dependency listed in requirements.txt
        return None
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, border=4)  # full quiet zone above the caption
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()  # includes the quiet-zone border
    n = len(matrix)
    cell = 10
    size = n * cell
    caption = 30 if label else 0
    path = "".join(
        f"M{x * cell},{y * cell}h{cell}v{cell}h-{cell}z"
        for y, row in enumerate(matrix) for x, dark in enumerate(row) if dark
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size + caption}" width="{size}" height="{size + caption}">',
        f'<rect width="{size}" height="{size + caption}" fill="#ffffff"/>',
        f'<path d="{path}" fill="#000000"/>',
    ]
    if label:
        name = html.escape(label[:16])
        # Centre badge sized to the text, capped so it covers well under level-H (30%) recovery
        bh = size * 0.1
        fs = bh * 0.45
        bw = min(size * 0.42, len(label[:16]) * fs * 0.62 + fs * 1.2)
        fs = min(fs, (bw - fs * 0.8) / (len(label[:16]) * 0.62))
        bx, by = (size - bw) / 2, (size - bh) / 2
        font = "font-family='Arial,Helvetica,sans-serif' font-weight='800'"
        parts += [
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{bh / 4:.1f}" fill="#ffffff" stroke="#000000" stroke-width="3"/>',
            f'<text x="{size / 2}" y="{size / 2}" {font} font-size="{fs:.1f}" text-anchor="middle" dominant-baseline="central" fill="#0b1b3f">{name}</text>',
            f'<text x="{size / 2}" y="{size + caption / 2 - 12}" {font} font-size="22" text-anchor="middle" dominant-baseline="central" fill="#0b1b3f">{name}</text>',
        ]
    parts.append("</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode("".join(parts).encode("utf-8")).decode("ascii")


async def _rate_limit(key: str, limit: int, window: int, message: str) -> None:
    if not await check_rate_limit(f"rl:pay:{key}", limit, window):
        raise RateLimitException(message)


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ================================================================ helpers

    async def _settings(self) -> Dict[str, Any]:
        return await platform_settings.get_all(self.db)

    async def _history(
        self, entity_type: str, entity_id: str, old: Optional[str], new: str, actor: Actor, reason: Optional[str]
    ) -> None:
        self.db.add(
            PaymentStatusHistory(
                id=str(uuid.uuid4()),
                entity_type=entity_type,
                entity_id=entity_id,
                from_state=old,
                to_state=new,
                actor_id=actor.id,
                actor_type=actor.kind,
                reason=(reason or None) and reason[:500],
                ip_address=actor.ip,
                request_id=(get_request_id() or None),
            )
        )

    async def _move_deposit(self, dep: Deposit, new: str, actor: Actor, reason: Optional[str] = None) -> None:
        old = dep.state if dep.state else None
        if new not in DEPOSIT_TRANSITIONS.get(old, set()):
            raise ConflictException(f"Deposit is {DEPOSIT_STATUS.get(old or '', old)} ({old}); it cannot move to {new}")
        dep.state = new
        dep.status = DEPOSIT_STATUS[new]
        await self._history("DEPOSIT", dep.id, old, new, actor, reason)

    async def _move_withdrawal(self, wd: Withdrawal, new: str, actor: Actor, reason: Optional[str] = None) -> None:
        old = wd.state if wd.state else None
        if new not in WITHDRAWAL_TRANSITIONS.get(old, set()):
            raise ConflictException(f"Withdrawal is {old}; it cannot move to {new}")
        wd.state = new
        wd.status = WITHDRAWAL_STATUS[new]
        await self._history("WITHDRAWAL", wd.id, old, new, actor, reason)

    async def _audit(self, actor: Actor, action: str, target_type: str, target_id: str, details: Dict[str, Any]) -> None:
        if actor.mfa:
            details = {**details, "mfa": actor.mfa}
        await AuditRepository(self.db).create_log(
            action=action, target_type=target_type, actor_id=actor.id, target_id=target_id,
            details=details, ip_address=actor.ip,
        )

    async def _notify(self, user_id: str, title: str, message: str, kind: str = "INFO") -> None:
        try:
            from app.services.notification_service import NotificationService

            await NotificationService(self.db).send_notification(user_id, title, message, kind)
        except Exception as exc:  # notifications must never block money movement
            logger.warning("Payment notification failed", user_id=user_id, error=str(exc))

    async def _commit(self) -> None:
        try:
            await self.db.commit()
        except StaleDataError as exc:
            await self.db.rollback()
            raise ConflictException("Someone else changed this record at the same time — refresh and try again") from exc

    async def _lock_wallet(self, wallet_id: str) -> Wallet:
        wallet = (await self.db.execute(select(Wallet).where(Wallet.id == wallet_id).with_for_update())).scalar_one_or_none()
        if wallet is None:
            raise NotFoundException("Wallet not found")
        return wallet

    def _ledger(
        self, wallet: Wallet, *, key: str, tx_type: TransactionType, amount: int, before: int,
        reference: str, description: str,
    ) -> WalletTransaction:
        tx = WalletTransaction(
            id=str(uuid.uuid4()),
            wallet_id=wallet.id,
            idempotency_key=key,
            type=tx_type.value,
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            status=TransactionStatus.COMPLETED.value,
            reference=reference,
            description=description[:255],
        )
        self.db.add(tx)
        return tx

    async def _user(self, user_id: str) -> User:
        user = await self.db.get(User, user_id)
        if user is None:
            raise NotFoundException("User not found")
        return user

    async def _lock_deposit(self, deposit_id: str) -> Deposit:
        dep = (await self.db.execute(select(Deposit).where(Deposit.id == deposit_id).with_for_update())).scalar_one_or_none()
        if dep is None:
            raise NotFoundException("Deposit not found")
        return dep

    async def _lock_withdrawal(self, withdrawal_id: str) -> Withdrawal:
        wd = (await self.db.execute(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update())).scalar_one_or_none()
        if wd is None:
            raise NotFoundException("Withdrawal not found")
        return wd

    async def owned_account_ids(self, actor: Actor) -> List[str]:
        rows = await self.db.execute(select(PaymentAccount.id).where(PaymentAccount.owner_id == actor.id))
        return [r[0] for r in rows]

    async def _ensure_account_access(self, actor: Actor, account_id: Optional[str]) -> PaymentAccount:
        account = await self.db.get(PaymentAccount, account_id) if account_id else None
        if account is None:
            raise NotFoundException("Collection account not found")
        if not actor.is_super and account.owner_id != actor.id:
            raise ForbiddenException("This belongs to another admin's QR account — only its owner or the super admin can act on it")
        return account

    # ================================================================ collection accounts

    @staticmethod
    def _validate_qr_image(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        if len(value) > MAX_QR_IMAGE_CHARS or not _QR_IMAGE_RE.match(value):
            raise BadRequestException("QR image must be a PNG, JPEG or WebP under ~400 KB")
        return value

    async def create_account(self, actor: Actor, data: Dict[str, Any]) -> PaymentAccount:
        upi_id = (data.get("upi_id") or "").strip()
        if not VPA_RE.match(upi_id):
            raise BadRequestException("Enter a valid UPI id (e.g. name@okaxis)")
        account = PaymentAccount(
            id=str(uuid.uuid4()),
            owner_id=actor.id,
            label=data["label"].strip(),
            upi_id=upi_id.lower(),
            payee_name=data["payee_name"].strip(),
            bank_name=(data.get("bank_name") or "").strip() or None,
            qr_image=self._validate_qr_image(data.get("qr_image")),
            min_amount_paise=int(data.get("min_amount_paise") or 0),
            max_amount_paise=int(data.get("max_amount_paise") or 0),
            daily_limit_paise=int(data.get("daily_limit_paise") or 0),
            # A super admin's own account is live at once; any other admin's waits for approval
            status="ACTIVE" if actor.is_super else "PENDING_APPROVAL",
            approved_by=actor.id if actor.is_super else None,
            approved_at=utcnow() if actor.is_super else None,
        )
        self.db.add(account)
        await self.db.flush()
        await self._audit(actor, "PAYMENT_ACCOUNT_CREATED", "PAYMENT_ACCOUNT", account.id,
                          {"label": account.label, "upi_id": account.upi_id, "status": account.status})
        await self._commit()
        return account

    async def update_account(self, actor: Actor, account_id: str, data: Dict[str, Any]) -> PaymentAccount:
        account = await self._ensure_account_access(actor, account_id)
        if account.status == "REJECTED":
            raise ConflictException("A rejected account cannot be edited — add a new one")
        changes: Dict[str, Any] = {}
        for field in ("label", "payee_name", "bank_name"):
            if data.get(field) is not None:
                value = data[field].strip() or None
                if field != "bank_name" and not value:
                    raise BadRequestException(f"{field} cannot be empty")
                changes[field] = value
        for field in ("min_amount_paise", "max_amount_paise", "daily_limit_paise"):
            if data.get(field) is not None:
                changes[field] = int(data[field])
        if data.get("qr_image") is not None:
            changes["qr_image"] = self._validate_qr_image(data["qr_image"])
        if data.get("upi_id") is not None:
            upi_id = data["upi_id"].strip().lower()
            if not VPA_RE.match(upi_id):
                raise BadRequestException("Enter a valid UPI id (e.g. name@okaxis)")
            changes["upi_id"] = upi_id
        # Where the money goes changed: an admin's account must be re-approved
        payee_changed = any(k in changes and changes[k] != getattr(account, k) for k in ("upi_id", "payee_name", "qr_image"))
        before = {k: getattr(account, k) for k in changes if k != "qr_image"}
        for key, value in changes.items():
            setattr(account, key, value)
        if payee_changed and not actor.is_super and account.status in ("ACTIVE", "DISABLED"):
            account.status = "PENDING_APPROVAL"
            account.approved_by = None
            account.approved_at = None
        if data.get("active") is not None:
            if data["active"]:
                if account.status == "DISABLED" and account.approved_at is not None:
                    account.status = "ACTIVE"
                elif account.status == "PENDING_APPROVAL":
                    raise ConflictException("Waiting for super admin approval")
            elif account.status == "ACTIVE":
                account.status = "DISABLED"
        await self._audit(actor, "PAYMENT_ACCOUNT_UPDATED", "PAYMENT_ACCOUNT", account.id, {
            "before": before, "after": {k: v for k, v in changes.items() if k != "qr_image"},
            "qr_image_changed": "qr_image" in changes, "status": account.status,
        })
        await self._commit()
        return account

    async def review_account(self, actor: Actor, account_id: str, approve: bool, note: Optional[str]) -> PaymentAccount:
        if not actor.is_super:
            raise ForbiddenException("Only the super admin approves collection accounts")
        account = await self.db.get(PaymentAccount, account_id)
        if account is None:
            raise NotFoundException("Collection account not found")
        if account.status != "PENDING_APPROVAL":
            raise ConflictException(f"Account is {account.status}, not waiting for approval")
        account.status = "ACTIVE" if approve else "REJECTED"
        account.review_note = (note or "").strip()[:255] or None
        if approve:
            account.approved_by, account.approved_at = actor.id, utcnow()
        await self._audit(actor, "PAYMENT_ACCOUNT_APPROVED" if approve else "PAYMENT_ACCOUNT_REJECTED",
                          "PAYMENT_ACCOUNT", account.id, {"upi_id": account.upi_id, "note": account.review_note})
        await self._commit()
        return account

    async def account_load(self, account_ids: Sequence[str]) -> Dict[str, Dict[str, int]]:
        """Received today + still-open intents per account (for routing and dashboards)."""
        if not account_ids:
            return {}
        day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        received = dict((await self.db.execute(
            select(Deposit.payment_account_id, func.coalesce(func.sum(Deposit.credited_amount_paise), 0))
            .where(Deposit.payment_account_id.in_(account_ids), Deposit.state == "CREDITED", Deposit.credited_at >= day_start)
            .group_by(Deposit.payment_account_id)
        )).all())
        open_ = dict((await self.db.execute(
            select(Deposit.payment_account_id, func.coalesce(func.sum(Deposit.amount_paise), 0))
            .where(Deposit.payment_account_id.in_(account_ids), Deposit.state.in_(OPEN_DEPOSIT_STATES))
            .group_by(Deposit.payment_account_id)
        )).all())
        return {aid: {"received_today": int(received.get(aid, 0)), "open": int(open_.get(aid, 0))} for aid in account_ids}

    async def _choose_account(self, amount: int) -> PaymentAccount:
        accounts = (await self.db.execute(select(PaymentAccount).where(PaymentAccount.status == "ACTIVE"))).scalars().all()
        load = await self.account_load([a.id for a in accounts])
        eligible = []
        for acc in accounts:
            if acc.min_amount_paise and amount < acc.min_amount_paise:
                continue
            if acc.max_amount_paise and amount > acc.max_amount_paise:
                continue
            used = load[acc.id]["received_today"] + load[acc.id]["open"]
            if acc.daily_limit_paise and used + amount > acc.daily_limit_paise:
                continue
            eligible.append((used, random.random(), acc))
        if not eligible:
            raise ServiceUnavailableException("No payment method is available for this amount right now. Try another amount or later.")
        return min(eligible, key=lambda t: (t[0], t[1]))[2]

    # ================================================================ deposits (player)

    async def expire_stale_deposits(self) -> int:
        """PENDING intents past expiry (no UTR submitted) -> EXPIRED."""
        now = utcnow()
        stale = (await self.db.execute(
            select(Deposit).where(Deposit.state == "PENDING", Deposit.expires_at < now).limit(500)
        )).scalars().all()
        for dep in stale:
            await self._move_deposit(dep, "EXPIRED", SYSTEM, "Payment window expired")
        if stale:
            await self._commit()
        return len(stale)

    async def create_deposit(self, user_id: str, amount: int, idem_key: str, ip: Optional[str]) -> Deposit:
        settings = await self._settings()
        if not settings["payments_enabled"]:
            raise ServiceUnavailableException("Deposits are paused right now")
        existing = (await self.db.execute(
            select(Deposit).where(Deposit.user_id == user_id, Deposit.idempotency_key == idem_key)
        )).scalar_one_or_none()
        if existing is not None:
            return existing
        if amount < settings["deposit_min_paise"] or amount > settings["deposit_max_paise"]:
            raise BadRequestException(
                f"Deposit must be between {rupees(settings['deposit_min_paise'])} and {rupees(settings['deposit_max_paise'])}"
            )
        await _rate_limit(f"deposit:{user_id}", 10, 3600, "Too many deposit requests — try again later")
        await self.expire_stale_deposits()
        open_count = (await self.db.execute(
            select(func.count(Deposit.id)).where(Deposit.user_id == user_id, Deposit.state == "PENDING")
        )).scalar_one()
        if open_count >= MAX_OPEN_DEPOSITS:
            raise ConflictException("You already have unpaid deposit requests — pay or cancel one first")
        wallet = (await self.db.execute(select(Wallet).where(Wallet.user_id == user_id))).scalar_one_or_none()
        if wallet is None:
            raise NotFoundException("Wallet not found")

        account = await self._choose_account(amount)
        if settings["deposit_unique_paise"]:
            amount = await self._unique_amount(account.id, amount)

        dep = Deposit(
            id=str(uuid.uuid4()),
            user_id=user_id,
            wallet_id=wallet.id,
            payment_account_id=account.id,
            amount_paise=amount,
            reference=await self._new_reference(),
            idempotency_key=idem_key,
            request_ip=ip,
            expires_at=utcnow() + timedelta(minutes=max(5, settings["deposit_expiry_minutes"])),
        )
        await self._move_deposit(dep, "PENDING", Actor(user_id, "USER", "USER", ip), "Deposit requested")
        self.db.add(dep)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = (await self.db.execute(
                select(Deposit).where(Deposit.user_id == user_id, Deposit.idempotency_key == idem_key)
            )).scalar_one_or_none()
            if existing is None:
                raise
            return existing
        logger.info("Deposit intent created", deposit_id=dep.id, user_id=user_id, amount=amount, account=account.id)
        return dep

    async def _unique_amount(self, account_id: str, amount: int) -> int:
        """amount + 1..99 paise, unused by any other open intent on this account."""
        taken = set((await self.db.execute(
            select(Deposit.amount_paise).where(
                Deposit.payment_account_id == account_id, Deposit.state.in_(MATCHABLE_DEPOSIT_STATES)
            )
        )).scalars().all())
        base = amount - amount % 100
        offsets = list(range(1, 100))
        random.shuffle(offsets)
        for off in offsets:
            if base + off not in taken:
                return base + off
        return amount

    async def _new_reference(self) -> str:
        for _ in range(10):
            ref = "RD" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(10))
            if (await self.db.execute(select(Deposit.id).where(Deposit.reference == ref))).scalar_one_or_none() is None:
                return ref
        raise ServiceUnavailableException("Could not allocate a payment reference — try again")

    async def get_user_deposit(self, user_id: str, deposit_id: str) -> Deposit:
        dep = await self.db.get(Deposit, deposit_id)
        if dep is None or dep.user_id != user_id:
            raise NotFoundException("Deposit not found")
        return dep

    async def refresh_deposit(self, dep: Deposit) -> Deposit:
        """Status check: expire if due, then try to match bank credits already on file."""
        if dep.state == "PENDING" and _aware(dep.expires_at) < utcnow():
            await self.expire_stale_deposits()
            await self.db.refresh(dep)
        if dep.state in MATCHABLE_DEPOSIT_STATES:
            await self._match_deposit(dep, SYSTEM)  # may credit, or flag a mismatch for review
            await self._commit()
            await self.db.refresh(dep)
        return dep

    async def submit_utr(self, user_id: str, deposit_id: str, raw_utr: str, ip: Optional[str]) -> Deposit:
        await _rate_limit(f"utr:{user_id}", 10, 3600, "Too many UTR submissions — try again later")
        utr = normalize_utr(raw_utr)
        dep = await self._lock_deposit(deposit_id)
        if dep.user_id != user_id:
            raise NotFoundException("Deposit not found")
        if dep.state not in MATCHABLE_DEPOSIT_STATES:
            raise ConflictException(f"This deposit is already {dep.status}")
        used = (await self.db.execute(
            select(BankCredit.id).where(BankCredit.utr == utr, BankCredit.status == "MATCHED")
        )).scalar_one_or_none()
        used = used or (await self.db.execute(
            select(Deposit.id).where(Deposit.user_utr == utr, Deposit.state == "CREDITED", Deposit.id != dep.id)
        )).scalar_one_or_none()
        if used:
            raise ConflictException("This UTR has already been used for another deposit")
        dep.user_utr = utr
        await self._move_deposit(dep, "UTR_SUBMITTED", Actor(user_id, "USER", "USER", ip), f"Player submitted UTR {utr}")
        await self._match_deposit(dep, SYSTEM)
        await self._commit()
        await self.db.refresh(dep)
        return dep

    async def cancel_deposit(self, user_id: str, deposit_id: str, ip: Optional[str]) -> Deposit:
        dep = await self._lock_deposit(deposit_id)
        if dep.user_id != user_id:
            raise NotFoundException("Deposit not found")
        if dep.state != "PENDING":
            raise ConflictException("Only an unpaid deposit without a UTR can be cancelled")
        await self._move_deposit(dep, "CANCELLED", Actor(user_id, "USER", "USER", ip), "Cancelled by player")
        await self._commit()
        return dep

    # ================================================================ matching + crediting

    async def _match_deposit(self, dep: Deposit, actor: Actor) -> bool:
        """Find an unmatched bank credit for this deposit (by UTR, then by reference in the remark)."""
        credit = None
        method = None
        if dep.user_utr:
            credit = (await self.db.execute(
                select(BankCredit).where(BankCredit.utr == dep.user_utr, BankCredit.status == "UNMATCHED")
            )).scalar_one_or_none()
            method = "AUTO_UTR"
        if credit is None:
            credit = (await self.db.execute(
                select(BankCredit).where(BankCredit.status == "UNMATCHED", BankCredit.remark.contains(dep.reference))
            )).scalars().first()
            method = "AUTO_REFERENCE"
        if credit is None:
            return False
        return await self._apply_credit(credit, dep, method, actor)

    async def _match_credit(self, credit: BankCredit, actor: Actor) -> Optional[Deposit]:
        """Find the deposit a new bank credit pays for: reference > player UTR > unique amount."""
        dep: Optional[Deposit] = None
        method = None
        ref = REFERENCE_RE.search((credit.remark or "").upper())
        if ref:
            dep = (await self.db.execute(select(Deposit).where(Deposit.reference == ref.group(0)))).scalar_one_or_none()
            method = "AUTO_REFERENCE"
        if dep is None:
            candidates = (await self.db.execute(
                select(Deposit).where(Deposit.user_utr == credit.utr, Deposit.state.in_(MATCHABLE_DEPOSIT_STATES))
            )).scalars().all()
            if len(candidates) == 1:
                dep, method = candidates[0], "AUTO_UTR"
            elif len(candidates) > 1:
                for cand in candidates:  # several players typed the same UTR: a human decides
                    await self._flag_review(cand, f"UTR {credit.utr} was submitted on {len(candidates)} deposits", actor)
                return None
        if dep is None and credit.payment_account_id:
            # Each open intent on an account has a unique amount (random paise), so an exact match is unambiguous
            window_start = (_aware(credit.received_at) or utcnow()) - timedelta(hours=24)
            candidates = (await self.db.execute(
                select(Deposit).where(
                    Deposit.payment_account_id == credit.payment_account_id,
                    Deposit.amount_paise == credit.amount_paise,
                    Deposit.state.in_(MATCHABLE_DEPOSIT_STATES),
                    Deposit.created_at >= window_start,
                )
            )).scalars().all()
            if len(candidates) == 1 and candidates[0].amount_paise % 100:
                dep, method = candidates[0], "AUTO_AMOUNT"
        if dep is None:
            return None
        dep = await self._lock_deposit(dep.id)
        return dep if await self._apply_credit(credit, dep, method, actor) else None

    async def _flag_review(self, dep: Deposit, reason: str, actor: Actor) -> None:
        dep.review_note = reason[:500]
        if dep.state != "MANUAL_REVIEW" and "MANUAL_REVIEW" in DEPOSIT_TRANSITIONS.get(dep.state, set()):
            await self._move_deposit(dep, "MANUAL_REVIEW", actor, reason)

    async def _apply_credit(
        self, credit: BankCredit, dep: Deposit, method: str, actor: Actor, *, manual: bool = False
    ) -> bool:
        """Validate the pair and credit the wallet; mismatches go to manual review instead."""
        if dep.state not in MATCHABLE_DEPOSIT_STATES:
            return False
        if credit.status != "UNMATCHED":
            raise ConflictException(f"Bank credit {credit.utr} is already {credit.status}")
        if credit.payment_account_id and credit.payment_account_id != dep.payment_account_id and not (manual and actor.is_super):
            await self._flag_review(dep, f"Bank credit {credit.utr} arrived in a different collection account", actor)
            return False
        if credit.amount_paise != dep.amount_paise and not manual:
            await self._flag_review(
                dep, f"Amount mismatch: requested {rupees(dep.amount_paise)}, bank shows {rupees(credit.amount_paise)} (UTR {credit.utr})", actor
            )
            return False
        await self._credit(dep, credit, method, actor)
        return True

    async def _credit(self, dep: Deposit, credit: BankCredit, method: str, actor: Actor) -> None:
        wallet = await self._lock_wallet(dep.wallet_id)
        before = wallet.balance
        wallet.balance += credit.amount_paise
        self._ledger(
            wallet, key=f"deposit:{dep.id}", tx_type=TransactionType.DEPOSIT, amount=credit.amount_paise, before=before,
            reference=f"DEPOSIT:{dep.reference}", description=f"Deposit {dep.reference} (UTR {credit.utr})",
        )
        dep.credited_amount_paise = credit.amount_paise
        dep.bank_credit_id = credit.id
        dep.verification_method = method
        dep.verified_by = actor.id if actor.kind == "ADMIN" else None
        dep.credited_at = utcnow()
        if not dep.user_utr:
            dep.user_utr = credit.utr
        credit.status = "MATCHED"
        credit.deposit_id = dep.id
        from app.affiliate import operator_bridge

        await operator_bridge.deposit_credited(self.db, dep.user_id, dep.id, credit.amount_paise, dep.credited_at)
        credit.payment_account_id = credit.payment_account_id or dep.payment_account_id
        await self._move_deposit(dep, "CREDITED", actor, f"{method}: UTR {credit.utr}, {rupees(credit.amount_paise)}")
        await self.db.flush()
        await self._notify(dep.user_id, "Deposit successful",
                           f"{rupees(credit.amount_paise)} has been added to your wallet (ref {dep.reference}).", "SUCCESS")
        logger.info("Deposit credited", deposit_id=dep.id, amount=credit.amount_paise, method=method)

    # ================================================================ deposits (staff)

    async def confirm_deposit(self, actor: Actor, deposit_id: str, raw_utr: str, amount: Optional[int], note: Optional[str]) -> Deposit:
        """Manual verification: the account owner saw the money in their bank and records its UTR."""
        dep = await self._lock_deposit(deposit_id)
        await self._ensure_account_access(actor, dep.payment_account_id)
        if dep.user_id == actor.id:
            raise ForbiddenException("You cannot verify your own deposit")
        if dep.state not in MATCHABLE_DEPOSIT_STATES:
            raise ConflictException(f"Deposit is already {dep.status}")
        amount = int(amount or dep.amount_paise)
        if amount <= 0:
            raise BadRequestException("Amount received must be positive")
        settings = await self._settings()
        if amount > settings["manual_deposit_super_threshold_paise"] and not actor.is_super:
            raise ForbiddenException(
                f"Manual confirmations above {rupees(settings['manual_deposit_super_threshold_paise'])} need the super admin"
            )
        utr = normalize_utr(raw_utr)
        credit = (await self.db.execute(select(BankCredit).where(BankCredit.utr == utr).with_for_update())).scalar_one_or_none()
        if credit is not None:
            if credit.status != "UNMATCHED":
                raise ConflictException(f"UTR {utr} was already used (deposit {credit.deposit_id or '-'})")
            if credit.amount_paise != amount:
                raise BadRequestException(f"UTR {utr} is on file for {rupees(credit.amount_paise)}, not {rupees(amount)}")
        else:
            credit = BankCredit(
                id=str(uuid.uuid4()), source="MANUAL", utr=utr, amount_paise=amount,
                payment_account_id=dep.payment_account_id, remark=(note or "").strip()[:255] or None,
                received_at=utcnow(), status="UNMATCHED", created_by=actor.id,
            )
            self.db.add(credit)
            try:
                await self.db.flush()
            except IntegrityError as exc:
                await self.db.rollback()
                raise ConflictException(f"UTR {utr} is already recorded") from exc
        if not await self._apply_credit(credit, dep, "MANUAL", actor, manual=True):
            await self._commit()
            raise ConflictException(dep.review_note or "This deposit could not be credited")
        await self._audit(actor, "DEPOSIT_MANUALLY_CONFIRMED", "DEPOSIT", dep.id, {
            "reference": dep.reference, "user_id": dep.user_id, "utr": utr, "requested_paise": dep.amount_paise,
            "credited_paise": amount, "note": note,
        })
        await self._commit()
        return dep

    async def reject_deposit(self, actor: Actor, deposit_id: str, reason: str) -> Deposit:
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise BadRequestException("Give a reason for rejecting")
        dep = await self._lock_deposit(deposit_id)
        await self._ensure_account_access(actor, dep.payment_account_id)
        if dep.state not in MATCHABLE_DEPOSIT_STATES:
            raise ConflictException(f"Deposit is already {dep.status}")
        dep.review_note = reason[:500]
        await self._move_deposit(dep, "FAILED", actor, reason)
        await self._audit(actor, "DEPOSIT_REJECTED", "DEPOSIT", dep.id, {"reference": dep.reference, "reason": reason})
        await self._notify(dep.user_id, "Deposit rejected", f"Deposit {dep.reference} was rejected: {reason}", "WARNING")
        await self._commit()
        return dep

    async def reverse_deposit(self, actor: Actor, deposit_id: str, reason: str) -> Deposit:
        """Chargeback / bank reversal of a credited deposit (super admin or provider webhook)."""
        if actor.kind == "ADMIN" and not actor.is_super:
            raise ForbiddenException("Only the super admin can reverse a deposit")
        reason = (reason or "").strip() or "Reversed"
        dep = await self._lock_deposit(deposit_id)
        if dep.state != "CREDITED":
            raise ConflictException("Only a successful deposit can be reversed")
        wallet = await self._lock_wallet(dep.wallet_id)
        amount = int(dep.credited_amount_paise or 0)
        available = wallet.balance - wallet.locked_balance
        debit = min(amount, max(available, 0))
        shortfall = amount - debit
        before = wallet.balance
        wallet.balance -= debit
        self._ledger(
            wallet, key=f"deposit-reversal:{dep.id}", tx_type=TransactionType.DEPOSIT_REVERSAL, amount=-debit, before=before,
            reference=f"DEPOSIT:{dep.reference}", description=f"Deposit {dep.reference} reversed: {reason}",
        )
        if shortfall:
            wallet.is_frozen = True  # money already spent/withdrawn: recovery case
        await self._move_deposit(dep, "REVERSED", actor, reason)
        from app.affiliate import operator_bridge

        await operator_bridge.deposit_reversed(self.db, dep.user_id, dep.id, amount, reason)
        await self._audit(actor, "DEPOSIT_REVERSED", "DEPOSIT", dep.id, {
            "reference": dep.reference, "amount_paise": amount, "debited_paise": debit,
            "shortfall_paise": shortfall, "wallet_frozen": bool(shortfall), "reason": reason,
        })
        await self._notify(dep.user_id, "Deposit reversed", f"Deposit {dep.reference} was reversed by the bank.", "WARNING")
        await self._commit()
        return dep

    # ================================================================ bank credits

    async def import_credits(self, actor: Actor, account_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Bank statement lines for one collection account; each new line is auto-matched."""
        account = await self._ensure_account_access(actor, account_id)
        result: Dict[str, Any] = {"created": 0, "matched": 0, "duplicates": [], "errors": [], "matched_deposits": []}
        for index, row in enumerate(rows, start=1):
            try:
                utr = normalize_utr(str(row.get("utr", "")))
                amount = int(row.get("amount_paise") or 0)
                if amount <= 0:
                    raise BadRequestException("amount must be positive")
            except BadRequestException as exc:
                result["errors"].append({"line": index, "error": exc.message})
                continue
            if (await self.db.execute(select(BankCredit.id).where(BankCredit.utr == utr))).scalar_one_or_none():
                result["duplicates"].append(utr)
                continue
            credit = BankCredit(
                id=str(uuid.uuid4()), source="STATEMENT", utr=utr, amount_paise=amount, payment_account_id=account.id,
                remark=(str(row.get("remark") or "").strip()[:255] or None),
                payer_name=(str(row.get("payer_name") or "").strip()[:100] or None),
                received_at=row.get("received_at") or utcnow(), status="UNMATCHED", created_by=actor.id,
            )
            self.db.add(credit)
            await self.db.flush()
            result["created"] += 1
            dep = await self._match_credit(credit, actor)
            if dep is not None:
                result["matched"] += 1
                result["matched_deposits"].append(dep.reference)
        await self._audit(actor, "BANK_STATEMENT_IMPORTED", "PAYMENT_ACCOUNT", account.id, {
            k: v for k, v in result.items() if k != "errors"
        } | {"errors": len(result["errors"])})
        await self._commit()
        return result

    async def assign_credit(self, actor: Actor, credit_id: str, deposit_id: str) -> Deposit:
        credit = (await self.db.execute(select(BankCredit).where(BankCredit.id == credit_id).with_for_update())).scalar_one_or_none()
        if credit is None:
            raise NotFoundException("Bank credit not found")
        dep = await self._lock_deposit(deposit_id)
        await self._ensure_account_access(actor, dep.payment_account_id)
        if credit.payment_account_id:
            await self._ensure_account_access(actor, credit.payment_account_id)
        if dep.user_id == actor.id:
            raise ForbiddenException("You cannot verify your own deposit")
        settings = await self._settings()
        if credit.amount_paise > settings["manual_deposit_super_threshold_paise"] and not actor.is_super:
            raise ForbiddenException("Large credits can only be assigned by the super admin")
        if not await self._apply_credit(credit, dep, "MANUAL_ASSIGN", actor, manual=True):
            await self._commit()
            raise ConflictException(dep.review_note or "This deposit could not be credited")
        await self._audit(actor, "BANK_CREDIT_ASSIGNED", "DEPOSIT", dep.id, {
            "reference": dep.reference, "utr": credit.utr, "credited_paise": credit.amount_paise,
            "requested_paise": dep.amount_paise,
        })
        await self._commit()
        return dep

    async def ignore_credit(self, actor: Actor, credit_id: str, reason: str) -> BankCredit:
        credit = (await self.db.execute(select(BankCredit).where(BankCredit.id == credit_id).with_for_update())).scalar_one_or_none()
        if credit is None:
            raise NotFoundException("Bank credit not found")
        if credit.payment_account_id:
            await self._ensure_account_access(actor, credit.payment_account_id)
        elif not actor.is_super:
            raise ForbiddenException("Only the super admin can handle credits with no account")
        if credit.status != "UNMATCHED":
            raise ConflictException(f"Bank credit is already {credit.status}")
        credit.status = "IGNORED"
        await self._audit(actor, "BANK_CREDIT_IGNORED", "BANK_CREDIT", credit.id, {"utr": credit.utr, "reason": reason})
        await self._commit()
        return credit

    # ================================================================ provider webhook

    async def handle_webhook(self, provider: str, body: bytes, headers: Dict[str, str], ip: Optional[str]) -> Dict[str, Any]:
        settings = get_settings()
        provider = provider.lower()
        secret = settings.payment_webhook_secrets.get(provider)
        if not secret:
            raise NotFoundException("Unknown payment provider")
        if settings.payment_webhook_ips and ip not in settings.payment_webhook_ips:
            raise ForbiddenException("Source not allowed")
        timestamp = headers.get("x-webhook-timestamp", "")
        signature = headers.get("x-webhook-signature", "")
        try:
            ts = int(timestamp)
        except ValueError:
            raise UnauthorizedException("Missing webhook timestamp")
        if abs(time.time() - ts) > settings.PAYMENT_WEBHOOK_TOLERANCE_SECONDS:
            raise UnauthorizedException("Webhook timestamp outside the allowed window")
        expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.strip().lower()):
            raise UnauthorizedException("Invalid webhook signature")
        try:
            payload = json.loads(body)
            event_id = str(payload["event_id"])[:100]
            event_type = str(payload["type"])[:40]
        except (ValueError, KeyError, TypeError) as exc:
            raise BadRequestException("Malformed webhook payload") from exc

        seen = (await self.db.execute(
            select(PaymentWebhookEvent.id).where(PaymentWebhookEvent.provider == provider, PaymentWebhookEvent.event_id == event_id)
        )).scalar_one_or_none()
        if seen:
            return {"status": "duplicate"}
        event = PaymentWebhookEvent(id=str(uuid.uuid4()), provider=provider, event_id=event_id, event_type=event_type,
                                    payload=payload, source_ip=ip)
        self.db.add(event)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return {"status": "duplicate"}

        actor = Actor(id=None, role="PROVIDER", kind="PROVIDER", ip=ip)
        result = await self._process_event(provider, event_id, event_type, payload, actor)
        event.result = result[:255]
        await self._commit()
        return {"status": "processed", "result": result}

    async def _process_event(self, provider: str, event_id: str, event_type: str, payload: Dict[str, Any], actor: Actor) -> str:
        if event_type in ("payment.credit", "payment.success"):
            try:
                utr = normalize_utr(str(payload.get("utr", "")))
                amount = int(payload["amount_paise"])
                if amount <= 0:
                    raise ValueError
            except (BadRequestException, KeyError, TypeError, ValueError):
                return "ignored: missing utr/amount"
            existing = (await self.db.execute(select(BankCredit).where(BankCredit.utr == utr))).scalar_one_or_none()
            if existing is not None:
                return f"already recorded ({existing.status})"
            account_id = None
            if payload.get("account_vpa"):
                account_id = (await self.db.execute(
                    select(PaymentAccount.id).where(func.lower(PaymentAccount.upi_id) == str(payload["account_vpa"]).lower())
                )).scalars().first()
            remark = " ".join(str(payload.get(k) or "") for k in ("reference", "remark")).strip()
            credit = BankCredit(
                id=str(uuid.uuid4()), source="WEBHOOK", provider=provider, provider_event_id=event_id, utr=utr,
                amount_paise=amount, payment_account_id=account_id, remark=remark[:255] or None,
                payer_name=(str(payload.get("payer_name") or "")[:100] or None),
                payer_vpa=(str(payload.get("payer_vpa") or "")[:100] or None),
                received_at=utcnow(), status="UNMATCHED",
            )
            self.db.add(credit)
            await self.db.flush()
            dep = await self._match_credit(credit, actor)
            return f"credited {dep.reference}" if dep else "recorded, unmatched"
        if event_type == "payment.failed":
            ref = REFERENCE_RE.search(str(payload.get("reference") or "").upper())
            if not ref:
                return "ignored: no reference"
            dep = (await self.db.execute(select(Deposit).where(Deposit.reference == ref.group(0)).with_for_update())).scalar_one_or_none()
            if dep is None or dep.state not in OPEN_DEPOSIT_STATES:
                return "ignored: no open deposit"
            await self._move_deposit(dep, "FAILED", actor, f"Provider reported failure: {payload.get('reason') or 'unknown'}")
            return f"failed {dep.reference}"
        if event_type == "payment.reversed":
            try:
                utr = normalize_utr(str(payload.get("utr", "")))
            except BadRequestException:
                return "ignored: missing utr"
            credit = (await self.db.execute(select(BankCredit).where(BankCredit.utr == utr))).scalar_one_or_none()
            if credit is None or not credit.deposit_id:
                return "ignored: unknown credit"
            dep = await self.db.get(Deposit, credit.deposit_id)
            if dep is None or dep.state != "CREDITED":
                return "ignored: deposit not credited"
            # reverse_deposit commits; the caller's final commit is then a no-op
            await self.reverse_deposit(actor, dep.id, f"Provider reversal: {payload.get('reason') or 'chargeback'}")
            return f"reversed {dep.reference}"
        return f"ignored: unknown type {event_type}"

    # ================================================================ PIN + beneficiaries

    async def set_pin(self, user_id: str, pin: str, password: str) -> None:
        user = await self._user(user_id)
        if not verify_password(password, user.password_hash):
            raise ForbiddenException("Your account password is incorrect")
        if not PIN_RE.match(pin or "") or pin in _WEAK_PINS or len(set(pin)) == 1:
            raise BadRequestException("PIN must be 4-6 digits and not an obvious sequence")
        had_pin = bool(user.transaction_pin_hash)
        user.transaction_pin_hash = hash_password(pin)
        # Changing an existing PIN restarts the withdrawal cooling period (account-takeover guard)
        user.transaction_pin_set_at = utcnow() if had_pin else utcnow() - timedelta(days=3650)
        await AuditRepository(self.db).create_log(
            action="TRANSACTION_PIN_CHANGED" if had_pin else "TRANSACTION_PIN_SET", target_type="USER",
            actor_id=user.id, target_id=user.id, details={},
        )
        await self._commit()

    async def _verify_pin(self, user: User, pin: str) -> None:
        if not user.transaction_pin_hash:
            raise BadRequestException("Set a transaction PIN first")
        identifier = f"txnpin:{user.id}"
        locked, remaining = await is_locked_out(identifier, "pin")
        if locked:
            raise RateLimitException(f"Too many wrong PINs — try again in {max(1, remaining // 60)} min")
        if not verify_password(pin or "", user.transaction_pin_hash):
            await record_failed_login(identifier, "pin")
            raise ForbiddenException("Incorrect transaction PIN")
        await reset_failed_attempts(identifier, "pin")

    async def list_beneficiaries(self, user_id: str) -> List[Beneficiary]:
        return list((await self.db.execute(
            select(Beneficiary).where(Beneficiary.user_id == user_id, Beneficiary.status == "ACTIVE")
            .order_by(Beneficiary.created_at.desc())
        )).scalars().all())

    async def add_beneficiary(self, user_id: str, data: Dict[str, Any], pin: str) -> Beneficiary:
        user = await self._user(user_id)
        await self._verify_pin(user, pin)
        await _rate_limit(f"benef:{user_id}", 5, 86400, "Too many payout account changes today")
        method = (data.get("method") or "").upper()
        holder = (data.get("holder_name") or "").strip()
        if not 2 <= len(holder) <= 100:
            raise BadRequestException("Enter the account holder's name")
        if method == "BANK":
            account_no = re.sub(r"\s", "", data.get("account_number") or "")
            ifsc = (data.get("ifsc") or "").strip().upper()
            if not ACCOUNT_RE.match(account_no):
                raise BadRequestException("Account number must be 9-18 digits")
            if not IFSC_RE.match(ifsc):
                raise BadRequestException("Enter a valid IFSC (e.g. HDFC0001234)")
            details = {"account_number": account_no, "ifsc": ifsc}
            normalized, masked = f"BANK:{ifsc[:4]}:{account_no}", f"{ifsc[:4]} A/c {mask_tail(account_no)}"
        elif method == "UPI":
            vpa = (data.get("vpa") or "").strip().lower()
            if not VPA_RE.match(vpa):
                raise BadRequestException("Enter a valid UPI id (e.g. name@okaxis)")
            details = {"vpa": vpa}
            normalized, masked = f"UPI:{vpa}", f"UPI {mask_vpa(vpa)}"
        else:
            raise BadRequestException("method must be BANK or UPI")
        active = await self.list_beneficiaries(user_id)
        if len(active) >= MAX_ACTIVE_BENEFICIARIES:
            raise ConflictException(f"You can keep at most {MAX_ACTIVE_BENEFICIARIES} payout accounts — remove one first")
        fp = field_crypto.fingerprint(normalized)
        if any(b.fingerprint == fp for b in active):
            raise ConflictException("This payout account is already saved")
        settings = await self._settings()
        ben_id = str(uuid.uuid4())
        ben = Beneficiary(
            id=ben_id, user_id=user_id, method=method, holder_name=holder,
            bank_name=(data.get("bank_name") or "").strip()[:100] or None,
            details_encrypted=field_crypto.encrypt_json(details, ben_id), masked=masked, fingerprint=fp, status="ACTIVE",
            cooling_until=utcnow() + timedelta(hours=settings["beneficiary_cooling_hours"]),
        )
        self.db.add(ben)
        await AuditRepository(self.db).create_log(
            action="BENEFICIARY_ADDED", target_type="BENEFICIARY", actor_id=user_id, target_id=ben_id,
            details={"method": method, "masked": masked},
        )
        await self._commit()
        return ben

    async def remove_beneficiary(self, user_id: str, beneficiary_id: str) -> None:
        ben = await self.db.get(Beneficiary, beneficiary_id)
        if ben is None or ben.user_id != user_id or ben.status != "ACTIVE":
            raise NotFoundException("Payout account not found")
        ben.status = "REMOVED"
        ben.removed_at = utcnow()
        await AuditRepository(self.db).create_log(
            action="BENEFICIARY_REMOVED", target_type="BENEFICIARY", actor_id=user_id, target_id=ben.id,
            details={"masked": ben.masked},
        )
        await self._commit()

    # ================================================================ withdrawals (player)

    async def _turnover(self, user_id: str) -> Dict[str, int]:
        deposited, first_at = (await self.db.execute(
            select(func.coalesce(func.sum(Deposit.credited_amount_paise), 0), func.min(Deposit.credited_at))
            .where(Deposit.user_id == user_id, Deposit.state == "CREDITED")
        )).one()
        wagered = 0
        if first_at is not None:
            wagered = (await self.db.execute(
                select(func.coalesce(func.sum(GameEntry.bet_amount), 0)).where(
                    GameEntry.user_id == user_id, GameEntry.created_at >= first_at,
                    GameEntry.status.notin_(_UNWAGERED_STATUSES),
                )
            )).scalar_one()
        return {"deposited": int(deposited or 0), "wagered": int(wagered or 0)}

    async def eligibility(self, user_id: str) -> Dict[str, Any]:
        """Everything the withdraw screen needs, and the reasons a request would be refused."""
        settings = await self._settings()
        user = await self._user(user_id)
        wallet = (await self.db.execute(select(Wallet).where(Wallet.user_id == user_id))).scalar_one_or_none()
        available = (wallet.balance - wallet.locked_balance) if wallet else 0
        turnover = await self._turnover(user_id)
        required = turnover["deposited"] * settings["withdrawal_turnover_pct"] // 100
        day_ago = utcnow() - timedelta(hours=24)
        today_count, today_amount = (await self.db.execute(
            select(func.count(Withdrawal.id), func.coalesce(func.sum(Withdrawal.amount_paise), 0)).where(
                Withdrawal.user_id == user_id, Withdrawal.created_at >= day_ago,
                Withdrawal.state.notin_(("REJECTED", "CANCELLED")),
            )
        )).one()
        pin_cooling_until = None
        if user.transaction_pin_set_at:
            until = _aware(user.transaction_pin_set_at) + timedelta(hours=settings["beneficiary_cooling_hours"])
            pin_cooling_until = until if until > utcnow() else None
        blockers: List[str] = []
        if not settings["payments_enabled"]:
            blockers.append("Withdrawals are paused right now")
        if wallet is not None and wallet.is_frozen:
            blockers.append("Your wallet is frozen — contact support")
        if not user.transaction_pin_hash:
            blockers.append("Set a transaction PIN")
        if pin_cooling_until:
            blockers.append("Your PIN was changed recently; withdrawals unlock after the cooling period")
        if settings["withdrawal_requires_deposit"] and turnover["deposited"] == 0:
            blockers.append("Make a successful deposit first")
        if turnover["wagered"] < required:
            blockers.append(f"Play {rupees(required - turnover['wagered'])} more before withdrawing (turnover rule)")
        if today_count >= settings["withdrawal_daily_count"]:
            blockers.append("Daily withdrawal limit reached")
        return {
            "available_paise": max(available, 0),
            "pending_withdrawal_paise": wallet.pending_withdrawal if wallet else 0,
            "min_paise": settings["withdrawal_min_paise"],
            "max_paise": settings["withdrawal_max_paise"],
            "daily_count_left": max(settings["withdrawal_daily_count"] - int(today_count), 0),
            "daily_amount_left_paise": max(settings["withdrawal_daily_amount_paise"] - int(today_amount), 0),
            "deposited_paise": turnover["deposited"],
            "wagered_paise": turnover["wagered"],
            "turnover_required_paise": required,
            "pin_set": bool(user.transaction_pin_hash),
            "pin_cooling_until": pin_cooling_until,
            "cooling_hours": settings["beneficiary_cooling_hours"],
            "blockers": blockers,
            "can_withdraw": not blockers,
        }

    async def request_withdrawal(
        self, user_id: str, amount: int, beneficiary_id: str, pin: str, idem_key: str, ip: Optional[str]
    ) -> Withdrawal:
        existing = (await self.db.execute(
            select(Withdrawal).where(Withdrawal.user_id == user_id, Withdrawal.idempotency_key == idem_key)
        )).scalar_one_or_none()
        if existing is not None:
            if existing.amount_paise != amount or existing.beneficiary_id != beneficiary_id:
                raise ConflictException("This request key was already used for a different withdrawal")
            return existing
        await _rate_limit(f"withdraw:{user_id}", 10, 3600, "Too many withdrawal attempts — try again later")
        user = await self._user(user_id)
        if not user.is_active:
            raise ForbiddenException("Account suspended")
        await self._verify_pin(user, pin)

        info = await self.eligibility(user_id)
        if info["blockers"]:
            raise ForbiddenException(info["blockers"][0])
        if amount < info["min_paise"] or amount > info["max_paise"]:
            raise BadRequestException(f"Withdrawal must be between {rupees(info['min_paise'])} and {rupees(info['max_paise'])}")
        if amount > info["daily_amount_left_paise"]:
            raise BadRequestException(f"You can withdraw {rupees(info['daily_amount_left_paise'])} more today")

        ben = await self.db.get(Beneficiary, beneficiary_id)
        if ben is None or ben.user_id != user_id or ben.status != "ACTIVE":
            raise NotFoundException("Payout account not found")
        if _aware(ben.cooling_until) > utcnow():
            raise ForbiddenException(f"This payout account can be used from {_aware(ben.cooling_until).isoformat()} (security cooling period)")

        wallet = (await self.db.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update())).scalar_one_or_none()
        if wallet is None:
            raise NotFoundException("Wallet not found")
        if wallet.is_frozen:
            raise ForbiddenException("Your wallet is frozen — contact support")
        available = wallet.balance - wallet.locked_balance
        if available < amount:
            raise InsufficientBalanceException(f"Insufficient balance: {rupees(max(available, 0))} available")

        wd_id = str(uuid.uuid4())
        flags, score = await self._risk_flags(user_id, ben, amount)
        details = field_crypto.decrypt_json(ben.details_encrypted, ben.id)
        snapshot = {**details, "method": ben.method, "holder_name": ben.holder_name, "bank_name": ben.bank_name}
        wd = Withdrawal(
            id=wd_id, user_id=user_id, wallet_id=wallet.id, beneficiary_id=ben.id, amount_paise=amount,
            idempotency_key=idem_key, risk_score=score, risk_flags=flags,
            payout_details_encrypted=field_crypto.encrypt_json(snapshot, wd_id),
            payout_masked=f"{ben.holder_name} · {ben.masked}"[:120], request_ip=ip,
        )
        before = wallet.balance
        wallet.balance -= amount
        wallet.pending_withdrawal += amount
        self._ledger(
            wallet, key=f"withdrawal-hold:{wd_id}", tx_type=TransactionType.WITHDRAWAL_HOLD, amount=-amount, before=before,
            reference=f"WITHDRAWAL:{wd_id}", description=f"Withdrawal requested to {ben.masked}",
        )
        await self._move_withdrawal(wd, "AWAITING_APPROVAL", Actor(user_id, "USER", "USER", ip), "Withdrawal requested")
        self.db.add(wd)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            existing = (await self.db.execute(
                select(Withdrawal).where(Withdrawal.user_id == user_id, Withdrawal.idempotency_key == idem_key)
            )).scalar_one_or_none()
            if existing is None:
                raise
            return existing
        await self._notify_superadmins(
            "New withdrawal request", f"{user.username} requested {rupees(amount)} (risk score {score})."
        )
        await self._commit()
        logger.info("Withdrawal requested", withdrawal_id=wd_id, user_id=user_id, amount=amount, risk=score)
        return wd

    async def _risk_flags(self, user_id: str, ben: Beneficiary, amount: int) -> Tuple[Dict[str, Any], int]:
        settings = await self._settings()
        now = utcnow()
        flags: Dict[str, Any] = {}
        completed = (await self.db.execute(
            select(func.count(Withdrawal.id)).where(Withdrawal.user_id == user_id, Withdrawal.state == "COMPLETED")
        )).scalar_one()
        if completed == 0:
            flags["first_withdrawal"] = True
        if _aware(ben.created_at or now) > now - timedelta(hours=72):
            flags["new_payout_account"] = True
        shared = (await self.db.execute(
            select(func.count(func.distinct(Beneficiary.user_id))).where(
                Beneficiary.fingerprint == ben.fingerprint, Beneficiary.user_id != user_id
            )
        )).scalar_one()
        if shared:
            flags["shared_payout_account"] = int(shared)
        last_dep = (await self.db.execute(
            select(func.max(Deposit.credited_at)).where(Deposit.user_id == user_id, Deposit.state == "CREDITED")
        )).scalar_one()
        if last_dep is not None and _aware(last_dep) > now - timedelta(hours=2):
            flags["deposit_then_withdraw"] = True
        if amount >= settings["withdrawal_high_value_paise"]:
            flags["high_value"] = True
        recent = (await self.db.execute(
            select(func.count(Withdrawal.id)).where(Withdrawal.user_id == user_id, Withdrawal.created_at >= now - timedelta(hours=24))
        )).scalar_one()
        if recent >= 2:
            flags["velocity_24h"] = int(recent) + 1
        wallet_id = (await self.db.execute(select(Wallet.id).where(Wallet.user_id == user_id))).scalar_one()
        free_credits = (await self.db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.wallet_id == wallet_id,
                WalletTransaction.type.in_((TransactionType.BONUS.value, TransactionType.FAUCET.value)),
            )
        )).scalar_one()
        deposited = (await self._turnover(user_id))["deposited"]
        if free_credits and free_credits > deposited:
            flags["bonus_heavy"] = {"bonus_paise": int(free_credits), "deposited_paise": deposited}
        weights = {"first_withdrawal": 10, "new_payout_account": 20, "shared_payout_account": 40, "deposit_then_withdraw": 25,
                   "high_value": 20, "velocity_24h": 15, "bonus_heavy": 30}
        return flags, min(100, sum(weights[k] for k in flags))

    async def _notify_superadmins(self, title: str, message: str) -> None:
        ids = (await self.db.execute(
            select(User.id).join(Role, User.role_id == Role.id).where(Role.name == UserRole.SUPERADMIN.value, User.is_active.is_(True))
        )).scalars().all()
        for uid in ids:
            await self._notify(uid, title, message, "INFO")

    async def cancel_withdrawal(self, user_id: str, withdrawal_id: str, ip: Optional[str]) -> Withdrawal:
        wd = await self._lock_withdrawal(withdrawal_id)
        if wd.user_id != user_id:
            raise NotFoundException("Withdrawal not found")
        if wd.state != "AWAITING_APPROVAL":
            raise ConflictException("This withdrawal is already being paid out and can no longer be cancelled")
        await self._release(wd, "CANCELLED", Actor(user_id, "USER", "USER", ip), "Cancelled by player")
        await self._commit()
        return wd

    async def _release(self, wd: Withdrawal, new_state: str, actor: Actor, reason: str) -> None:
        wallet = await self._lock_wallet(wd.wallet_id)
        if wallet.pending_withdrawal < wd.amount_paise:
            raise ConflictException("Wallet hold is inconsistent — run the payments integrity check")
        before = wallet.balance
        wallet.pending_withdrawal -= wd.amount_paise
        wallet.balance += wd.amount_paise
        self._ledger(
            wallet, key=f"withdrawal-release:{wd.id}", tx_type=TransactionType.WITHDRAWAL_RELEASE, amount=wd.amount_paise,
            before=before, reference=f"WITHDRAWAL:{wd.id}", description=f"Withdrawal {new_state.lower()}: funds returned",
        )
        await self._move_withdrawal(wd, new_state, actor, reason)

    # ================================================================ withdrawals (staff)

    def _check_version(self, wd: Withdrawal, expected_version: Optional[int]) -> None:
        if expected_version is not None and wd.version != expected_version:
            raise ConflictException("This withdrawal changed since you opened it — refresh and try again")

    async def initiate_withdrawal(self, actor: Actor, withdrawal_id: str, note: Optional[str], expected_version: Optional[int]) -> Withdrawal:
        """Maker step: an admin records that the bank payout has been started."""
        wd = await self._lock_withdrawal(withdrawal_id)
        self._check_version(wd, expected_version)
        if wd.user_id == actor.id:
            raise ForbiddenException("You cannot process your own withdrawal")
        if wd.state != "AWAITING_APPROVAL":
            raise ConflictException(f"Withdrawal is {wd.state}")
        wd.initiated_by, wd.initiated_at = actor.id, utcnow()
        wd.admin_note = (note or "").strip()[:500] or wd.admin_note
        await self._move_withdrawal(wd, "PAYOUT_INITIATED", actor, note or "Payout initiated")
        await self._audit(actor, "WITHDRAWAL_PAYOUT_INITIATED", "WITHDRAWAL", wd.id,
                          {"amount_paise": wd.amount_paise, "user_id": wd.user_id, "note": note})
        await self._commit()
        return wd

    async def complete_withdrawal(
        self, actor: Actor, withdrawal_id: str, payout_reference: str, expected_version: Optional[int], note: Optional[str]
    ) -> Withdrawal:
        if not actor.is_super:
            raise ForbiddenException("Only the super admin can complete a withdrawal")
        reference = normalize_utr(payout_reference)
        wd = await self._lock_withdrawal(withdrawal_id)
        self._check_version(wd, expected_version)
        if wd.user_id == actor.id:
            raise ForbiddenException("You cannot approve your own withdrawal")
        if wd.state not in OPEN_WITHDRAWAL_STATES:
            raise ConflictException(f"Withdrawal is already {wd.status}")
        settings = await self._settings()
        if wd.amount_paise >= settings["withdrawal_high_value_paise"]:
            if wd.state != "PAYOUT_INITIATED":
                raise ConflictException("High-value withdrawal: another admin must mark the payout initiated first (maker-checker)")
            if wd.initiated_by == actor.id:
                raise ForbiddenException("Maker-checker: the admin who initiated the payout cannot also complete it")
        clash = (await self.db.execute(
            select(Withdrawal.id).where(Withdrawal.payout_reference == reference, Withdrawal.id != wd.id)
        )).scalar_one_or_none()
        if clash:
            raise ConflictException("This payout reference (UTR) is already recorded on another withdrawal")
        wallet = await self._lock_wallet(wd.wallet_id)
        if wallet.pending_withdrawal < wd.amount_paise:
            raise ConflictException("Wallet hold is inconsistent — run the payments integrity check")
        wallet.pending_withdrawal -= wd.amount_paise
        self._ledger(
            wallet, key=f"withdrawal-settle:{wd.id}", tx_type=TransactionType.WITHDRAWAL_SETTLE, amount=0, before=wallet.balance,
            reference=f"WITHDRAWAL:{wd.id}", description=f"Withdrawal of {rupees(wd.amount_paise)} paid (UTR {reference})",
        )
        wd.payout_reference = reference
        wd.completed_by, wd.completed_at = actor.id, utcnow()
        if note:
            wd.admin_note = note.strip()[:500]
        await self._move_withdrawal(wd, "COMPLETED", actor, f"Paid, UTR {reference}")
        await self._audit(actor, "WITHDRAWAL_COMPLETED", "WITHDRAWAL", wd.id, {
            "amount_paise": wd.amount_paise, "user_id": wd.user_id, "payout_reference": reference,
            "initiated_by": wd.initiated_by, "risk_score": wd.risk_score,
        })
        await self._notify(wd.user_id, "Withdrawal completed",
                           f"{rupees(wd.amount_paise)} was sent to {wd.payout_masked} (UTR …{reference[-4:]}).", "SUCCESS")
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException("This payout reference (UTR) is already recorded on another withdrawal") from exc
        await self._commit()
        return wd

    async def reject_withdrawal(self, actor: Actor, withdrawal_id: str, reason: str, expected_version: Optional[int]) -> Withdrawal:
        if not actor.is_super:
            raise ForbiddenException("Only the super admin can reject a withdrawal")
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise BadRequestException("Give a reason — the player will see it")
        wd = await self._lock_withdrawal(withdrawal_id)
        self._check_version(wd, expected_version)
        if wd.state not in OPEN_WITHDRAWAL_STATES:
            raise ConflictException(f"Withdrawal is already {wd.status}")
        wd.rejected_by, wd.rejected_at, wd.reject_reason = actor.id, utcnow(), reason[:500]
        await self._release(wd, "REJECTED", actor, reason)
        await self._audit(actor, "WITHDRAWAL_REJECTED", "WITHDRAWAL", wd.id,
                          {"amount_paise": wd.amount_paise, "user_id": wd.user_id, "reason": reason})
        await self._notify(wd.user_id, "Withdrawal rejected",
                           f"Your withdrawal of {rupees(wd.amount_paise)} was rejected and returned to your wallet: {reason}", "WARNING")
        await self._commit()
        return wd

    async def payout_details(self, actor: Actor, withdrawal_id: str) -> Dict[str, Any]:
        """Full bank details for paying out — super admin only, and every view is audited."""
        if not actor.is_super:
            raise ForbiddenException("Only the super admin can view full payout details")
        wd = await self.db.get(Withdrawal, withdrawal_id)
        if wd is None:
            raise NotFoundException("Withdrawal not found")
        details = field_crypto.decrypt_json(wd.payout_details_encrypted, wd.id)
        await self._audit(actor, "PAYOUT_DETAILS_VIEWED", "WITHDRAWAL", wd.id, {"user_id": wd.user_id})
        await self._commit()
        return details

    # ================================================================ reporting

    async def integrity_report(self) -> Dict[str, Any]:
        """Ledger checks the PDF asks to run nightly: holds, credits, payout references."""
        problems: List[Dict[str, Any]] = []
        held = dict((await self.db.execute(
            select(Withdrawal.wallet_id, func.sum(Withdrawal.amount_paise))
            .where(Withdrawal.state.in_(OPEN_WITHDRAWAL_STATES)).group_by(Withdrawal.wallet_id)
        )).all())
        wallets = (await self.db.execute(
            select(Wallet.id, Wallet.user_id, Wallet.pending_withdrawal).where(
                or_(Wallet.pending_withdrawal != 0, Wallet.id.in_(list(held) or [""]))
            )
        )).all()
        for wallet_id, user_id, pending in wallets:
            expected = int(held.get(wallet_id, 0) or 0)
            if int(pending) != expected:
                problems.append({"check": "withdrawal_hold", "wallet_id": wallet_id, "user_id": user_id,
                                 "wallet_pending_paise": int(pending), "open_withdrawals_paise": expected})
        credited_total = (await self.db.execute(
            select(func.coalesce(func.sum(Deposit.credited_amount_paise), 0)).where(Deposit.state.in_(("CREDITED", "REVERSED")))
        )).scalar_one()
        ledger_total = (await self.db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(WalletTransaction.type == TransactionType.DEPOSIT.value)
        )).scalar_one()
        if int(credited_total) != int(ledger_total):
            problems.append({"check": "deposit_ledger", "deposits_credited_paise": int(credited_total), "ledger_deposit_paise": int(ledger_total)})
        orphan = (await self.db.execute(
            select(func.count(Deposit.id)).where(Deposit.state == "CREDITED", Deposit.bank_credit_id.is_(None))
        )).scalar_one()
        if orphan:
            problems.append({"check": "credited_without_bank_credit", "count": int(orphan)})
        missing_ref = (await self.db.execute(
            select(func.count(Withdrawal.id)).where(Withdrawal.state == "COMPLETED", Withdrawal.payout_reference.is_(None))
        )).scalar_one()
        if missing_ref:
            problems.append({"check": "completed_without_payout_reference", "count": int(missing_ref)})
        return {"ok": not problems, "checked_at": utcnow(), "problems": problems,
                "totals": {"deposits_credited_paise": int(credited_total), "withdrawals_held_paise": int(sum(int(v or 0) for v in held.values()))}}
