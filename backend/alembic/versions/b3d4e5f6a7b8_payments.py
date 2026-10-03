"""Payments: collection accounts, deposits, bank credits, beneficiaries, withdrawals

Revision ID: b3d4e5f6a7b8
Revises: a1c2d3e4f5a6
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3d4e5f6a7b8"
down_revision: Union[str, None] = "a1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = sa.DateTime(timezone=True)

# permission code -> (name, description, roles granted)
_PERMISSIONS = {
    "payment:deposit": ("Deposit", "Create deposit requests and submit payment UTRs", ("USER",)),
    "payment:withdraw": ("Withdraw", "Add payout accounts and request withdrawals", ("USER",)),
    "payment:read": ("View Payments", "View deposits, withdrawals and bank credits", ("ADMIN", "SUPPORT", "AUDITOR", "SUPERADMIN")),
    "payment:manage": ("Manage Payments", "Own QR collection accounts; verify or reject deposits paid into them", ("ADMIN", "SUPERADMIN")),
}


def upgrade() -> None:
    op.add_column("wallets", sa.Column("pending_withdrawal", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("chk_wallet_positive_pending_withdrawal", "wallets", "pending_withdrawal >= 0")
    op.add_column("users", sa.Column("transaction_pin_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("transaction_pin_set_at", _TS, nullable=True))

    op.create_table(
        "payment_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("upi_id", sa.String(100), nullable=False, index=True),
        sa.Column("payee_name", sa.String(100), nullable=False),
        sa.Column("qr_image", sa.Text(), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("min_amount_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("max_amount_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("daily_limit_paise", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", _TS, nullable=True),
        sa.Column("review_note", sa.String(255), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("min_amount_paise >= 0", name="chk_payacct_min"),
        sa.CheckConstraint("max_amount_paise >= 0", name="chk_payacct_max"),
        sa.CheckConstraint("daily_limit_paise >= 0", name="chk_payacct_daily"),
    )

    op.create_table(
        "bank_credits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("provider_event_id", sa.String(100), nullable=True),
        sa.Column("utr", sa.String(40), nullable=False, unique=True, index=True),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("payment_account_id", sa.String(36), sa.ForeignKey("payment_accounts.id", ondelete="RESTRICT"), nullable=True, index=True),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column("payer_name", sa.String(100), nullable=True),
        sa.Column("payer_vpa", sa.String(100), nullable=True),
        sa.Column("received_at", _TS, nullable=True),
        sa.Column("status", sa.String(12), nullable=False, index=True),
        sa.Column("deposit_id", sa.String(36), nullable=True, index=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_bank_credit_provider_event"),
        sa.CheckConstraint("amount_paise > 0", name="chk_bank_credit_amount_positive"),
    )

    op.create_table(
        "deposits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("wallet_id", sa.String(36), sa.ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_account_id", sa.String(36), sa.ForeignKey("payment_accounts.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("credited_amount_paise", sa.BigInteger(), nullable=True),
        sa.Column("reference", sa.String(20), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(12), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False, index=True),
        sa.Column("user_utr", sa.String(40), nullable=True, index=True),
        sa.Column("bank_credit_id", sa.String(36), sa.ForeignKey("bank_credits.id", ondelete="RESTRICT"), nullable=True, unique=True),
        sa.Column("verification_method", sa.String(20), nullable=True),
        sa.Column("verified_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_ip", sa.String(50), nullable=True),
        sa.Column("expires_at", _TS, nullable=False),
        sa.Column("credited_at", _TS, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_deposit_user_idem"),
        sa.CheckConstraint("amount_paise > 0", name="chk_deposit_amount_positive"),
    )
    op.create_index("ix_deposits_account_state", "deposits", ["payment_account_id", "state"])
    op.create_index("ix_deposits_created", "deposits", ["created_at"])

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.String(255), nullable=True),
        sa.Column("source_ip", sa.String(50), nullable=True),
        sa.Column("received_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )

    op.create_table(
        "beneficiaries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("holder_name", sa.String(100), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column("details_encrypted", sa.Text(), nullable=False),
        sa.Column("masked", sa.String(60), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("cooling_until", _TS, nullable=False),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("removed_at", _TS, nullable=True),
    )

    op.create_table(
        "withdrawals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("wallet_id", sa.String(36), sa.ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("beneficiary_id", sa.String(36), sa.ForeignKey("beneficiaries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_flags", sa.JSON(), nullable=True),
        sa.Column("payout_details_encrypted", sa.Text(), nullable=False),
        sa.Column("payout_masked", sa.String(120), nullable=False),
        sa.Column("payout_reference", sa.String(64), nullable=True, unique=True),
        sa.Column("initiated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("initiated_at", _TS, nullable=True),
        sa.Column("completed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", _TS, nullable=True),
        sa.Column("rejected_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rejected_at", _TS, nullable=True),
        sa.Column("reject_reason", sa.String(500), nullable=True),
        sa.Column("admin_note", sa.String(500), nullable=True),
        sa.Column("request_ip", sa.String(50), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_withdrawal_user_idem"),
        sa.CheckConstraint("amount_paise > 0", name="chk_withdrawal_amount_positive"),
    )
    op.create_index("ix_withdrawals_state_created", "withdrawals", ["state", "created_at"])

    op.create_table(
        "payment_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(12), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False, index=True),
        sa.Column("from_state", sa.String(20), nullable=True),
        sa.Column("to_state", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_type", sa.String(12), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.func.now(), nullable=False),
    )

    # Grant the new permissions to the built-in roles of an existing database
    # (plain idempotent SQL so `alembic upgrade --sql` renders it too; values are constants above)
    for code, (name, description, roles) in _PERMISSIONS.items():
        op.execute(
            sa.text(
                "INSERT INTO permissions (code, name, description, created_at) "
                "SELECT :c, :n, :d, now() WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)"
            ).bindparams(c=code, n=name, d=description)
        )
        role_list = ", ".join(f"'{r}'" for r in roles)
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id, created_at) "
                "SELECT r.id, p.id, now() FROM roles r, permissions p "
                f"WHERE p.code = :c AND r.name IN ({role_list}) "
                "AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
            ).bindparams(c=code)
        )


def downgrade() -> None:
    codes = ", ".join(f"'{c}'" for c in _PERMISSIONS)
    op.execute(f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({codes}))")
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")
    op.drop_table("payment_status_history")
    op.drop_index("ix_withdrawals_state_created", table_name="withdrawals")
    op.drop_table("withdrawals")
    op.drop_table("beneficiaries")
    op.drop_table("payment_webhook_events")
    op.drop_index("ix_deposits_created", table_name="deposits")
    op.drop_index("ix_deposits_account_state", table_name="deposits")
    op.drop_table("deposits")
    op.drop_table("bank_credits")
    op.drop_table("payment_accounts")
    op.drop_column("users", "transaction_pin_set_at")
    op.drop_column("users", "transaction_pin_hash")
    op.drop_constraint("chk_wallet_positive_pending_withdrawal", "wallets", type_="check")
    op.drop_column("wallets", "pending_withdrawal")
