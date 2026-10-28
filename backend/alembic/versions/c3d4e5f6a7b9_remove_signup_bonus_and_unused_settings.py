"""Remove the sign-up bonus and settings rows nothing reads

New accounts start with nothing (credits come only from promo codes and the daily bonus).
The seed script used to insert signup_bonus_paise = 10000 after the earlier migration had
set it to 0, so new production databases paid every account again. The other four keys
were seeded but never read by any code.

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-10-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b9"
down_revision: Union[str, None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNUSED_KEYS = ("signup_bonus_paise", "daily_faucet_paise", "faucet_cooldown_hours", "platform_mode",
               "responsible_gaming_max_daily_bet")


def upgrade() -> None:
    keys = ", ".join(f"'{k}'" for k in UNUSED_KEYS)
    op.execute(f"DELETE FROM system_settings WHERE key IN ({keys})")


def downgrade() -> None:
    pass  # the rows were unused; nothing to restore
