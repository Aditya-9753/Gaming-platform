"""Enumerations shared by the affiliate models, services and API."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum


class PartnerStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BLOCKED = "BLOCKED"


class SignupSource(str, Enum):
    SELF = "SELF"
    ADMIN = "ADMIN"


class DealType(str, Enum):
    REVSHARE = "REVSHARE"
    CPA = "CPA"
    HYBRID = "HYBRID"
    TIERED = "TIERED"


class RecordStatus(str, Enum):
    """Generic ACTIVE / ARCHIVED style status for configuration rows."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class DomainStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"


class SourceType(str, Enum):
    WEBSITE = "WEBSITE"
    SOCIAL = "SOCIAL"
    TELEGRAM = "TELEGRAM"
    YOUTUBE = "YOUTUBE"
    PAID_ADS = "PAID_ADS"
    OTHER = "OTHER"


class CustomerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    SELF_EXCLUDED = "SELF_EXCLUDED"


class AttributionType(str, Enum):
    CLICK = "CLICK"
    PROMO = "PROMO"
    MANUAL = "MANUAL"


class RegistrationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FRAUD = "FRAUD"


class DepositStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class IngestEventType(str, Enum):
    REGISTRATION = "REGISTRATION"
    DEPOSIT = "DEPOSIT"
    REVENUE = "REVENUE"
    REVERSAL = "REVERSAL"


class IngestStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class PeriodType(str, Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class PeriodStatus(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class CommissionType(str, Enum):
    CPA = "CPA"
    REVSHARE = "REVSHARE"
    SUBPARTNER = "SUBPARTNER"
    REVERSAL = "REVERSAL"


class CommissionStatus(str, Enum):
    PENDING = "PENDING"    # in the open period
    HELD = "HELD"          # CPA under fraud hold
    APPROVED = "APPROVED"  # settled into the available balance
    REVERSED = "REVERSED"


class WalletStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"


class Bucket(str, Enum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"


class Direction(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class LedgerType(str, Enum):
    COMMISSION_CPA = "COMMISSION_CPA"
    COMMISSION_REVSHARE = "COMMISSION_REVSHARE"
    SUBPARTNER_COMMISSION = "SUBPARTNER_COMMISSION"
    COMMISSION_ADJUSTMENT = "COMMISSION_ADJUSTMENT"
    PERIOD_SETTLE = "PERIOD_SETTLE"
    CARRYOVER_WRITEOFF = "CARRYOVER_WRITEOFF"
    WITHDRAWAL_RESERVE = "WITHDRAWAL_RESERVE"
    WITHDRAWAL_RELEASE = "WITHDRAWAL_RELEASE"
    WITHDRAWAL_PAID = "WITHDRAWAL_PAID"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MethodType(str, Enum):
    EWALLET_EMAIL = "EWALLET_EMAIL"
    USDT_TRC20 = "USDT_TRC20"
    BANK = "BANK"
    UPI = "UPI"
    OTHER = "OTHER"


class WithdrawalSource(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"


class WithdrawalStatus(str, Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


OPEN_WITHDRAWAL_STATUSES = (
    WithdrawalStatus.PENDING,
    WithdrawalStatus.UNDER_REVIEW,
    WithdrawalStatus.APPROVED,
    WithdrawalStatus.PROCESSING,
)

# from -> allowed next states
WITHDRAWAL_TRANSITIONS = {
    WithdrawalStatus.PENDING: {WithdrawalStatus.UNDER_REVIEW, WithdrawalStatus.APPROVED, WithdrawalStatus.REJECTED, WithdrawalStatus.CANCELLED},
    WithdrawalStatus.UNDER_REVIEW: {WithdrawalStatus.APPROVED, WithdrawalStatus.REJECTED},
    WithdrawalStatus.APPROVED: {WithdrawalStatus.PROCESSING, WithdrawalStatus.COMPLETED, WithdrawalStatus.REJECTED},
    WithdrawalStatus.PROCESSING: {WithdrawalStatus.COMPLETED, WithdrawalStatus.FAILED},
}


class MaterialType(str, Enum):
    BANNER = "BANNER"
    LANDING = "LANDING"
    VIDEO = "VIDEO"
    TEXT = "TEXT"


class ContentStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ContactStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class PostbackEvent(str, Enum):
    REGISTRATION = "REGISTRATION"
    FTD = "FTD"
    DEPOSIT = "DEPOSIT"


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskStatus(str, Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class EmailTokenPurpose(str, Enum):
    VERIFY = "VERIFY"
    RESET = "RESET"


class ExportStatus(str, Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    FAILED = "FAILED"


ZERO = Decimal("0")
CENT = Decimal("0.01")
MONEY_Q = Decimal("0.0001")


def enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]
