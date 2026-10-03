"""Deposits, withdrawals and the records that prove them.

Money model (all amounts are integer paise, never floats):

* A deposit is an *intent* with a unique reference routed to one staff-owned
  collection account (UPI QR). It becomes SUCCESS only when a bank credit
  (signed provider webhook, imported bank statement line, or an admin
  confirming the credit they can see in their own bank account) is matched
  to it. A user-typed UTR is a lookup hint, never proof.
* A withdrawal moves money from ``wallets.balance`` into
  ``wallets.pending_withdrawal`` at request time (WITHDRAWAL_HOLD). Only a
  super admin can complete it (WITHDRAWAL_SETTLE, with the bank payout UTR)
  or reject it (WITHDRAWAL_RELEASE, money back to the player).

``status`` is the small user-facing value; ``state`` is the detailed internal
state machine. Both are written only by ``app.services.payment_service``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PaymentAccount(Base):
    """A staff-owned UPI collection account (the QR players pay into)."""

    __tablename__ = "payment_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    upi_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Optional static QR image uploaded by the owner (data URL: png/jpeg/webp)
    qr_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # PENDING_APPROVAL -> ACTIVE <-> DISABLED ; REJECTED
    status: Mapped[str] = mapped_column(String(20), default="PENDING_APPROVAL", nullable=False, index=True)
    min_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    max_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 0 = no cap
    daily_limit_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 0 = no cap
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("min_amount_paise >= 0", name="chk_payacct_min"),
        CheckConstraint("max_amount_paise >= 0", name="chk_payacct_max"),
        CheckConstraint("daily_limit_paise >= 0", name="chk_payacct_daily"),
    )


class Deposit(Base):
    """A deposit intent and its lifecycle."""

    __tablename__ = "deposits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False)
    payment_account_id: Mapped[str] = mapped_column(
        ForeignKey("payment_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    credited_amount_paise: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reference: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    # User-facing: PENDING | SUCCESS | REJECTED
    status: Mapped[str] = mapped_column(String(12), default="PENDING", nullable=False, index=True)
    # Internal: PENDING | UTR_SUBMITTED | MANUAL_REVIEW | CREDITED | FAILED | EXPIRED | CANCELLED | REVERSED
    state: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    user_utr: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    bank_credit_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("bank_credits.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    verification_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    verified_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    credited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Optimistic lock: a concurrent update of the same row raises StaleDataError
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_deposit_user_idem"),
        CheckConstraint("amount_paise > 0", name="chk_deposit_amount_positive"),
        Index("ix_deposits_account_state", "payment_account_id", "state"),
        Index("ix_deposits_created", "created_at"),
    )


class BankCredit(Base):
    """Money that verifiably arrived in a collection account.

    UTR is globally unique: one bank credit can fund at most one deposit.
    """

    __tablename__ = "bank_credits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # WEBHOOK | STATEMENT | MANUAL
    provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utr: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_account_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("payment_accounts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payer_vpa: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="UNMATCHED", nullable=False, index=True)  # UNMATCHED | MATCHED | IGNORED
    deposit_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_bank_credit_provider_event"),
        CheckConstraint("amount_paise > 0", name="chk_bank_credit_amount_positive"),
    )


class PaymentWebhookEvent(Base):
    """Raw provider webhook events (replay store; one row per provider event id)."""

    __tablename__ = "payment_webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)


class Beneficiary(Base):
    """A player's payout destination (bank account or UPI id), encrypted at rest."""

    __tablename__ = "beneficiaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)  # BANK | UPI
    holder_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    masked: Mapped[str] = mapped_column(String(60), nullable=False)
    # Keyed hash of the normalised account so the same account across users can be flagged
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", nullable=False)  # ACTIVE | REMOVED
    cooling_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Withdrawal(Base):
    """A withdrawal request; funds are held in wallets.pending_withdrawal until settled."""

    __tablename__ = "withdrawals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False)
    beneficiary_id: Mapped[str] = mapped_column(ForeignKey("beneficiaries.id", ondelete="RESTRICT"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # User-facing: PENDING | COMPLETED | REJECTED
    status: Mapped[str] = mapped_column(String(12), default="PENDING", nullable=False, index=True)
    # Internal: AWAITING_APPROVAL | PAYOUT_INITIATED | COMPLETED | REJECTED | CANCELLED
    state: Mapped[str] = mapped_column(String(20), default="AWAITING_APPROVAL", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_flags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Payout destination frozen at request time (encrypted) + its masked label
    payout_details_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    payout_masked: Mapped[str] = mapped_column(String(120), nullable=False)
    payout_reference: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    initiated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    initiated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    request_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_withdrawal_user_idem"),
        CheckConstraint("amount_paise > 0", name="chk_withdrawal_amount_positive"),
        Index("ix_withdrawals_state_created", "state", "created_at"),
    )


class PaymentStatusHistory(Base):
    """Every state change of a deposit or withdrawal (who, when, why, from where)."""

    __tablename__ = "payment_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(12), nullable=False)  # DEPOSIT | WITHDRAWAL
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(12), nullable=False)  # USER | ADMIN | SYSTEM | PROVIDER
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
