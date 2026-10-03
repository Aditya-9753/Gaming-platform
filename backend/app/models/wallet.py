"""SQLAlchemy models for virtual credit wallets and immutable ledger transactions."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Text,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Wallet(Base):
    """User virtual credit wallet storing balances in integer paise."""

    __tablename__ = "wallets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    # Balance stored as BigInteger in paise (100 paise = 1 Credit) - NEVER FLOAT
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    locked_balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # Already removed from balance; reserved for withdrawals awaiting super-admin payout
    pending_withdrawal: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="VIRTUAL", nullable=False)

    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Integrity Constraints
    __table_args__ = (
        CheckConstraint("balance >= 0", name="chk_wallet_positive_balance"),
        CheckConstraint("locked_balance >= 0", name="chk_wallet_positive_locked_balance"),
        CheckConstraint("pending_withdrawal >= 0", name="chk_wallet_positive_pending_withdrawal"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="wallet")
    transactions: Mapped[List["WalletTransaction"]] = relationship(
        "WalletTransaction", back_populates="wallet", cascade="all, delete-orphan"
    )

    @property
    def available_balance(self) -> int:
        """Calculate spendable credits: balance minus locked balance."""
        return self.balance - self.locked_balance


class WalletTransaction(Base):
    """Immutable credit movement ledger record."""

    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    wallet_id: Mapped[str] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Ledger audit fields (in integer paise)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_before: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[str] = mapped_column(String(50), default="COMPLETED", nullable=False, index=True)
    reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # AES-256-GCM seal of this row (see app.security.integrity)
    integrity_seal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Index for fast ledger history retrieval
    __table_args__ = (
        Index("ix_wallet_tx_wallet_created", "wallet_id", "created_at"),
    )

    # Relationships
    wallet: Mapped[Wallet] = relationship("Wallet", back_populates="transactions")
