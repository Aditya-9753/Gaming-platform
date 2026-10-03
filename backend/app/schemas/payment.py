"""Payment request schemas (strict: unknown fields rejected) and response serializers.

There is deliberately no request field for a status anywhere: status is
computed by app.services.payment_service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment import BankCredit, Beneficiary, Deposit, PaymentAccount, PaymentStatusHistory, Withdrawal
from app.services.payment_service import MATCHABLE_DEPOSIT_STATES, qr_data_url, upi_link

_MAX_PAISE = 100_000_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------------ player requests


class DepositCreate(_Strict):
    amount_paise: int = Field(..., gt=0, le=_MAX_PAISE)


class UtrSubmit(_Strict):
    utr: str = Field(..., min_length=6, max_length=60)


class PinSet(_Strict):
    pin: str = Field(..., min_length=4, max_length=6)
    password: str = Field(..., min_length=1, max_length=128)


class BeneficiaryCreate(_Strict):
    method: str = Field(..., pattern=r"^(BANK|UPI|bank|upi)$")
    holder_name: str = Field(..., min_length=2, max_length=100)
    account_number: Optional[str] = Field(None, max_length=30)
    ifsc: Optional[str] = Field(None, max_length=11)
    bank_name: Optional[str] = Field(None, max_length=100)
    vpa: Optional[str] = Field(None, max_length=256)
    pin: str = Field(..., min_length=4, max_length=6)


class WithdrawalCreate(_Strict):
    amount_paise: int = Field(..., gt=0, le=_MAX_PAISE)
    beneficiary_id: str = Field(..., min_length=1, max_length=36)
    pin: str = Field(..., min_length=4, max_length=6)


# ------------------------------------------------------------------ staff requests


class StepUpVerify(_Strict):
    code: str = Field(..., pattern=r"^\d{6}$")


class AccountCreate(_Strict):
    label: str = Field(..., min_length=2, max_length=80)
    upi_id: str = Field(..., min_length=3, max_length=100)
    payee_name: str = Field(..., min_length=2, max_length=100)
    bank_name: Optional[str] = Field(None, max_length=100)
    qr_image: Optional[str] = None
    min_amount_paise: int = Field(0, ge=0, le=_MAX_PAISE)
    max_amount_paise: int = Field(0, ge=0, le=_MAX_PAISE)
    daily_limit_paise: int = Field(0, ge=0, le=10 * _MAX_PAISE)


class AccountUpdate(_Strict):
    label: Optional[str] = Field(None, max_length=80)
    upi_id: Optional[str] = Field(None, max_length=100)
    payee_name: Optional[str] = Field(None, max_length=100)
    bank_name: Optional[str] = Field(None, max_length=100)
    qr_image: Optional[str] = None
    min_amount_paise: Optional[int] = Field(None, ge=0, le=_MAX_PAISE)
    max_amount_paise: Optional[int] = Field(None, ge=0, le=_MAX_PAISE)
    daily_limit_paise: Optional[int] = Field(None, ge=0, le=10 * _MAX_PAISE)
    active: Optional[bool] = None


class AccountReview(_Strict):
    approve: bool
    note: Optional[str] = Field(None, max_length=255)


class DepositConfirm(_Strict):
    utr: str = Field(..., min_length=6, max_length=60)
    amount_paise: Optional[int] = Field(None, gt=0, le=_MAX_PAISE)
    note: Optional[str] = Field(None, max_length=255)


class ReasonBody(_Strict):
    reason: str = Field(..., min_length=3, max_length=500)


class StatementLine(_Strict):
    utr: str = Field(..., min_length=1, max_length=60)
    amount_paise: int = Field(..., gt=0, le=10 * _MAX_PAISE)
    remark: Optional[str] = Field(None, max_length=255)
    payer_name: Optional[str] = Field(None, max_length=100)
    received_at: Optional[datetime] = None


class StatementImport(_Strict):
    account_id: str = Field(..., min_length=1, max_length=36)
    lines: List[StatementLine] = Field(..., min_length=1, max_length=500)


class CreditAssign(_Strict):
    deposit_id: str = Field(..., min_length=1, max_length=36)


class WithdrawalInitiate(_Strict):
    note: Optional[str] = Field(None, max_length=500)
    expected_version: Optional[int] = None


class WithdrawalComplete(_Strict):
    payout_reference: str = Field(..., min_length=6, max_length=60)
    expected_version: Optional[int] = None
    note: Optional[str] = Field(None, max_length=500)


class WithdrawalReject(_Strict):
    reason: str = Field(..., min_length=3, max_length=500)
    expected_version: Optional[int] = None


# ------------------------------------------------------------------ serializers

_DEPOSIT_STAGE = {
    "PENDING": "Waiting for your payment",
    "UTR_SUBMITTED": "Verifying your payment",
    "MANUAL_REVIEW": "Under review by our team",
    "CREDITED": "Added to wallet",
    "FAILED": "Rejected",
    "EXPIRED": "Payment window expired",
    "CANCELLED": "Cancelled",
    "REVERSED": "Reversed by bank",
}
_WITHDRAWAL_STAGE = {
    "AWAITING_APPROVAL": "Awaiting approval",
    "PAYOUT_INITIATED": "Payout in progress",
    "COMPLETED": "Paid",
    "REJECTED": "Rejected — amount returned to wallet",
    "CANCELLED": "Cancelled — amount returned to wallet",
}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def deposit_out(
    dep: Deposit, account: Optional[PaymentAccount] = None, *, admin: bool = False,
    names: Optional[Dict[str, str]] = None, with_qr: bool = False, brand: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": dep.id,
        "reference": dep.reference,
        "amount_paise": dep.amount_paise,
        "credited_amount_paise": dep.credited_amount_paise,
        "status": dep.status,
        "stage": _DEPOSIT_STAGE.get(dep.state, dep.state),
        "utr": dep.user_utr,
        "note": dep.review_note if dep.state in ("FAILED", "MANUAL_REVIEW") or admin else None,
        "created_at": _iso(dep.created_at),
        "expires_at": _iso(dep.expires_at),
        "credited_at": _iso(dep.credited_at),
        "can_submit_utr": dep.state in MATCHABLE_DEPOSIT_STATES,
        "can_cancel": dep.state == "PENDING",
    }
    if account is not None and admin:
        link = upi_link(account, dep.amount_paise, dep.reference)
        out["payment"] = {
            "payee_name": account.payee_name,
            "upi_id": account.upi_id,
            "bank_name": account.bank_name,
            "upi_link": link,
            "qr": None,
            "qr_image": None,
        }
    elif account is not None and dep.state in MATCHABLE_DEPOSIT_STATES:
        # Players get only a generated QR for this exact amount, labelled with the platform
        # brand: no UPI id, payee name, bank or uploaded QR image in the response.
        link = upi_link(account, dep.amount_paise, dep.reference, display_name=brand or "Payment")
        out["payment"] = {
            "upi_link": link,
            "qr": qr_data_url(link, label=brand or None) if with_qr else None,
        }
    if admin:
        names = names or {}
        out.update({
            "state": dep.state,
            "user_id": dep.user_id,
            "username": names.get(dep.user_id),
            "payment_account_id": dep.payment_account_id,
            "account_label": account.label if account else None,
            "account_owner": names.get(account.owner_id) if account else None,
            "verification_method": dep.verification_method,
            "verified_by": names.get(dep.verified_by or "", dep.verified_by),
            "bank_credit_id": dep.bank_credit_id,
            "request_ip": dep.request_ip,
            "version": dep.version,
        })
    return out


def withdrawal_out(wd: Withdrawal, *, admin: bool = False, names: Optional[Dict[str, str]] = None,
                   high_value_paise: Optional[int] = None) -> Dict[str, Any]:
    ref = wd.payout_reference
    out: Dict[str, Any] = {
        "id": wd.id,
        "amount_paise": wd.amount_paise,
        "status": wd.status,
        "stage": _WITHDRAWAL_STAGE.get(wd.state, wd.state),
        "payout_to": wd.payout_masked,
        "payout_reference": ref if admin else (f"…{ref[-4:]}" if ref else None),
        "reject_reason": wd.reject_reason,
        "created_at": _iso(wd.created_at),
        "completed_at": _iso(wd.completed_at or wd.rejected_at),
        "can_cancel": wd.state == "AWAITING_APPROVAL",
    }
    if admin:
        names = names or {}
        out.update({
            "state": wd.state,
            "user_id": wd.user_id,
            "username": names.get(wd.user_id),
            "risk_score": wd.risk_score,
            "risk_flags": wd.risk_flags or {},
            "initiated_by": names.get(wd.initiated_by or "", wd.initiated_by),
            "initiated_by_id": wd.initiated_by,
            "initiated_at": _iso(wd.initiated_at),
            "completed_by": names.get(wd.completed_by or "", wd.completed_by),
            "rejected_by": names.get(wd.rejected_by or "", wd.rejected_by),
            "admin_note": wd.admin_note,
            "request_ip": wd.request_ip,
            "version": wd.version,
            "high_value": high_value_paise is not None and wd.amount_paise >= high_value_paise,
        })
    return out


def beneficiary_out(ben: Beneficiary) -> Dict[str, Any]:
    return {
        "id": ben.id,
        "method": ben.method,
        "holder_name": ben.holder_name,
        "bank_name": ben.bank_name,
        "masked": ben.masked,
        "cooling_until": _iso(ben.cooling_until),
        "created_at": _iso(ben.created_at),
    }


def account_out(acc: PaymentAccount, *, names: Optional[Dict[str, str]] = None,
                load: Optional[Dict[str, int]] = None, include_image: bool = False) -> Dict[str, Any]:
    names = names or {}
    return {
        "id": acc.id,
        "label": acc.label,
        "upi_id": acc.upi_id,
        "payee_name": acc.payee_name,
        "bank_name": acc.bank_name,
        "has_qr_image": bool(acc.qr_image),
        "qr_image": acc.qr_image if include_image else None,
        "status": acc.status,
        "owner_id": acc.owner_id,
        "owner": names.get(acc.owner_id),
        "approved_by": names.get(acc.approved_by or "", acc.approved_by),
        "review_note": acc.review_note,
        "min_amount_paise": acc.min_amount_paise,
        "max_amount_paise": acc.max_amount_paise,
        "daily_limit_paise": acc.daily_limit_paise,
        "received_today_paise": (load or {}).get("received_today", 0),
        "open_paise": (load or {}).get("open", 0),
        "created_at": _iso(acc.created_at),
    }


def credit_out(credit: BankCredit, *, names: Optional[Dict[str, str]] = None,
               labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    names, labels = names or {}, labels or {}
    return {
        "id": credit.id,
        "source": credit.source,
        "provider": credit.provider,
        "utr": credit.utr,
        "amount_paise": credit.amount_paise,
        "payment_account_id": credit.payment_account_id,
        "account_label": labels.get(credit.payment_account_id or ""),
        "remark": credit.remark,
        "payer_name": credit.payer_name,
        "payer_vpa": credit.payer_vpa,
        "status": credit.status,
        "deposit_id": credit.deposit_id,
        "created_by": names.get(credit.created_by or "", credit.created_by),
        "received_at": _iso(credit.received_at),
        "created_at": _iso(credit.created_at),
    }


def history_out(rows: List[PaymentStatusHistory], names: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    names = names or {}
    return [
        {
            "from": h.from_state,
            "to": h.to_state,
            "actor": names.get(h.actor_id or "", h.actor_type),
            "actor_type": h.actor_type,
            "reason": h.reason,
            "ip": h.ip_address,
            "at": _iso(h.created_at),
        }
        for h in rows
    ]
