"""Sign-in with a mobile number (users.phone) and rebrand RudraWin -> RunWin

Revision ID: e8f9a0b1c2d3
Revises: d6e7f8a9b0c1
Create Date: 2026-10-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stored as "+91" + 10 digits; optional for accounts made before phone sign-up existed
    op.add_column("users", sa.Column("phone", sa.String(length=16), nullable=True))
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    # Only when the super admin has not chosen a different name
    op.execute("UPDATE system_settings SET value = 'RunWin' WHERE key = 'platform_name' AND value IN ('RudraWin', 'Rudra247')")


def downgrade() -> None:
    op.execute("UPDATE system_settings SET value = 'RudraWin' WHERE key = 'platform_name' AND value = 'RunWin'")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "phone")
