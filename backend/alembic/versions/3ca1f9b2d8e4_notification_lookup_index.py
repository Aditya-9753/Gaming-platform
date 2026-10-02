"""Add composite index for notification inbox lookups.

Revision ID: 3ca1f9b2d8e4
Revises: 1d12ab34ef56
"""
from typing import Sequence, Union

from alembic import op


revision: str = "3ca1f9b2d8e4"
down_revision: Union[str, None] = "1d12ab34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_notifications_user_read_created",
        "notifications",
        ["user_id", "is_read", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_user_read_created",
        table_name="notifications",
    )
