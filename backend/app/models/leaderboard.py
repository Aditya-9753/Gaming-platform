"""SQLAlchemy model for platform and game leaderboards."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.user import User


class Leaderboard(Base):
    """Aggregated leaderboard ranks and virtual credit turnover."""

    __tablename__ = "leaderboards"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True
    )

    period: Mapped[str] = mapped_column(String(50), default="DAILY", nullable=False, index=True)

    # Financials in integer paise
    total_wagered: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_won: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    net_profit: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    rank: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_leaderboard_period_rank", "period", "rank"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    game: Mapped[Optional["Game"]] = relationship("Game")
