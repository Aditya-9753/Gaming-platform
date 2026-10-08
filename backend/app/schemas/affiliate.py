"""Request bodies for the affiliate / partner API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

_CODE = r"^[0-9A-Za-z]+$"


class ProfileIn(BaseModel):
    first_name: Optional[str] = Field(None, max_length=80)
    last_name: Optional[str] = Field(None, max_length=80)
    phone: Optional[str] = Field(None, max_length=32)
    company_name: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, min_length=2, max_length=2)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=80)
    state: Optional[str] = Field(None, max_length=80)
    postal_code: Optional[str] = Field(None, max_length=20)
    telegram: Optional[str] = Field(None, max_length=64)
    website: Optional[str] = Field(None, max_length=255)
    traffic_description: Optional[str] = Field(None, max_length=2000)

    @field_validator("country")
    @classmethod
    def upper_country(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    accept_terms: bool = False
    confirm_adult: bool = False
    inviter: Optional[str] = Field(None, max_length=16, pattern=_CODE)
    timezone: Optional[str] = Field(None, max_length=64)
    locale: Optional[str] = Field(None, max_length=8)
    profile: ProfileIn = ProfileIn()


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class MeUpdateIn(BaseModel):
    timezone: Optional[str] = Field(None, max_length=64)
    locale: Optional[str] = Field(None, max_length=8)
    profile: Optional[ProfileIn] = None


class TermsAcceptIn(BaseModel):
    version_id: int


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class EmailChangeIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    new_email: EmailStr


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = "OTHER"
    url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)


class SourceUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    type: Optional[str] = None
    url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = None


class CampaignIn(BaseModel):
    source_id: int
    name: str = Field(min_length=1, max_length=80)
    destination_url: Optional[str] = Field(None, max_length=500)
    blocked_countries: Optional[List[str]] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None


class CampaignUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    destination_url: Optional[str] = Field(None, max_length=500)
    blocked_countries: Optional[List[str]] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    status: Optional[str] = None


class LinkIn(BaseModel):
    source_id: int
    campaign_id: Optional[int] = None
    name: str = Field("Link", min_length=1, max_length=80)
    destination_url: Optional[str] = Field(None, max_length=500)


class LinkUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    destination_url: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None


class PromoIn(BaseModel):
    tracking_link_id: int
    code: Optional[str] = Field(None, max_length=32)


class QrIn(BaseModel):
    tracking_link_id: int
    name: Optional[str] = Field(None, max_length=80)


class ClickIn(BaseModel):
    ref: str = Field(min_length=1, max_length=24, pattern=_CODE)
    sub1: Optional[str] = Field(None, max_length=128)
    sub2: Optional[str] = Field(None, max_length=128)
    sub3: Optional[str] = Field(None, max_length=128)
    sub4: Optional[str] = Field(None, max_length=128)
    sub5: Optional[str] = Field(None, max_length=128)
    referrer: Optional[str] = Field(None, max_length=500)


class MethodIn(BaseModel):
    type: str
    label: Optional[str] = Field(None, max_length=60)
    account_name: Optional[str] = Field(None, max_length=120)
    account_identifier: str = Field(min_length=3, max_length=254)
    is_default: bool = False


class MethodUpdateIn(BaseModel):
    label: Optional[str] = Field(None, max_length=60)
    account_identifier: Optional[str] = Field(None, min_length=3, max_length=254)
    is_default: Optional[bool] = None
    status: Optional[str] = None


class WithdrawalIn(BaseModel):
    amount: str = Field(min_length=1, max_length=20)
    method_id: Optional[int] = None


class AutoWithdrawalIn(BaseModel):
    enabled: bool
    method_id: Optional[int] = None
    min_amount: Optional[str] = Field(None, max_length=20)


class PostbackIn(BaseModel):
    event_type: str
    url_template: str = Field(min_length=10, max_length=1000)


class PostbackUpdateIn(BaseModel):
    url_template: Optional[str] = Field(None, min_length=10, max_length=1000)
    status: Optional[str] = None


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)


class ExportIn(BaseModel):
    kind: str = Field("common", pattern=r"^(common|subpartners)$")
    group_by: str = "day"
    period: str = "30d"
    date_from: Optional[date] = None
    date_to: Optional[date] = None


# ------------------------------------------------------------------ admin


class DealIn(BaseModel):
    plan_id: Optional[int] = None
    deal_type: Optional[str] = None
    revshare_rate: Optional[str] = None
    cpa_amount: Optional[str] = None
    min_ftd_amount: Optional[str] = None
    cpa_geo_list: Optional[List[str]] = None
    carryover: Optional[bool] = None
    carryover_cap: Optional[str] = None
    hold_days: Optional[int] = Field(None, ge=0, le=180)
    tier_table: Optional[List[Dict[str, Any]]] = None


class DealChangeIn(DealIn):
    effective_from: Optional[date] = None


class PartnerCreateIn(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(None, min_length=10, max_length=128)
    send_set_password_email: bool = True
    parent_partner_id: Optional[int] = None
    manager_id: Optional[str] = None
    timezone: Optional[str] = Field(None, max_length=64)
    profile: ProfileIn = ProfileIn()
    deal: DealIn = DealIn()


class PartnerUpdateIn(BaseModel):
    manager_id: Optional[str] = None
    subpartner_rate: Optional[str] = None
    timezone: Optional[str] = Field(None, max_length=64)
    parent_partner_id: Optional[int] = None
    profile: Optional[ProfileIn] = None


class StatusIn(BaseModel):
    status: str
    reason: Optional[str] = Field(None, max_length=255)


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    deal_type: str
    default_revshare_rate: str = "0"
    default_cpa_amount: str = "0"
    min_ftd_amount: str = "0"
    hold_days: int = Field(14, ge=0, le=180)
    carryover: bool = True
    tier_table: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = Field(None, max_length=255)
    status: str = "ACTIVE"


class DomainIn(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    is_primary: bool = False
    status: str = "ACTIVE"


class PeriodReopenIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class WithdrawalActionIn(BaseModel):
    note: Optional[str] = Field(None, max_length=255)
    external_payment_reference: Optional[str] = Field(None, max_length=120)


class AdjustmentIn(BaseModel):
    partner_id: int
    direction: str = Field(pattern=r"^(CREDIT|DEBIT)$")
    amount: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=3, max_length=255)


class DecisionIn(BaseModel):
    approve: bool
    note: Optional[str] = Field(None, max_length=255)


class FreezeIn(BaseModel):
    frozen: bool
    reason: str = Field(min_length=3, max_length=255)


class FraudIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class IpFraudIn(BaseModel):
    partner_id: int
    ip_hash: str = Field(min_length=64, max_length=64)
    hours: int = Field(24, ge=1, le=744)
    reason: str = Field(min_length=3, max_length=255)


class RiskReviewIn(BaseModel):
    status: str
    note: Optional[str] = Field(None, max_length=255)


class FxRateIn(BaseModel):
    rate_date: date
    currency: str = Field(min_length=3, max_length=3)
    rate_to_usd: str = Field(min_length=1, max_length=24)


class CsvImportIn(BaseModel):
    event_type: str
    csv: str = Field(min_length=10, max_length=5_000_000)


class ManualAttributionIn(BaseModel):
    external_customer_id: str = Field(min_length=1, max_length=64)
    partner_id: int
    tracking_link_id: Optional[int] = None
    country: Optional[str] = Field(None, max_length=2)
    reason: str = Field(min_length=3, max_length=255)


class MaterialIn(BaseModel):
    type: str
    title: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    file_url: Optional[str] = None
    body_text: Optional[str] = Field(None, max_length=10000)
    width: Optional[int] = Field(None, ge=1, le=10000)
    height: Optional[int] = Field(None, ge=1, le=10000)
    language: str = Field("en", max_length=8)
    geo: Optional[List[str]] = None
    partner_id: Optional[int] = None
    campaign_id: Optional[int] = None
    status: str = "DRAFT"


class FaqIn(BaseModel):
    question: str = Field(min_length=3, max_length=255)
    answer: str = Field(min_length=1, max_length=10000)
    category: Optional[str] = Field(None, max_length=60)
    language: str = Field("en", max_length=8)
    status: str = "PUBLISHED"
    sort_order: int = 0


class BlogIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    excerpt: Optional[str] = Field(None, max_length=400)
    content: str = Field(min_length=1, max_length=100000)
    cover_image: Optional[str] = None
    language: str = Field("en", max_length=8)
    status: str = "DRAFT"


class ContactReplyIn(BaseModel):
    reply: Optional[str] = Field(None, max_length=5000)
    status: Optional[str] = None
    assigned_to: Optional[str] = None


class TermsIn(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=10, max_length=200000)
    content_url: Optional[str] = Field(None, max_length=500)


class SettingsIn(BaseModel):
    changes: Dict[str, Any]
