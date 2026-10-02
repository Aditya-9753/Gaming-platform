"""Full name for staff accounts

Revision ID: 8e3a4b5c6d72
Revises: 7d2f3a4b5c61
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8e3a4b5c6d72"
down_revision: Union[str, None] = "7d2f3a4b5c61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "full_name")
