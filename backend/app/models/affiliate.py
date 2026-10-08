"""Partner / affiliate platform tables (``aff_*``).

Reuses the platform's ``users``, ``roles``, ``permissions``,
``role_permissions``, ``refresh_tokens`` (sessions), ``audit_logs``,
``notifications`` and ``system_settings`` tables; everything else the
affiliate product needs lives here.

Conventions
-----------
* ids: BIGINT identity (INTEGER on SQLite so tests autoincrement).
* money: NUMERIC(19,4) handled as ``Decimal``; rates NUMERIC(7,4) (0.5000 = 50%).
* timestamps: timezone-aware, UTC.
* status columns: VARCHAR + CHECK constraint generated from the Python enums.
* financial rows are never hard-deleted (status columns instead); the wallet
  ledger is append-only (enforced by ORM events below and DB grants).
* ``aff_tracking_clicks`` is range-partitioned by month on PostgreSQL (see
  the migration); its primary key is (click_id, clicked_at) and it has no
  foreign keys, so referential checks are done by the application.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.affiliate.constants import (
    ApprovalStatus,
    AttributionType,
    Bucket,
    CommissionStatus,
    CommissionType,
    ContactStatus,
    ContentStatus,
    CustomerStatus,
    DealType,
    DepositStatus,
    Direction,
    DomainStatus,
    EmailTokenPurpose,
    ExportStatus,
    IngestEventType,
    IngestStatus,
    LedgerType,
    MaterialType,
    MethodType,
    PartnerStatus,
    PeriodStatus,
    PeriodType,
    PostbackEvent,
    RecordStatus,
    RegistrationStatus,
    RiskSeverity,
    RiskStatus,
    SignupSource,
    SourceType,
    WalletStatus,
    WithdrawalSource,
    WithdrawalStatus,
)
from app.core.database import Base

# BIGINT on PostgreSQL; plain INTEGER on SQLite so "INTEGER PRIMARY KEY" autoincrements in tests
BigId = BigInteger().with_variant(Integer(), "sqlite")
Money = Numeric(19, 4)
Rate = Numeric(7, 4)
TS = DateTime(timezone=True)


def _enum(enum_cls: type[PyEnum], name: str) -> SAEnum:
    """VARCHAR + CHECK constraint (portable, no native PG enum types to migrate)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=max(len(m.value) for m in enum_cls) + 4,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def _pk() -> Mapped[int]:
    return mapped_column(BigId, primary_key=True, autoincrement=True)


def _created() -> Mapped[datetime]:
    return mapped_column(TS, server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(TS, server_default=func.now(), onupdate=func.now(), nullable=False)


def _user_fk(nullable: bool = True, ondelete: str = "SET NULL") -> Any:
    return mapped_column(String(36), ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def _partner_fk(nullable: bool = False, index: bool = True) -> Any:
    return mapped_column(BigId, ForeignKey("aff_partners.id", ondelete="RESTRICT"), nullable=nullable, index=index)


# ===========================================================================
# 12.1 Identity extras (users / roles / sessions / 2FA secret are platform tables)
# ===========================================================================


class AffEmailToken(Base):
    """Email verification / password reset tokens (hash only)."""

    __tablename__ = "aff_email_tokens"

    id: Mapped[int] = _pk()
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[EmailTokenPurpose] = mapped_column(_enum(EmailTokenPurpose, "ck_aff_email_token_purpose"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = _created()


class AffTermsVersion(Base):
    __tablename__ = "aff_terms_versions"

    id: Mapped[int] = _pk()
    version: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    content_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = _created()


class AffTermsAcceptance(Base):
    __tablename__ = "aff_terms_acceptances"
    __table_args__ = (UniqueConstraint("user_id", "terms_version_id", name="uq_aff_terms_acceptance"),)

    id: Mapped[int] = _pk()
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    terms_version_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_terms_versions.id", ondelete="RESTRICT"), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


# ===========================================================================
# 12.2 Partners
# ===========================================================================


class AffPartner(Base):
    __tablename__ = "aff_partners"

    id: Mapped[int] = _pk()
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, unique=True)
    parent_partner_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_partners.id", ondelete="RESTRICT"), nullable=True, index=True)
    partner_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    status: Mapped[PartnerStatus] = mapped_column(_enum(PartnerStatus, "ck_aff_partner_status"), nullable=False, index=True)
    signup_source: Mapped[SignupSource] = mapped_column(_enum(SignupSource, "ck_aff_partner_signup_source"), nullable=False)
    manager_id: Mapped[Optional[str]] = _user_fk()
    # Share of each direct subpartner's positive period commission paid to this (master) partner
    subpartner_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False, default=Decimal("0"))
    payout_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    approved_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    approved_by: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        CheckConstraint("subpartner_rate >= 0 AND subpartner_rate <= 1", name="ck_aff_partner_subrate"),
    )


class AffPartnerProfile(Base):
    __tablename__ = "aff_partner_profiles"

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_partners.id", ondelete="CASCADE"), nullable=False, unique=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(80))
    last_name: Mapped[Optional[str]] = mapped_column(String(80))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    company_name: Mapped[Optional[str]] = mapped_column(String(120))
    country: Mapped[Optional[str]] = mapped_column(String(2))
    address: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(80))
    state: Mapped[Optional[str]] = mapped_column(String(80))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    telegram: Mapped[Optional[str]] = mapped_column(String(64))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    traffic_description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffCommissionPlan(Base):
    """Deal templates admins pick from; the terms are copied into aff_partner_deals."""

    __tablename__ = "aff_commission_plans"

    id: Mapped[int] = _pk()
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    deal_type: Mapped[DealType] = mapped_column(_enum(DealType, "ck_aff_plan_deal_type"), nullable=False)
    default_revshare_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False, default=Decimal("0"))
    default_cpa_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    min_ftd_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    hold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    carryover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tier_table: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_plan_status"), nullable=False, default=RecordStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffPartnerDeal(Base):
    """A partner's commercial terms over a date range (history kept; no overlaps)."""

    __tablename__ = "aff_partner_deals"
    __table_args__ = (
        Index("ix_aff_deal_partner_from", "partner_id", "effective_from"),
        CheckConstraint("revshare_rate >= 0 AND revshare_rate <= 1", name="ck_aff_deal_rate"),
        CheckConstraint("cpa_amount >= 0", name="ck_aff_deal_cpa"),
        CheckConstraint("hold_days >= 0", name="ck_aff_deal_hold"),
    )

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    plan_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_commission_plans.id", ondelete="SET NULL"), nullable=True)
    deal_type: Mapped[DealType] = mapped_column(_enum(DealType, "ck_aff_deal_type"), nullable=False)
    revshare_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False, default=Decimal("0"))
    cpa_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    min_ftd_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    cpa_geo_list: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    carryover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    carryover_cap: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    hold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    tier_table: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = _created()


# ===========================================================================
# 12.3 Marketing and tracking
# ===========================================================================


class AffTrackingDomain(Base):
    __tablename__ = "aff_tracking_domains"

    id: Mapped[int] = _pk()
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[DomainStatus] = mapped_column(_enum(DomainStatus, "ck_aff_domain_status"), nullable=False, default=DomainStatus.ACTIVE)
    ssl_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    last_check_error: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffSource(Base):
    __tablename__ = "aff_sources"

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[SourceType] = mapped_column(_enum(SourceType, "ck_aff_source_type"), nullable=False, default=SourceType.OTHER)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_source_status"), nullable=False, default=RecordStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffCampaign(Base):
    __tablename__ = "aff_campaigns"
    __table_args__ = (Index("ix_aff_campaign_partner_source", "partner_id", "source_id"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    source_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_sources.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    destination_url: Mapped[Optional[str]] = mapped_column(String(500))
    blocked_countries: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_campaign_status"), nullable=False, default=RecordStatus.ACTIVE)
    start_at: Mapped[Optional[datetime]] = mapped_column(TS)
    end_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffTrackingLink(Base):
    __tablename__ = "aff_tracking_links"
    __table_args__ = (Index("ix_aff_link_partner_source_campaign", "partner_id", "source_id", "campaign_id"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    source_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_sources.id", ondelete="RESTRICT"), nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_campaigns.id", ondelete="RESTRICT"), nullable=True)
    link_code: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    destination_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_link_status"), nullable=False, default=RecordStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffPromoCode(Base):
    __tablename__ = "aff_promo_codes"

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk()
    tracking_link_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_tracking_links.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_promo_status"), nullable=False, default=RecordStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffQrCode(Base):
    __tablename__ = "aff_qr_codes"

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    tracking_link_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_tracking_links.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # PNG data URL rendered server side (small; S3 can replace this later)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


class AffVisitor(Base):
    __tablename__ = "aff_visitors"

    id: Mapped[int] = _pk()
    anonymous_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    first_seen_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    device_type: Mapped[Optional[str]] = mapped_column(String(16))


class AffTrackingClick(Base):
    """One row per click. Partitioned by month on PostgreSQL; no FKs (enforced in app)."""

    __tablename__ = "aff_tracking_clicks"
    __table_args__ = (
        Index("ix_aff_click_partner_time", "partner_id", "clicked_at"),
        Index("ix_aff_click_link_time", "tracking_link_id", "clicked_at"),
        Index("ix_aff_click_iphash_time", "ip_hash", "clicked_at"),
        {"postgresql_partition_by": "RANGE (clicked_at)"},
    )

    click_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    clicked_at: Mapped[datetime] = mapped_column(TS, primary_key=True)
    tracking_link_id: Mapped[int] = mapped_column(BigId, nullable=False)
    partner_id: Mapped[int] = mapped_column(BigId, nullable=False)
    source_id: Mapped[int] = mapped_column(BigId, nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(BigId, nullable=True)
    visitor_id: Mapped[Optional[int]] = mapped_column(BigId, nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(400))
    country: Mapped[Optional[str]] = mapped_column(String(2))
    region: Mapped[Optional[str]] = mapped_column(String(80))
    city: Mapped[Optional[str]] = mapped_column(String(80))
    device_type: Mapped[Optional[str]] = mapped_column(String(16))
    browser: Mapped[Optional[str]] = mapped_column(String(32))
    os: Mapped[Optional[str]] = mapped_column(String(32))
    referrer: Mapped[Optional[str]] = mapped_column(String(500))
    sub1: Mapped[Optional[str]] = mapped_column(String(128))
    sub2: Mapped[Optional[str]] = mapped_column(String(128))
    sub3: Mapped[Optional[str]] = mapped_column(String(128))
    sub4: Mapped[Optional[str]] = mapped_column(String(128))
    sub5: Mapped[Optional[str]] = mapped_column(String(128))
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ===========================================================================
# 12.4 Customers, deposits and ingest
# ===========================================================================


class AffCustomer(Base):
    __tablename__ = "aff_customers"

    id: Mapped[int] = _pk()
    external_customer_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    status: Mapped[CustomerStatus] = mapped_column(_enum(CustomerStatus, "ck_aff_customer_status"), nullable=False, default=CustomerStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffRegistration(Base):
    """Attribution of a customer to a partner. Frozen once written (status aside)."""

    __tablename__ = "aff_registrations"
    __table_args__ = (Index("ix_aff_reg_partner_time", "partner_id", "registered_at"),)

    id: Mapped[int] = _pk()
    customer_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_customers.id", ondelete="RESTRICT"), nullable=False, unique=True)
    partner_id: Mapped[int] = _partner_fk(index=False)
    source_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_sources.id", ondelete="RESTRICT"))
    campaign_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_campaigns.id", ondelete="RESTRICT"))
    tracking_link_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_tracking_links.id", ondelete="RESTRICT"), index=True)
    promo_code_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_promo_codes.id", ondelete="RESTRICT"))
    click_id: Mapped[Optional[str]] = mapped_column(String(26), index=True)
    visitor_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_visitors.id", ondelete="SET NULL"))
    attribution_type: Mapped[AttributionType] = mapped_column(_enum(AttributionType, "ck_aff_reg_attribution"), nullable=False)
    sub1: Mapped[Optional[str]] = mapped_column(String(128))
    sub2: Mapped[Optional[str]] = mapped_column(String(128))
    sub3: Mapped[Optional[str]] = mapped_column(String(128))
    sub4: Mapped[Optional[str]] = mapped_column(String(128))
    sub5: Mapped[Optional[str]] = mapped_column(String(128))
    country: Mapped[Optional[str]] = mapped_column(String(2))
    registered_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(_enum(RegistrationStatus, "ck_aff_reg_status"), nullable=False, default=RegistrationStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()


class AffDeposit(Base):
    __tablename__ = "aff_deposits"
    __table_args__ = (
        Index("ix_aff_dep_partner_time", "partner_id", "completed_at"),
        Index("ix_aff_dep_customer_time", "customer_id", "completed_at"),
        CheckConstraint("amount >= 0", name="ck_aff_dep_amount"),
    )

    id: Mapped[int] = _pk()
    customer_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_customers.id", ondelete="RESTRICT"), nullable=False)
    partner_id: Mapped[Optional[int]] = _partner_fk(nullable=True, index=False)
    external_transaction_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Money, nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(19, 8), nullable=False)
    status: Mapped[DepositStatus] = mapped_column(_enum(DepositStatus, "ck_aff_dep_status"), nullable=False)
    is_first_deposit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    qualified_for_cpa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffPlayerRevenueDaily(Base):
    """Operator-reported revenue per player per day (USD). Upserted until the period closes."""

    __tablename__ = "aff_player_revenue_daily"
    __table_args__ = (
        UniqueConstraint("customer_id", "revenue_date", name="uq_aff_rev_customer_date"),
        Index("ix_aff_rev_partner_date", "partner_id", "revenue_date"),
        Index("ix_aff_rev_dirty", "needs_commission"),
    )

    id: Mapped[int] = _pk()
    customer_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_customers.id", ondelete="RESTRICT"), nullable=False)
    partner_id: Mapped[Optional[int]] = _partner_fk(nullable=True, index=False)
    revenue_date: Mapped[date] = mapped_column(Date, nullable=False)
    bets: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    wins: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    bonuses: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    fees: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    chargebacks: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    ngr: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    period_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_settlement_periods.id", ondelete="RESTRICT"), nullable=True)
    needs_commission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffReversal(Base):
    __tablename__ = "aff_reversals"

    id: Mapped[int] = _pk()
    external_reversal_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    deposit_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_deposits.id", ondelete="RESTRICT"))
    customer_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_customers.id", ondelete="RESTRICT"), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    received_at: Mapped[datetime] = mapped_column(TS, nullable=False)


class AffIngestEvent(Base):
    """Raw S2S payloads, stored before processing (RECEIVED -> PROCESSED / FAILED)."""

    __tablename__ = "aff_ingest_events"
    __table_args__ = (
        UniqueConstraint("event_type", "idempotency_key", name="uq_aff_ingest_key"),
        Index("ix_aff_ingest_status_time", "status", "received_at"),
    )

    id: Mapped[int] = _pk()
    event_type: Mapped[IngestEventType] = mapped_column(_enum(IngestEventType, "ck_aff_ingest_type"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="S2S")  # S2S | INTERNAL | CSV | PULL
    signature_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[IngestStatus] = mapped_column(_enum(IngestStatus, "ck_aff_ingest_status"), nullable=False, default=IngestStatus.RECEIVED)
    error: Mapped[Optional[str]] = mapped_column(Text)
    result_ref: Mapped[Optional[str]] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(TS)


class AffFxRate(Base):
    __tablename__ = "aff_fx_rates"

    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate_to_usd: Mapped[Decimal] = mapped_column(Numeric(19, 8), nullable=False)
    created_at: Mapped[datetime] = _created()


# ===========================================================================
# 12.5 Commission and settlement
# ===========================================================================


class AffSettlementPeriod(Base):
    __tablename__ = "aff_settlement_periods"
    __table_args__ = (UniqueConstraint("period_type", "start_date", name="uq_aff_period_start"),)

    id: Mapped[int] = _pk()
    period_type: Mapped[PeriodType] = mapped_column(_enum(PeriodType, "ck_aff_period_type"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)  # inclusive
    status: Mapped[PeriodStatus] = mapped_column(_enum(PeriodStatus, "ck_aff_period_status"), nullable=False, default=PeriodStatus.OPEN)
    closed_at: Mapped[Optional[datetime]] = mapped_column(TS)
    closed_by: Mapped[Optional[str]] = _user_fk()
    reopened_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()


class AffCommission(Base):
    __tablename__ = "aff_commissions"
    __table_args__ = (
        # customer_id / deposit_id / source_partner_id use 0 instead of NULL so the key really is unique
        UniqueConstraint(
            "partner_id", "customer_id", "revenue_date", "commission_type", "deposit_id", "source_partner_id",
            name="uq_aff_commission",
        ),
        Index("ix_aff_commission_period_partner", "period_id", "partner_id"),
        Index("ix_aff_commission_status", "status"),
    )

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    customer_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)  # 0 = none (SUBPARTNER)
    deposit_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)  # 0 = none (REVSHARE)
    deal_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_partner_deals.id", ondelete="RESTRICT"))
    period_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_settlement_periods.id", ondelete="RESTRICT"), nullable=False)
    commission_type: Mapped[CommissionType] = mapped_column(_enum(CommissionType, "ck_aff_commission_type"), nullable=False)
    revenue_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(Rate, nullable=False, default=Decimal("0"))
    commission_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    source_partner_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)  # subpartner (SUBPARTNER rows), else 0
    status: Mapped[CommissionStatus] = mapped_column(_enum(CommissionStatus, "ck_aff_commission_status"), nullable=False)
    hold_until: Mapped[Optional[datetime]] = mapped_column(TS)
    approved_at: Mapped[Optional[datetime]] = mapped_column(TS)
    # amount already moved pending -> available (lets a re-opened period settle only the difference)
    settled_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffPartnerPeriodBalance(Base):
    __tablename__ = "aff_partner_period_balances"
    __table_args__ = (UniqueConstraint("partner_id", "period_id", name="uq_aff_period_balance"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    period_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_settlement_periods.id", ondelete="RESTRICT"), nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    cpa_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    revshare_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    sub_commission_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    adjustments_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    withdrawals_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    carryover_in: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    writeoff: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    closing_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = _created()


# ===========================================================================
# 12.6 Wallet and withdrawals
# ===========================================================================


class AffWallet(Base):
    """Cached balances of the ledger. Lock with SELECT ... FOR UPDATE before writing."""

    __tablename__ = "aff_wallets"
    __table_args__ = (CheckConstraint("reserved_balance >= 0", name="ck_aff_wallet_reserved"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_partners.id", ondelete="RESTRICT"), nullable=False, unique=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    available_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    pending_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    reserved_balance: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    status: Mapped[WalletStatus] = mapped_column(_enum(WalletStatus, "ck_aff_wallet_status"), nullable=False, default=WalletStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffWalletTransaction(Base):
    """Append-only ledger. amount > 0; direction says which way it moved its bucket."""

    __tablename__ = "aff_wallet_transactions"
    __table_args__ = (
        Index("ix_aff_wtx_wallet_created", "wallet_id", "created_at"),
        Index("ix_aff_wtx_reference", "reference_type", "reference_id"),
        CheckConstraint("amount > 0", name="ck_aff_wtx_amount"),
    )

    id: Mapped[int] = _pk()
    wallet_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_wallets.id", ondelete="RESTRICT"), nullable=False)
    type: Mapped[LedgerType] = mapped_column(_enum(LedgerType, "ck_aff_wtx_type"), nullable=False)
    bucket: Mapped[Bucket] = mapped_column(_enum(Bucket, "ck_aff_wtx_bucket"), nullable=False)
    direction: Mapped[Direction] = mapped_column(_enum(Direction, "ck_aff_wtx_direction"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String(32))
    reference_id: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    created_by: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = _created()


class AffManualAdjustment(Base):
    """Maker-checker wallet credit/debit: approved_by must differ from requested_by."""

    __tablename__ = "aff_manual_adjustments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_aff_adj_amount"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk()
    direction: Mapped[Direction] = mapped_column(_enum(Direction, "ck_aff_adj_direction"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[Optional[str]] = _user_fk()
    status: Mapped[ApprovalStatus] = mapped_column(_enum(ApprovalStatus, "ck_aff_adj_status"), nullable=False, default=ApprovalStatus.PENDING)
    decision_note: Mapped[Optional[str]] = mapped_column(String(255))
    decided_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()


class AffWithdrawalMethod(Base):
    __tablename__ = "aff_withdrawal_methods"

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk()
    type: Mapped[MethodType] = mapped_column(_enum(MethodType, "ck_aff_method_type"), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    account_name: Mapped[Optional[str]] = mapped_column(String(120))
    account_identifier_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    account_identifier_masked: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usable_after: Mapped[datetime] = mapped_column(TS, nullable=False)
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_method_status"), nullable=False, default=RecordStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffWithdrawal(Base):
    __tablename__ = "aff_withdrawals"
    __table_args__ = (
        Index("ix_aff_wd_partner_time", "partner_id", "requested_at"),
        Index("ix_aff_wd_status", "status"),
        CheckConstraint("amount > 0", name="ck_aff_wd_amount"),
        CheckConstraint("fee >= 0", name="ck_aff_wd_fee"),
    )

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk(index=False)
    wallet_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_wallets.id", ondelete="RESTRICT"), nullable=False)
    withdrawal_method_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_withdrawal_methods.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[WithdrawalSource] = mapped_column(_enum(WithdrawalSource, "ck_aff_wd_source"), nullable=False, default=WithdrawalSource.MANUAL)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    fee: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[WithdrawalStatus] = mapped_column(_enum(WithdrawalStatus, "ck_aff_wd_status"), nullable=False, default=WithdrawalStatus.PENDING)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    destination_masked: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(TS)
    approved_by: Mapped[Optional[str]] = _user_fk()
    processed_at: Mapped[Optional[datetime]] = mapped_column(TS)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(TS)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255))
    external_payment_reference: Mapped[Optional[str]] = mapped_column(String(120))
    updated_at: Mapped[datetime] = _updated()


class AffWithdrawalStatusHistory(Base):
    __tablename__ = "aff_withdrawal_status_history"

    id: Mapped[int] = _pk()
    withdrawal_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_withdrawals.id", ondelete="RESTRICT"), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    changed_by: Mapped[Optional[str]] = _user_fk()
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created()


class AffAutoWithdrawalSetting(Base):
    __tablename__ = "aff_auto_withdrawal_settings"

    partner_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_partners.id", ondelete="RESTRICT"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    withdrawal_method_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_withdrawal_methods.id", ondelete="RESTRICT"))
    min_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("20"))
    updated_at: Mapped[datetime] = _updated()


# ===========================================================================
# 12.7 PR tools, content, support, postbacks
# ===========================================================================


class AffPrMaterial(Base):
    __tablename__ = "aff_pr_materials"
    __table_args__ = (Index("ix_aff_pr_status_type", "status", "type"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[Optional[int]] = _partner_fk(nullable=True, index=False)  # NULL = for every partner
    campaign_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_campaigns.id", ondelete="SET NULL"))
    type: Mapped[MaterialType] = mapped_column(_enum(MaterialType, "ck_aff_pr_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    file_url: Mapped[Optional[str]] = mapped_column(Text)
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    geo: Mapped[Optional[List[str]]] = mapped_column(JSON)
    status: Mapped[ContentStatus] = mapped_column(_enum(ContentStatus, "ck_aff_pr_status"), nullable=False, default=ContentStatus.DRAFT)
    reviewed_by: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffFaq(Base):
    __tablename__ = "aff_faqs"
    __table_args__ = (Index("ix_aff_faq_status_order", "status", "sort_order"),)

    id: Mapped[int] = _pk()
    question: Mapped[str] = mapped_column(String(255), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    status: Mapped[ContentStatus] = mapped_column(_enum(ContentStatus, "ck_aff_faq_status"), nullable=False, default=ContentStatus.PUBLISHED)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffBlogPost(Base):
    __tablename__ = "aff_blog_posts"

    id: Mapped[int] = _pk()
    author_id: Mapped[Optional[str]] = _user_fk()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    excerpt: Mapped[Optional[str]] = mapped_column(String(400))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image: Mapped[Optional[str]] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    status: Mapped[ContentStatus] = mapped_column(_enum(ContentStatus, "ck_aff_blog_status"), nullable=False, default=ContentStatus.DRAFT)
    published_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffContact(Base):
    __tablename__ = "aff_contacts"

    id: Mapped[int] = _pk()
    partner_id: Mapped[Optional[int]] = _partner_fk(nullable=True, index=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reply: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ContactStatus] = mapped_column(_enum(ContactStatus, "ck_aff_contact_status"), nullable=False, default=ContactStatus.NEW, index=True)
    assigned_to: Mapped[Optional[str]] = _user_fk()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffPartnerPostback(Base):
    __tablename__ = "aff_partner_postbacks"

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = _partner_fk()
    event_type: Mapped[PostbackEvent] = mapped_column(_enum(PostbackEvent, "ck_aff_postback_event"), nullable=False)
    url_template: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(_enum(RecordStatus, "ck_aff_postback_status"), nullable=False, default=RecordStatus.ACTIVE)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AffPartnerPostbackLog(Base):
    __tablename__ = "aff_partner_postback_logs"
    __table_args__ = (
        Index("ix_aff_pblog_postback_time", "partner_postback_id", "sent_at"),
        UniqueConstraint("partner_postback_id", "event_ref", name="uq_aff_pblog_event"),
    )

    id: Mapped[int] = _pk()
    partner_postback_id: Mapped[int] = mapped_column(BigId, ForeignKey("aff_partner_postbacks.id", ondelete="RESTRICT"), nullable=False)
    event_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    url_sent: Mapped[str] = mapped_column(String(2000), nullable=False)
    response_code: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDING")  # PENDING | SENT | FAILED
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(TS)
    sent_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()


# ===========================================================================
# 12.8 Analytics, risk, export
# ===========================================================================


class AffAnalyticsHourly(Base):
    """Pre-aggregated stats per (partner, source, campaign, link, hour, country). 0 = none."""

    __tablename__ = "aff_analytics_hourly"
    __table_args__ = (
        UniqueConstraint("partner_id", "source_id", "campaign_id", "tracking_link_id", "date_hour", "country", name="uq_aff_analytics_hourly"),
        Index("ix_aff_ah_partner_hour", "partner_id", "date_hour"),
    )

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = mapped_column(BigId, nullable=False)
    source_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)
    campaign_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)
    tracking_link_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)
    date_hour: Mapped[datetime] = mapped_column(TS, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    registrations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_deposits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deposit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deposit_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    ngr: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    income: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    sub_commission: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))


class AffAnalyticsDaily(Base):
    __tablename__ = "aff_analytics_daily"
    __table_args__ = (
        UniqueConstraint("partner_id", "source_id", "campaign_id", "tracking_link_id", "stat_date", "country", name="uq_aff_analytics_daily"),
        Index("ix_aff_ad_partner_date", "partner_id", "stat_date"),
    )

    id: Mapped[int] = _pk()
    partner_id: Mapped[int] = mapped_column(BigId, nullable=False)
    source_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)
    campaign_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)
    tracking_link_id: Mapped[int] = mapped_column(BigId, nullable=False, default=0)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="")
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    registrations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_deposits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deposit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deposit_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    ngr: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    income: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    sub_commission: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))


class AffRiskEvent(Base):
    __tablename__ = "aff_risk_events"
    __table_args__ = (Index("ix_aff_risk_status_severity", "status", "severity"),)

    id: Mapped[int] = _pk()
    partner_id: Mapped[Optional[int]] = _partner_fk(nullable=True)
    customer_id: Mapped[Optional[int]] = mapped_column(BigId, ForeignKey("aff_customers.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    severity: Mapped[RiskSeverity] = mapped_column(_enum(RiskSeverity, "ck_aff_risk_severity"), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(160), unique=True)
    status: Mapped[RiskStatus] = mapped_column(_enum(RiskStatus, "ck_aff_risk_status"), nullable=False, default=RiskStatus.OPEN)
    reviewed_by: Mapped[Optional[str]] = _user_fk()
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()


class AffExportJob(Base):
    __tablename__ = "aff_export_jobs"

    id: Mapped[int] = _pk()
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    params: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[ExportStatus] = mapped_column(_enum(ExportStatus, "ck_aff_export_status"), nullable=False, default=ExportStatus.PENDING)
    file_content: Mapped[Optional[str]] = mapped_column(Text)  # CSV body (small exports; S3 later)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(String(255))
    expires_at: Mapped[Optional[datetime]] = mapped_column(TS)
    created_at: Mapped[datetime] = _created()


# ---------------------------------------------------------------------------
# Append-only guards for money history
# ---------------------------------------------------------------------------


@event.listens_for(AffWalletTransaction, "before_update")
@event.listens_for(AffWithdrawalStatusHistory, "before_update")
def _ledger_no_update(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise PermissionError("Affiliate ledger rows are append-only")


@event.listens_for(AffWalletTransaction, "before_delete")
@event.listens_for(AffWithdrawalStatusHistory, "before_delete")
@event.listens_for(AffCommission, "before_delete")
@event.listens_for(AffDeposit, "before_delete")
@event.listens_for(AffWithdrawal, "before_delete")
@event.listens_for(AffPartner, "before_delete")
@event.listens_for(AffTrackingLink, "before_delete")
def _financial_no_delete(_mapper: Any, _connection: Any, _target: Any) -> None:
    raise PermissionError("Financial and partner rows are never hard-deleted; change their status instead")
