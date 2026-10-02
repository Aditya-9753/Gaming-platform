"""Durable Cricket winner-market state and player predictions."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CricketMatchRecord(Base):
    __tablename__ = "cricket_matches"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    home_team: Mapped[str] = mapped_column(String(150), nullable=False)
    away_team: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    home_score: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    away_score: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    winner: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    abandoned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CricketPrediction(Base):
    __tablename__ = "cricket_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id: Mapped[str] = mapped_column(
        ForeignKey("cricket_matches.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    selection: Mapped[str] = mapped_column(String(150), nullable=False)
    stake: Mapped[int] = mapped_column(BigInteger, nullable=False)
    odds_bp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payout: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PLACED", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("match_id", "user_id", "idempotency_key", name="uq_cricket_prediction_request"),
        Index("ix_cricket_predictions_match_status", "match_id", "status"),
    )
