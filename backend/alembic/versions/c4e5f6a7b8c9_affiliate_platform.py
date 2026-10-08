"""Partner / affiliate platform: aff_* tables, roles, permissions, click partitions

Revision ID: c4e5f6a7b8c9
Revises: b3d4e5f6a7b8
Create Date: 2026-10-08

Reuses users / roles / permissions / role_permissions / refresh_tokens /
audit_logs / notifications / system_settings. aff_tracking_clicks is range
partitioned by month on PostgreSQL; aff_ensure_click_partitions(n) creates the
current month plus the next n months (called here and nightly by the worker).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e5f6a7b8c9"
down_revision: Union[str, None] = "b3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIGID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

# code -> (name, description, roles granted besides SUPERADMIN)
_PERMISSIONS = {
    "aff:portal": ("Partner Portal", "Use the partner portal for one's own partner account", ("PARTNER",)),
    "aff:partner:read": ("View Partners", "Look up partners, their links and statistics (read-only)", ("ADMIN", "SUPPORT", "FINANCE_ADMIN")),
    "aff:partner:manage": ("Manage Partners", "Create, approve, suspend partners and assign managers", ("ADMIN",)),
    "aff:impersonate": ("Impersonate Partner", "Open a partner's portal read-only for support", ("ADMIN", "SUPPORT")),
    "aff:tracking:manage": ("Manage Tracking", "Sources, campaigns, tracking links and promo codes of any partner", ("ADMIN",)),
    "aff:domain:manage": ("Manage Tracking Domains", "Primary and mirror tracking domains", ()),
    "aff:deal:manage": ("Manage Deals", "Commission plans and partner deals / rates", ("FINANCE_ADMIN",)),
    "aff:settlement:manage": ("Manage Settlement", "Close settlement periods", ("FINANCE_ADMIN",)),
    "aff:withdrawal:manage": ("Manage Partner Withdrawals", "Approve, reject and mark partner payouts paid", ("FINANCE_ADMIN",)),
    "aff:adjust": ("Partner Wallet Adjustments", "Request or approve maker-checker wallet adjustments", ("FINANCE_ADMIN",)),
    "aff:finance:read": ("View Partner Finance", "Partner wallets, ledger and period balances", ("ADMIN", "FINANCE_ADMIN")),
    "aff:stats:read": ("View Affiliate Statistics", "Platform-wide affiliate statistics", ("ADMIN", "FINANCE_ADMIN")),
    "aff:content:manage": ("Manage Partner Content", "PR materials and blog posts", ("ADMIN",)),
    "aff:support:manage": ("Manage Partner Support", "Partner contact requests and FAQ", ("ADMIN", "SUPPORT")),
    "aff:risk:manage": ("Manage Affiliate Risk", "Risk events, payout freezes, fraud marking", ("ADMIN", "FINANCE_ADMIN")),
    "aff:ingest:manage": ("Ingest Monitor", "Inspect and retry operator S2S events", ("ADMIN",)),
    "aff:settings:manage": ("Affiliate Settings", "Global affiliate settings", ()),
}
_EXTRA_GRANTS = {"FINANCE_ADMIN": ("audit:read",)}
_ROLES = {"PARTNER": "Affiliate partner", "FINANCE_ADMIN": "Affiliate finance: deals, settlement, payouts"}

_PARTITION_FN = """
CREATE OR REPLACE FUNCTION aff_ensure_click_partitions(months_ahead integer) RETURNS void AS $fn$
DECLARE
    start_month date := date_trunc('month', now())::date;
    m date;
    part text;
BEGIN
    FOR i IN 0..months_ahead LOOP
        m := (start_month + make_interval(months => i))::date;
        part := 'aff_tracking_clicks_' || to_char(m, 'YYYY_MM');
        IF to_regclass(part) IS NULL THEN
            EXECUTE format('CREATE TABLE %I PARTITION OF aff_tracking_clicks FOR VALUES FROM (%L) TO (%L)',
                           part, m, (m + interval '1 month')::date);
        END IF;
    END LOOP;
END;
$fn$ LANGUAGE plpgsql;
"""


def _seed_rbac() -> None:
    bind = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("description", sa.String))
    perms = sa.table("permissions", sa.column("id", sa.Integer), sa.column("code", sa.String), sa.column("name", sa.String),
                     sa.column("description", sa.String))
    links = sa.table("role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer))
    for name, desc in _ROLES.items():
        if bind.execute(sa.select(roles.c.id).where(roles.c.name == name)).first() is None:
            bind.execute(roles.insert().values(name=name, description=desc))
    for code, (name, desc, _granted) in _PERMISSIONS.items():
        if bind.execute(sa.select(perms.c.id).where(perms.c.code == code)).first() is None:
            bind.execute(perms.insert().values(code=code, name=name, description=desc))
    role_ids = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    perm_ids = dict(bind.execute(sa.select(perms.c.code, perms.c.id)).all())
    grants = [(role, code) for code, (_n, _d, granted) in _PERMISSIONS.items() for role in ("SUPERADMIN",) + tuple(granted)]
    grants += [(role, code) for role, codes in _EXTRA_GRANTS.items() for code in codes]
    for role, code in grants:
        rid, pid = role_ids.get(role), perm_ids.get(code)
        if rid is None or pid is None:
            continue
        exists = bind.execute(sa.select(links.c.role_id).where(links.c.role_id == rid, links.c.permission_id == pid)).first()
        if exists is None:
            bind.execute(links.insert().values(role_id=rid, permission_id=pid))


def upgrade() -> None:
    op.create_table('aff_analytics_daily',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('source_id', BIGID, nullable=False),
    sa.Column('campaign_id', BIGID, nullable=False),
    sa.Column('tracking_link_id', BIGID, nullable=False),
    sa.Column('stat_date', sa.Date(), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('clicks', sa.Integer(), nullable=False),
    sa.Column('unique_clicks', sa.Integer(), nullable=False),
    sa.Column('registrations', sa.Integer(), nullable=False),
    sa.Column('first_deposits', sa.Integer(), nullable=False),
    sa.Column('deposit_count', sa.Integer(), nullable=False),
    sa.Column('deposit_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('ngr', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('income', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('sub_commission', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'source_id', 'campaign_id', 'tracking_link_id', 'stat_date', 'country', name='uq_aff_analytics_daily')
    )
    op.create_index('ix_aff_ad_partner_date', 'aff_analytics_daily', ['partner_id', 'stat_date'], unique=False)
    op.create_table('aff_analytics_hourly',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('source_id', BIGID, nullable=False),
    sa.Column('campaign_id', BIGID, nullable=False),
    sa.Column('tracking_link_id', BIGID, nullable=False),
    sa.Column('date_hour', sa.DateTime(timezone=True), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('clicks', sa.Integer(), nullable=False),
    sa.Column('unique_clicks', sa.Integer(), nullable=False),
    sa.Column('registrations', sa.Integer(), nullable=False),
    sa.Column('first_deposits', sa.Integer(), nullable=False),
    sa.Column('deposit_count', sa.Integer(), nullable=False),
    sa.Column('deposit_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('ngr', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('income', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('sub_commission', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'source_id', 'campaign_id', 'tracking_link_id', 'date_hour', 'country', name='uq_aff_analytics_hourly')
    )
    op.create_index('ix_aff_ah_partner_hour', 'aff_analytics_hourly', ['partner_id', 'date_hour'], unique=False)
    op.create_table('aff_commission_plans',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('deal_type', sa.String(length=12), nullable=False),
    sa.Column('default_revshare_rate', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('default_cpa_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('min_ftd_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('hold_days', sa.Integer(), nullable=False),
    sa.Column('carryover', sa.Boolean(), nullable=False),
    sa.Column('tier_table', sa.JSON(), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("deal_type IN ('REVSHARE', 'CPA', 'HYBRID', 'TIERED')", name='ck_aff_plan_deal_type'),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_plan_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('aff_customers',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('external_customer_id', sa.String(length=64), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('status', sa.String(length=17), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'BLOCKED', 'SELF_EXCLUDED')", name='ck_aff_customer_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_customer_id')
    )
    op.create_table('aff_faqs',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('question', sa.String(length=255), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name='ck_aff_faq_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_aff_faq_status_order', 'aff_faqs', ['status', 'sort_order'], unique=False)
    op.create_table('aff_fx_rates',
    sa.Column('rate_date', sa.Date(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('rate_to_usd', sa.Numeric(precision=19, scale=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('rate_date', 'currency')
    )
    op.create_table('aff_ingest_events',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('event_type', sa.String(length=16), nullable=False),
    sa.Column('idempotency_key', sa.String(length=160), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('signature_ok', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('result_ref', sa.String(length=64), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("event_type IN ('REGISTRATION', 'DEPOSIT', 'REVENUE', 'REVERSAL')", name='ck_aff_ingest_type'),
    sa.CheckConstraint("status IN ('RECEIVED', 'PROCESSED', 'FAILED', 'IGNORED')", name='ck_aff_ingest_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_type', 'idempotency_key', name='uq_aff_ingest_key')
    )
    op.create_index('ix_aff_ingest_status_time', 'aff_ingest_events', ['status', 'received_at'], unique=False)
    op.create_table('aff_terms_versions',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('version', sa.String(length=20), nullable=False),
    sa.Column('content_url', sa.String(length=500), nullable=True),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_table('aff_tracking_clicks',
    sa.Column('click_id', sa.String(length=26), nullable=False),
    sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('tracking_link_id', BIGID, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('source_id', BIGID, nullable=False),
    sa.Column('campaign_id', BIGID, nullable=True),
    sa.Column('visitor_id', BIGID, nullable=True),
    sa.Column('ip_hash', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=400), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('region', sa.String(length=80), nullable=True),
    sa.Column('city', sa.String(length=80), nullable=True),
    sa.Column('device_type', sa.String(length=16), nullable=True),
    sa.Column('browser', sa.String(length=32), nullable=True),
    sa.Column('os', sa.String(length=32), nullable=True),
    sa.Column('referrer', sa.String(length=500), nullable=True),
    sa.Column('sub1', sa.String(length=128), nullable=True),
    sa.Column('sub2', sa.String(length=128), nullable=True),
    sa.Column('sub3', sa.String(length=128), nullable=True),
    sa.Column('sub4', sa.String(length=128), nullable=True),
    sa.Column('sub5', sa.String(length=128), nullable=True),
    sa.Column('is_bot', sa.Boolean(), nullable=False),
    sa.Column('is_unique', sa.Boolean(), nullable=False),
    sa.Column('is_fraud', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('click_id', 'clicked_at'),
    postgresql_partition_by='RANGE (clicked_at)'
    )
    op.create_index('ix_aff_click_iphash_time', 'aff_tracking_clicks', ['ip_hash', 'clicked_at'], unique=False)
    op.create_index('ix_aff_click_link_time', 'aff_tracking_clicks', ['tracking_link_id', 'clicked_at'], unique=False)
    op.create_index('ix_aff_click_partner_time', 'aff_tracking_clicks', ['partner_id', 'clicked_at'], unique=False)
    op.create_table('aff_tracking_domains',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('ssl_ok', sa.Boolean(), nullable=True),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_check_error', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'BLOCKED')", name='ck_aff_domain_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('domain')
    )
    op.create_table('aff_visitors',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('anonymous_id', sa.String(length=32), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('device_type', sa.String(length=16), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('anonymous_id')
    )
    op.create_table('aff_blog_posts',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=200), nullable=False),
    sa.Column('excerpt', sa.String(length=400), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('cover_image', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name='ck_aff_blog_status'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('aff_email_tokens',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('purpose', sa.String(length=10), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("purpose IN ('VERIFY', 'RESET')", name='ck_aff_email_token_purpose'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_aff_email_tokens_user_id'), 'aff_email_tokens', ['user_id'], unique=False)
    op.create_table('aff_export_jobs',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=11), nullable=False),
    sa.Column('file_content', sa.Text(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(length=255), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'DONE', 'FAILED')", name='ck_aff_export_status'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_export_jobs_user_id'), 'aff_export_jobs', ['user_id'], unique=False)
    op.create_table('aff_partners',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('parent_partner_id', BIGID, nullable=True),
    sa.Column('partner_code', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('signup_source', sa.String(length=9), nullable=False),
    sa.Column('manager_id', sa.String(length=36), nullable=True),
    sa.Column('subpartner_rate', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('payout_frozen', sa.Boolean(), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('locale', sa.String(length=8), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("signup_source IN ('SELF', 'ADMIN')", name='ck_aff_partner_signup_source'),
    sa.CheckConstraint("status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'BLOCKED')", name='ck_aff_partner_status'),
    sa.CheckConstraint('subpartner_rate >= 0 AND subpartner_rate <= 1', name='ck_aff_partner_subrate'),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['manager_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_code'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_aff_partners_parent_partner_id'), 'aff_partners', ['parent_partner_id'], unique=False)
    op.create_index(op.f('ix_aff_partners_status'), 'aff_partners', ['status'], unique=False)
    op.create_table('aff_settlement_periods',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('period_type', sa.String(length=11), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=11), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_by', sa.String(length=36), nullable=True),
    sa.Column('reopened_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("period_type IN ('WEEKLY', 'MONTHLY')", name='ck_aff_period_type'),
    sa.CheckConstraint("status IN ('OPEN', 'CLOSING', 'CLOSED')", name='ck_aff_period_status'),
    sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('period_type', 'start_date', name='uq_aff_period_start')
    )
    op.create_table('aff_terms_acceptances',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('terms_version_id', BIGID, nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('ip_hash', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['terms_version_id'], ['aff_terms_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'terms_version_id', name='uq_aff_terms_acceptance')
    )
    op.create_table('aff_contacts',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('reply', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('assigned_to', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('NEW', 'IN_PROGRESS', 'CLOSED')", name='ck_aff_contact_status'),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_contacts_status'), 'aff_contacts', ['status'], unique=False)
    op.create_table('aff_deposits',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('customer_id', BIGID, nullable=False),
    sa.Column('partner_id', BIGID, nullable=True),
    sa.Column('external_transaction_id', sa.String(length=64), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('amount_usd', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('fx_rate', sa.Numeric(precision=19, scale=8), nullable=False),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('is_first_deposit', sa.Boolean(), nullable=False),
    sa.Column('qualified_for_cpa', sa.Boolean(), nullable=False),
    sa.Column('is_fraud', sa.Boolean(), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'COMPLETED', 'FAILED', 'REVERSED')", name='ck_aff_dep_status'),
    sa.CheckConstraint('amount >= 0', name='ck_aff_dep_amount'),
    sa.ForeignKeyConstraint(['customer_id'], ['aff_customers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_transaction_id')
    )
    op.create_index('ix_aff_dep_customer_time', 'aff_deposits', ['customer_id', 'completed_at'], unique=False)
    op.create_index('ix_aff_dep_partner_time', 'aff_deposits', ['partner_id', 'completed_at'], unique=False)
    op.create_table('aff_manual_adjustments',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=False),
    sa.Column('requested_by', sa.String(length=36), nullable=False),
    sa.Column('approved_by', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('decision_note', sa.String(length=255), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("direction IN ('CREDIT', 'DEBIT')", name='ck_aff_adj_direction'),
    sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name='ck_aff_adj_status'),
    sa.CheckConstraint('amount > 0', name='ck_aff_adj_amount'),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_manual_adjustments_partner_id'), 'aff_manual_adjustments', ['partner_id'], unique=False)
    op.create_table('aff_partner_deals',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('plan_id', BIGID, nullable=True),
    sa.Column('deal_type', sa.String(length=12), nullable=False),
    sa.Column('revshare_rate', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('cpa_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('min_ftd_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('cpa_geo_list', sa.JSON(), nullable=True),
    sa.Column('carryover', sa.Boolean(), nullable=False),
    sa.Column('carryover_cap', sa.Numeric(precision=19, scale=4), nullable=True),
    sa.Column('hold_days', sa.Integer(), nullable=False),
    sa.Column('tier_table', sa.JSON(), nullable=True),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("deal_type IN ('REVSHARE', 'CPA', 'HYBRID', 'TIERED')", name='ck_aff_deal_type'),
    sa.CheckConstraint('cpa_amount >= 0', name='ck_aff_deal_cpa'),
    sa.CheckConstraint('hold_days >= 0', name='ck_aff_deal_hold'),
    sa.CheckConstraint('revshare_rate >= 0 AND revshare_rate <= 1', name='ck_aff_deal_rate'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['plan_id'], ['aff_commission_plans.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_aff_deal_partner_from', 'aff_partner_deals', ['partner_id', 'effective_from'], unique=False)
    op.create_table('aff_partner_period_balances',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('period_id', BIGID, nullable=False),
    sa.Column('opening_balance', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('cpa_total', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('revshare_total', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('sub_commission_total', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('adjustments_total', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('withdrawals_total', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('carryover_in', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('writeoff', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('closing_balance', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['period_id'], ['aff_settlement_periods.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'period_id', name='uq_aff_period_balance')
    )
    op.create_table('aff_partner_postbacks',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('event_type', sa.String(length=16), nullable=False),
    sa.Column('url_template', sa.String(length=1000), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("event_type IN ('REGISTRATION', 'FTD', 'DEPOSIT')", name='ck_aff_postback_event'),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_postback_status'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_partner_postbacks_partner_id'), 'aff_partner_postbacks', ['partner_id'], unique=False)
    op.create_table('aff_partner_profiles',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('first_name', sa.String(length=80), nullable=True),
    sa.Column('last_name', sa.String(length=80), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('company_name', sa.String(length=120), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=80), nullable=True),
    sa.Column('state', sa.String(length=80), nullable=True),
    sa.Column('postal_code', sa.String(length=20), nullable=True),
    sa.Column('telegram', sa.String(length=64), nullable=True),
    sa.Column('website', sa.String(length=255), nullable=True),
    sa.Column('traffic_description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id')
    )
    op.create_table('aff_player_revenue_daily',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('customer_id', BIGID, nullable=False),
    sa.Column('partner_id', BIGID, nullable=True),
    sa.Column('revenue_date', sa.Date(), nullable=False),
    sa.Column('bets', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('wins', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('bonuses', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('fees', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('chargebacks', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('ngr', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('period_id', BIGID, nullable=True),
    sa.Column('needs_commission', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['aff_customers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['period_id'], ['aff_settlement_periods.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('customer_id', 'revenue_date', name='uq_aff_rev_customer_date')
    )
    op.create_index('ix_aff_rev_dirty', 'aff_player_revenue_daily', ['needs_commission'], unique=False)
    op.create_index('ix_aff_rev_partner_date', 'aff_player_revenue_daily', ['partner_id', 'revenue_date'], unique=False)
    op.create_table('aff_risk_events',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=True),
    sa.Column('customer_id', BIGID, nullable=True),
    sa.Column('event_type', sa.String(length=48), nullable=False),
    sa.Column('risk_score', sa.Integer(), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('dedupe_key', sa.String(length=160), nullable=True),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('reviewed_by', sa.String(length=36), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("severity IN ('LOW', 'MEDIUM', 'HIGH')", name='ck_aff_risk_severity'),
    sa.CheckConstraint("status IN ('OPEN', 'REVIEWED', 'CONFIRMED', 'DISMISSED')", name='ck_aff_risk_status'),
    sa.ForeignKeyConstraint(['customer_id'], ['aff_customers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key')
    )
    op.create_index(op.f('ix_aff_risk_events_partner_id'), 'aff_risk_events', ['partner_id'], unique=False)
    op.create_index('ix_aff_risk_status_severity', 'aff_risk_events', ['status', 'severity'], unique=False)
    op.create_table('aff_sources',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('type', sa.String(length=12), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_source_status'),
    sa.CheckConstraint("type IN ('WEBSITE', 'SOCIAL', 'TELEGRAM', 'YOUTUBE', 'PAID_ADS', 'OTHER')", name='ck_aff_source_type'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_sources_partner_id'), 'aff_sources', ['partner_id'], unique=False)
    op.create_table('aff_wallets',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('available_balance', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('pending_balance', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('reserved_balance', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'FROZEN')", name='ck_aff_wallet_status'),
    sa.CheckConstraint('reserved_balance >= 0', name='ck_aff_wallet_reserved'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id')
    )
    op.create_table('aff_withdrawal_methods',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('type', sa.String(length=17), nullable=False),
    sa.Column('label', sa.String(length=60), nullable=False),
    sa.Column('account_name', sa.String(length=120), nullable=True),
    sa.Column('account_identifier_encrypted', sa.Text(), nullable=False),
    sa.Column('account_identifier_masked', sa.String(length=80), nullable=False),
    sa.Column('metadata_encrypted', sa.Text(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('usable_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_method_status'),
    sa.CheckConstraint("type IN ('EWALLET_EMAIL', 'USDT_TRC20', 'BANK', 'UPI', 'OTHER')", name='ck_aff_method_type'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_withdrawal_methods_partner_id'), 'aff_withdrawal_methods', ['partner_id'], unique=False)
    op.create_table('aff_auto_withdrawal_settings',
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('withdrawal_method_id', BIGID, nullable=True),
    sa.Column('min_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['withdrawal_method_id'], ['aff_withdrawal_methods.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('partner_id')
    )
    op.create_table('aff_campaigns',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('source_id', BIGID, nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('code', sa.String(length=24), nullable=False),
    sa.Column('destination_url', sa.String(length=500), nullable=True),
    sa.Column('blocked_countries', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_campaign_status'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_id'], ['aff_sources.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index('ix_aff_campaign_partner_source', 'aff_campaigns', ['partner_id', 'source_id'], unique=False)
    op.create_table('aff_commissions',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('customer_id', BIGID, nullable=False),
    sa.Column('deposit_id', BIGID, nullable=False),
    sa.Column('deal_id', BIGID, nullable=True),
    sa.Column('period_id', BIGID, nullable=False),
    sa.Column('commission_type', sa.String(length=14), nullable=False),
    sa.Column('revenue_date', sa.Date(), nullable=False),
    sa.Column('base_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('rate', sa.Numeric(precision=7, scale=4), nullable=False),
    sa.Column('commission_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('source_partner_id', BIGID, nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('hold_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('settled_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("commission_type IN ('CPA', 'REVSHARE', 'SUBPARTNER', 'REVERSAL')", name='ck_aff_commission_type'),
    sa.CheckConstraint("status IN ('PENDING', 'HELD', 'APPROVED', 'REVERSED')", name='ck_aff_commission_status'),
    sa.ForeignKeyConstraint(['deal_id'], ['aff_partner_deals.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['period_id'], ['aff_settlement_periods.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'customer_id', 'revenue_date', 'commission_type', 'deposit_id', 'source_partner_id', name='uq_aff_commission')
    )
    op.create_index('ix_aff_commission_period_partner', 'aff_commissions', ['period_id', 'partner_id'], unique=False)
    op.create_index('ix_aff_commission_status', 'aff_commissions', ['status'], unique=False)
    op.create_table('aff_partner_postback_logs',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_postback_id', BIGID, nullable=False),
    sa.Column('event_ref', sa.String(length=80), nullable=False),
    sa.Column('url_sent', sa.String(length=2000), nullable=False),
    sa.Column('response_code', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['partner_postback_id'], ['aff_partner_postbacks.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_postback_id', 'event_ref', name='uq_aff_pblog_event')
    )
    op.create_index('ix_aff_pblog_postback_time', 'aff_partner_postback_logs', ['partner_postback_id', 'sent_at'], unique=False)
    op.create_table('aff_reversals',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('external_reversal_id', sa.String(length=64), nullable=False),
    sa.Column('deposit_id', BIGID, nullable=True),
    sa.Column('customer_id', BIGID, nullable=False),
    sa.Column('amount_usd', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['aff_customers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['deposit_id'], ['aff_deposits.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_reversal_id')
    )
    op.create_table('aff_wallet_transactions',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('wallet_id', BIGID, nullable=False),
    sa.Column('type', sa.String(length=25), nullable=False),
    sa.Column('bucket', sa.String(length=13), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('balance_after', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('reference_type', sa.String(length=32), nullable=True),
    sa.Column('reference_id', sa.String(length=64), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('idempotency_key', sa.String(length=160), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("bucket IN ('PENDING', 'AVAILABLE', 'RESERVED')", name='ck_aff_wtx_bucket'),
    sa.CheckConstraint("direction IN ('CREDIT', 'DEBIT')", name='ck_aff_wtx_direction'),
    sa.CheckConstraint("type IN ('COMMISSION_CPA', 'COMMISSION_REVSHARE', 'SUBPARTNER_COMMISSION', 'COMMISSION_ADJUSTMENT', 'PERIOD_SETTLE', 'CARRYOVER_WRITEOFF', 'WITHDRAWAL_RESERVE', 'WITHDRAWAL_RELEASE', 'WITHDRAWAL_PAID', 'MANUAL_ADJUSTMENT')", name='ck_aff_wtx_type'),
    sa.CheckConstraint('amount > 0', name='ck_aff_wtx_amount'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['wallet_id'], ['aff_wallets.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_aff_wtx_reference', 'aff_wallet_transactions', ['reference_type', 'reference_id'], unique=False)
    op.create_index('ix_aff_wtx_wallet_created', 'aff_wallet_transactions', ['wallet_id', 'created_at'], unique=False)
    op.create_table('aff_withdrawals',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('wallet_id', BIGID, nullable=False),
    sa.Column('withdrawal_method_id', BIGID, nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('fee', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('net_amount', sa.Numeric(precision=19, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('idempotency_key', sa.String(length=160), nullable=False),
    sa.Column('destination_masked', sa.String(length=80), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.String(length=36), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.String(length=255), nullable=True),
    sa.Column('external_payment_reference', sa.String(length=120), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("source IN ('MANUAL', 'AUTO')", name='ck_aff_wd_source'),
    sa.CheckConstraint("status IN ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'PROCESSING', 'COMPLETED', 'REJECTED', 'CANCELLED', 'FAILED')", name='ck_aff_wd_status'),
    sa.CheckConstraint('amount > 0', name='ck_aff_wd_amount'),
    sa.CheckConstraint('fee >= 0', name='ck_aff_wd_fee'),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['wallet_id'], ['aff_wallets.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['withdrawal_method_id'], ['aff_withdrawal_methods.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_aff_wd_partner_time', 'aff_withdrawals', ['partner_id', 'requested_at'], unique=False)
    op.create_index('ix_aff_wd_status', 'aff_withdrawals', ['status'], unique=False)
    op.create_table('aff_pr_materials',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=True),
    sa.Column('campaign_id', BIGID, nullable=True),
    sa.Column('type', sa.String(length=11), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('file_url', sa.Text(), nullable=True),
    sa.Column('body_text', sa.Text(), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('geo', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('reviewed_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name='ck_aff_pr_status'),
    sa.CheckConstraint("type IN ('BANNER', 'LANDING', 'VIDEO', 'TEXT')", name='ck_aff_pr_type'),
    sa.ForeignKeyConstraint(['campaign_id'], ['aff_campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_aff_pr_status_type', 'aff_pr_materials', ['status', 'type'], unique=False)
    op.create_table('aff_tracking_links',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('source_id', BIGID, nullable=False),
    sa.Column('campaign_id', BIGID, nullable=True),
    sa.Column('link_code', sa.String(length=24), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('destination_url', sa.String(length=500), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_link_status'),
    sa.ForeignKeyConstraint(['campaign_id'], ['aff_campaigns.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_id'], ['aff_sources.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('link_code')
    )
    op.create_index('ix_aff_link_partner_source_campaign', 'aff_tracking_links', ['partner_id', 'source_id', 'campaign_id'], unique=False)
    op.create_table('aff_withdrawal_status_history',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('withdrawal_id', BIGID, nullable=False),
    sa.Column('from_status', sa.String(length=16), nullable=True),
    sa.Column('to_status', sa.String(length=16), nullable=False),
    sa.Column('changed_by', sa.String(length=36), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['withdrawal_id'], ['aff_withdrawals.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_withdrawal_status_history_withdrawal_id'), 'aff_withdrawal_status_history', ['withdrawal_id'], unique=False)
    op.create_table('aff_promo_codes',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('tracking_link_id', BIGID, nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'ARCHIVED')", name='ck_aff_promo_status'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tracking_link_id'], ['aff_tracking_links.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_aff_promo_codes_partner_id'), 'aff_promo_codes', ['partner_id'], unique=False)
    op.create_table('aff_qr_codes',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('tracking_link_id', BIGID, nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('image_url', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tracking_link_id'], ['aff_tracking_links.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aff_qr_codes_tracking_link_id'), 'aff_qr_codes', ['tracking_link_id'], unique=False)
    op.create_table('aff_registrations',
    sa.Column('id', BIGID, autoincrement=True, nullable=False),
    sa.Column('customer_id', BIGID, nullable=False),
    sa.Column('partner_id', BIGID, nullable=False),
    sa.Column('source_id', BIGID, nullable=True),
    sa.Column('campaign_id', BIGID, nullable=True),
    sa.Column('tracking_link_id', BIGID, nullable=True),
    sa.Column('promo_code_id', BIGID, nullable=True),
    sa.Column('click_id', sa.String(length=26), nullable=True),
    sa.Column('visitor_id', BIGID, nullable=True),
    sa.Column('attribution_type', sa.String(length=10), nullable=False),
    sa.Column('sub1', sa.String(length=128), nullable=True),
    sa.Column('sub2', sa.String(length=128), nullable=True),
    sa.Column('sub3', sa.String(length=128), nullable=True),
    sa.Column('sub4', sa.String(length=128), nullable=True),
    sa.Column('sub5', sa.String(length=128), nullable=True),
    sa.Column('country', sa.String(length=2), nullable=True),
    sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("attribution_type IN ('CLICK', 'PROMO', 'MANUAL')", name='ck_aff_reg_attribution'),
    sa.CheckConstraint("status IN ('ACTIVE', 'FRAUD')", name='ck_aff_reg_status'),
    sa.ForeignKeyConstraint(['campaign_id'], ['aff_campaigns.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['customer_id'], ['aff_customers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['partner_id'], ['aff_partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['promo_code_id'], ['aff_promo_codes.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['source_id'], ['aff_sources.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tracking_link_id'], ['aff_tracking_links.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['visitor_id'], ['aff_visitors.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('customer_id')
    )
    op.create_index('ix_aff_reg_partner_time', 'aff_registrations', ['partner_id', 'registered_at'], unique=False)
    op.create_index(op.f('ix_aff_registrations_click_id'), 'aff_registrations', ['click_id'], unique=False)
    op.create_index(op.f('ix_aff_registrations_tracking_link_id'), 'aff_registrations', ['tracking_link_id'], unique=False)

    plans = sa.table("aff_commission_plans", sa.column("name", sa.String), sa.column("deal_type", sa.String),
                     sa.column("default_revshare_rate", sa.Numeric), sa.column("default_cpa_amount", sa.Numeric),
                     sa.column("min_ftd_amount", sa.Numeric), sa.column("hold_days", sa.Integer), sa.column("carryover", sa.Boolean),
                     sa.column("description", sa.String), sa.column("status", sa.String))
    op.bulk_insert(plans, [
        {"name": "Revshare 50%", "deal_type": "REVSHARE", "default_revshare_rate": 0.5, "default_cpa_amount": 0,
         "min_ftd_amount": 0, "hold_days": 14, "carryover": True,
         "description": "Default: 50% of player NGR, negative balance carried over", "status": "ACTIVE"},
    ])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(_PARTITION_FN)
        op.execute("SELECT aff_ensure_click_partitions(3)")
        # rows outside the prepared months still have a home
        op.execute("CREATE TABLE IF NOT EXISTS aff_tracking_clicks_default PARTITION OF aff_tracking_clicks DEFAULT")

    _seed_rbac()


def downgrade() -> None:
    bind = op.get_bind()
    codes = list(_PERMISSIONS)
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN :codes)")
                 .bindparams(sa.bindparam("codes", expanding=True)), {"codes": codes})
    bind.execute(sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(sa.bindparam("codes", expanding=True)),
                 {"codes": codes})
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name = 'FINANCE_ADMIN')"))
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS aff_ensure_click_partitions(integer)")
    op.drop_index(op.f('ix_aff_registrations_tracking_link_id'), table_name='aff_registrations')
    op.drop_index(op.f('ix_aff_registrations_click_id'), table_name='aff_registrations')
    op.drop_index('ix_aff_reg_partner_time', table_name='aff_registrations')
    op.drop_table('aff_registrations')
    op.drop_index(op.f('ix_aff_qr_codes_tracking_link_id'), table_name='aff_qr_codes')
    op.drop_table('aff_qr_codes')
    op.drop_index(op.f('ix_aff_promo_codes_partner_id'), table_name='aff_promo_codes')
    op.drop_table('aff_promo_codes')
    op.drop_index(op.f('ix_aff_withdrawal_status_history_withdrawal_id'), table_name='aff_withdrawal_status_history')
    op.drop_table('aff_withdrawal_status_history')
    op.drop_index('ix_aff_link_partner_source_campaign', table_name='aff_tracking_links')
    op.drop_table('aff_tracking_links')
    op.drop_index('ix_aff_pr_status_type', table_name='aff_pr_materials')
    op.drop_table('aff_pr_materials')
    op.drop_index('ix_aff_wd_status', table_name='aff_withdrawals')
    op.drop_index('ix_aff_wd_partner_time', table_name='aff_withdrawals')
    op.drop_table('aff_withdrawals')
    op.drop_index('ix_aff_wtx_wallet_created', table_name='aff_wallet_transactions')
    op.drop_index('ix_aff_wtx_reference', table_name='aff_wallet_transactions')
    op.drop_table('aff_wallet_transactions')
    op.drop_table('aff_reversals')
    op.drop_index('ix_aff_pblog_postback_time', table_name='aff_partner_postback_logs')
    op.drop_table('aff_partner_postback_logs')
    op.drop_index('ix_aff_commission_status', table_name='aff_commissions')
    op.drop_index('ix_aff_commission_period_partner', table_name='aff_commissions')
    op.drop_table('aff_commissions')
    op.drop_index('ix_aff_campaign_partner_source', table_name='aff_campaigns')
    op.drop_table('aff_campaigns')
    op.drop_table('aff_auto_withdrawal_settings')
    op.drop_index(op.f('ix_aff_withdrawal_methods_partner_id'), table_name='aff_withdrawal_methods')
    op.drop_table('aff_withdrawal_methods')
    op.drop_table('aff_wallets')
    op.drop_index(op.f('ix_aff_sources_partner_id'), table_name='aff_sources')
    op.drop_table('aff_sources')
    op.drop_index('ix_aff_risk_status_severity', table_name='aff_risk_events')
    op.drop_index(op.f('ix_aff_risk_events_partner_id'), table_name='aff_risk_events')
    op.drop_table('aff_risk_events')
    op.drop_index('ix_aff_rev_partner_date', table_name='aff_player_revenue_daily')
    op.drop_index('ix_aff_rev_dirty', table_name='aff_player_revenue_daily')
    op.drop_table('aff_player_revenue_daily')
    op.drop_table('aff_partner_profiles')
    op.drop_index(op.f('ix_aff_partner_postbacks_partner_id'), table_name='aff_partner_postbacks')
    op.drop_table('aff_partner_postbacks')
    op.drop_table('aff_partner_period_balances')
    op.drop_index('ix_aff_deal_partner_from', table_name='aff_partner_deals')
    op.drop_table('aff_partner_deals')
    op.drop_index(op.f('ix_aff_manual_adjustments_partner_id'), table_name='aff_manual_adjustments')
    op.drop_table('aff_manual_adjustments')
    op.drop_index('ix_aff_dep_partner_time', table_name='aff_deposits')
    op.drop_index('ix_aff_dep_customer_time', table_name='aff_deposits')
    op.drop_table('aff_deposits')
    op.drop_index(op.f('ix_aff_contacts_status'), table_name='aff_contacts')
    op.drop_table('aff_contacts')
    op.drop_table('aff_terms_acceptances')
    op.drop_table('aff_settlement_periods')
    op.drop_index(op.f('ix_aff_partners_status'), table_name='aff_partners')
    op.drop_index(op.f('ix_aff_partners_parent_partner_id'), table_name='aff_partners')
    op.drop_table('aff_partners')
    op.drop_index(op.f('ix_aff_export_jobs_user_id'), table_name='aff_export_jobs')
    op.drop_table('aff_export_jobs')
    op.drop_index(op.f('ix_aff_email_tokens_user_id'), table_name='aff_email_tokens')
    op.drop_table('aff_email_tokens')
    op.drop_table('aff_blog_posts')
    op.drop_table('aff_visitors')
    op.drop_table('aff_tracking_domains')
    op.drop_index('ix_aff_click_partner_time', table_name='aff_tracking_clicks')
    op.drop_index('ix_aff_click_link_time', table_name='aff_tracking_clicks')
    op.drop_index('ix_aff_click_iphash_time', table_name='aff_tracking_clicks')
    op.drop_table('aff_tracking_clicks')
    op.drop_table('aff_terms_versions')
    op.drop_index('ix_aff_ingest_status_time', table_name='aff_ingest_events')
    op.drop_table('aff_ingest_events')
    op.drop_table('aff_fx_rates')
    op.drop_index('ix_aff_faq_status_order', table_name='aff_faqs')
    op.drop_table('aff_faqs')
    op.drop_table('aff_customers')
    op.drop_table('aff_commission_plans')
    op.drop_index('ix_aff_ah_partner_hour', table_name='aff_analytics_hourly')
    op.drop_table('aff_analytics_hourly')
    op.drop_index('ix_aff_ad_partner_date', table_name='aff_analytics_daily')
    op.drop_table('aff_analytics_daily')
    # roles stay while users still hold them
    bind.execute(sa.text("DELETE FROM roles WHERE name IN ('PARTNER', 'FINANCE_ADMIN') AND id NOT IN (SELECT role_id FROM users)"))
