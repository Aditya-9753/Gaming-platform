"""Players who signed up with a mobile number: use the number as their username

Accounts created with a generated name ("player123456") get their 10-digit number instead, so
staff screens show who is playing. Public feeds keep masking names ("98***0").

Revision ID: f0a1b2c3d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-10-17
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users AS u SET username = substr(u.phone, 4)
        WHERE u.phone IS NOT NULL AND u.username LIKE 'player%' AND length(u.username) = 12
          AND NOT EXISTS (SELECT 1 FROM users o WHERE lower(o.username) = substr(u.phone, 4))
        """
    )


def downgrade() -> None:
    pass  # the generated names are not kept; the numbers stay as usernames
