"""Make users.email optional (username + password sign-up)

Revision ID: 6c1e2f3a4b50
Revises: 5b7c9d2e4f10
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6c1e2f3a4b50"
down_revision: Union[str, None] = "5b7c9d2e4f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(length=255), nullable=True)
    # Case-insensitive username uniqueness (login is case-insensitive)
    op.create_index(
        "ix_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_username_lower", table_name="users")
    op.execute("UPDATE users SET email = id || '@users.invalid' WHERE email IS NULL")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", existing_type=sa.String(length=255), nullable=False)
