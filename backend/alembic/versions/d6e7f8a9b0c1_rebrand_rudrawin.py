"""Rebrand: Rudra247 -> RudraWin (only if the stored name is still the old default)

Revision ID: d6e7f8a9b0c1
Revises: f7b8c9d0e1f2
Create Date: 2026-10-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "f7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE system_settings SET value = 'RudraWin' WHERE key = 'platform_name' AND value = 'Rudra247'")


def downgrade() -> None:
    op.execute("UPDATE system_settings SET value = 'Rudra247' WHERE key = 'platform_name' AND value = 'RudraWin'")
