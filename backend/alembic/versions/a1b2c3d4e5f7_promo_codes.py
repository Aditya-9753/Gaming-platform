"""Bonus promo codes; no automatic sign-up bonus

New accounts no longer get credits automatically (one person with ten numbers collected ten
bonuses). The super admin creates promo codes instead; each player can redeem a code once.

Revision ID: a1b2c3d4e5f7
Revises: f0a1b2c3d4e5
Create Date: 2026-10-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"], unique=True)
    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("promo_code_id", sa.String(36), sa.ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemption_once"),
    )
    op.create_index("ix_promo_redemptions_promo_code_id", "promo_redemptions", ["promo_code_id"])
    op.create_index("ix_promo_redemptions_user_id", "promo_redemptions", ["user_id"])
    # A bonus saved earlier in Platform Settings would keep paying every new account
    op.execute("UPDATE system_settings SET value = '0' WHERE key = 'signup_bonus_paise'")


def downgrade() -> None:
    op.drop_table("promo_redemptions")
    op.drop_table("promo_codes")
