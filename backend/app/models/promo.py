"""Bonus promo codes: the super admin creates them, each player can redeem a code once."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)  # stored upper case
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemption_once"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    promo_code_id: Mapped[str] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
