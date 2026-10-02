"""SQLAlchemy models for games, game settings, rounds, results, and entries."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Game(Base):
    """Registered games on the platform (aviator, mines, color, cricket)."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # e.g. "aviator", "mines", "color", "cricket"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    settings: Mapped[Optional["GameSetting"]] = relationship(
        "GameSetting", back_populates="game", uselist=False, cascade="all, delete-orphan"
    )
    rounds: Mapped[List["GameRound"]] = relationship(
        "GameRound", back_populates="game", cascade="all, delete-orphan"
    )


class GameSetting(Base):
    """Game rules, bet limits (in paise), and house edge configuration."""

    __tablename__ = "game_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Limits stored in integer paise (1 credit = 100 paise)
    min_bet: Mapped[int] = mapped_column(BigInteger, default=100, nullable=False)
    max_bet: Mapped[int] = mapped_column(BigInteger, default=100000, nullable=False)
    house_edge_percent: Mapped[int] = mapped_column(BigInteger, default=300, nullable=False)  # basis points (300 = 3.00%)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    game: Mapped[Game] = relationship("Game", back_populates="settings")


class GameRound(Base):
    """Game round with provably fair cryptographic seeds and outcome."""

    __tablename__ = "game_rounds"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="SCHEDULED", nullable=False, index=True)

    # Provably Fair commit-reveal parameters
    server_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    server_seed: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    client_seed: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Required compound index and unique round number per game
    __table_args__ = (
        Index("ix_game_rounds_game_round_no", "game_id", "round_no"),
        Index("ix_game_rounds_game_status_created", "game_id", "status", "created_at"),
        Index("ix_game_rounds_created_at", "created_at"),
        UniqueConstraint("game_id", "round_no", name="uq_game_rounds_game_round_no"),
    )

    # Relationships
    game: Mapped[Game] = relationship("Game", back_populates="rounds")
    entries: Mapped[List["GameEntry"]] = relationship(
        "GameEntry", back_populates="round", cascade="all, delete-orphan"
    )
    game_result: Mapped[Optional["GameResult"]] = relationship(
        "GameResult", back_populates="round", uselist=False, cascade="all, delete-orphan"
    )


class GameResult(Base):
    """Aggregated game round result and provably fair validation data."""

    __tablename__ = "game_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    round_id: Mapped[str] = mapped_column(
        ForeignKey("game_rounds.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    outcome: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    total_bets: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_payouts: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    round: Mapped[GameRound] = relationship("GameRound", back_populates="game_result")


class GameEntry(Base):
    """Player wager/entry into a game round with unique idempotency."""

    __tablename__ = "game_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    round_id: Mapped[str] = mapped_column(
        ForeignKey("game_rounds.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Financials in integer paise
    bet_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    multiplier: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # basis points (e.g. 250 for 2.50x)
    payout_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    status: Mapped[str] = mapped_column(String(50), default="PLACED", nullable=False, index=True)
    selection: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Required indexes
    __table_args__ = (
        Index("ix_game_entries_user_created", "user_id", "created_at"),
        Index("ix_game_entries_round_id", "round_id"),
    )

    # Relationships
    round: Mapped[GameRound] = relationship("GameRound", back_populates="entries")
    user: Mapped["User"] = relationship("User", back_populates="game_entries")
