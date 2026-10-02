"""Add cold-storage table for archived game records.

Revision ID: 1d12ab34ef56
Revises: bd79ca76edcc
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1d12ab34ef56"
down_revision: Union[str, None] = "bd79ca76edcc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_archives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("record_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "record_type", "source_id", name="uq_game_archives_type_source"
        ),
    )
    op.create_index(
        "ix_game_archives_type_created",
        "game_archives",
        ["record_type", "source_created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_game_archives_type_created", table_name="game_archives")
    op.drop_table("game_archives")
