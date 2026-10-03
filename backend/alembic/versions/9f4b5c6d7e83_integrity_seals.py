"""AES-256-GCM integrity seals on ledger and audit rows

Revision ID: 9f4b5c6d7e83
Revises: 8e3a4b5c6d72
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f4b5c6d7e83"
down_revision: Union[str, None] = "8e3a4b5c6d72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wallet_transactions", sa.Column("integrity_seal", sa.Text(), nullable=True))
    op.add_column("audit_logs", sa.Column("integrity_seal", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "integrity_seal")
    op.drop_column("wallet_transactions", "integrity_seal")
