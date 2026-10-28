"""Drop a duplicate index on game_rounds (game_id, round_no)

The unique constraint uq_game_rounds_game_round_no already indexes these columns, so
ix_game_rounds_game_round_no only cost disk space on the biggest table.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-10-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_game_rounds_game_round_no", table_name="game_rounds")


def downgrade() -> None:
    op.create_index("ix_game_rounds_game_round_no", "game_rounds", ["game_id", "round_no"], unique=False)
