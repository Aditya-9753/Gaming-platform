"""Remember how each account does its second factor (totp | email)

Revision ID: 7d2f3a4b5c61
Revises: 6c1e2f3a4b50
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7d2f3a4b5c61"
down_revision: Union[str, None] = "6c1e2f3a4b50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("two_factor_method", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "two_factor_method")
