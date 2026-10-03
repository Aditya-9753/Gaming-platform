"""Rebrand: GameZone -> Rudra247 (only if the stored name is still the old default)

Revision ID: a1c2d3e4f5a6
Revises: 9f4b5c6d7e83
Create Date: 2026-10-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1c2d3e4f5a6"
down_revision: Union[str, None] = "9f4b5c6d7e83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE system_settings SET value = 'Rudra247' WHERE key = 'platform_name' AND value = 'GameZone'")


def downgrade() -> None:
    op.execute("UPDATE system_settings SET value = 'GameZone' WHERE key = 'platform_name' AND value = 'Rudra247'")
