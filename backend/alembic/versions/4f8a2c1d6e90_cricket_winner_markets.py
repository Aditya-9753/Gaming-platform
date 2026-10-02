"""Create Cricket match and prediction market tables.

Revision ID: 4f8a2c1d6e90
Revises: 3ca1f9b2d8e4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f8a2c1d6e90"
down_revision: Union[str, None] = "3ca1f9b2d8e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cricket_matches",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("home_team", sa.String(length=150), nullable=False),
        sa.Column("away_team", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("home_score", sa.String(length=80), nullable=True),
        sa.Column("away_score", sa.String(length=80), nullable=True),
        sa.Column("winner", sa.String(length=150), nullable=True),
        sa.Column("abandoned", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cricket_matches_status", "cricket_matches", ["status"])
    op.create_table(
        "cricket_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("match_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("selection", sa.String(length=150), nullable=False),
        sa.Column("stake", sa.BigInteger(), nullable=False),
        sa.Column("odds_bp", sa.BigInteger(), nullable=False),
        sa.Column("payout", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["cricket_matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint(
            "match_id", "user_id", "idempotency_key",
            name="uq_cricket_prediction_request",
        ),
    )
    op.create_index(
        "ix_cricket_predictions_status", "cricket_predictions", ["status"]
    )
    op.create_index(
        "ix_cricket_predictions_match_status",
        "cricket_predictions",
        ["match_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cricket_predictions_match_status", table_name="cricket_predictions"
    )
    op.drop_index("ix_cricket_predictions_status", table_name="cricket_predictions")
    op.drop_table("cricket_predictions")
    op.drop_index("ix_cricket_matches_status", table_name="cricket_matches")
    op.drop_table("cricket_matches")
