"""Admins keep day-to-day operations only; the rest becomes super-admin only

Removed from the ADMIN role: manual wallet adjustment, game configuration, system config,
audit logs, ledgers, reports/profit, partner finance and statistics, partner risk, ingest and tracking.
The seed script only adds permissions, so existing databases need this delete.

Revision ID: d4e5f6a7b8ca
Revises: c3d4e5f6a7b9
Create Date: 2026-10-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8ca"
down_revision: Union[str, None] = "c3d4e5f6a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REMOVED = ("wallet:adjust", "game:manage", "system:config", "audit:read", "ledger:read", "report:export",
           "aff:finance:read", "aff:risk:manage", "aff:ingest:manage", "aff:tracking:manage", "aff:stats:read")


def upgrade() -> None:
    codes = ", ".join(f"'{c}'" for c in REMOVED)
    op.execute(f"""
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'ADMIN')
          AND permission_id IN (SELECT id FROM permissions WHERE code IN ({codes}))
    """)


def downgrade() -> None:
    pass  # the seed script re-adds whatever ROLE_PERMISSIONS lists
