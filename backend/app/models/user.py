"""SQLAlchemy model for users (single unified table for players, admins, and support)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.game import GameEntry
    from app.models.notification import Notification
    from app.models.refresh_token import RefreshToken
    from app.models.role import Role
    from app.models.self_exclusion import SelfExclusion
    from app.models.support import SupportTicket
    from app.models.wallet import Wallet


class User(Base):
    """Unified user entity for players, auditors, support, and administrators."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "totp" (authenticator app) or "email" (one-time code by email); None = not set up
    two_factor_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users")
    wallet: Mapped[Optional["Wallet"]] = relationship(
        "Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    game_entries: Mapped[List["GameEntry"]] = relationship("GameEntry", back_populates="user")
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    support_tickets: Mapped[List["SupportTicket"]] = relationship(
        "SupportTicket",
        foreign_keys="SupportTicket.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    self_exclusion: Mapped[Optional["SelfExclusion"]] = relationship(
        "SelfExclusion", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
