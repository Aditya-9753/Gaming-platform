"""Add round history and retention query indexes.

Revision ID: 5b7c9d2e4f10
Revises: 4f8a2c1d6e90
"""
from typing import Sequence, Union

from alembic import op


revision: str = "5b7c9d2e4f10"
down_revision: Union[str, None] = "4f8a2c1d6e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_game_rounds_game_status_created",
        "game_rounds",
        ["game_id", "status", "created_at"],
    )
    op.create_index("ix_game_rounds_created_at", "game_rounds", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_game_rounds_created_at", table_name="game_rounds")
    op.drop_index("ix_game_rounds_game_status_created", table_name="game_rounds")
