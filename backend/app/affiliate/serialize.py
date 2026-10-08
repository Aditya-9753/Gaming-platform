"""JSON shapes returned by the affiliate API (money as 2-dp strings, enums as values)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional

from app.affiliate.util import aware, money_out
from app.models import affiliate as m


def _v(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return aware(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def partner(p: m.AffPartner, email: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": p.id, "partner_code": p.partner_code, "email": email, "status": _v(p.status), "signup_source": _v(p.signup_source),
        "parent_partner_id": p.parent_partner_id, "manager_id": p.manager_id, "subpartner_rate": str(p.subpartner_rate),
        "payout_frozen": p.payout_frozen, "timezone": p.timezone, "locale": p.locale,
        "approved_at": _v(p.approved_at), "created_at": _v(p.created_at),
    }


def profile(pr: Optional[m.AffPartnerProfile]) -> Dict[str, Any]:
    if pr is None:
        return {}
    from app.affiliate.partners import PROFILE_FIELDS

    return {k: getattr(pr, k) for k in PROFILE_FIELDS}


def deal(d: Optional[m.AffPartnerDeal]) -> Optional[Dict[str, Any]]:
    if d is None:
        return None
    return {
        "id": d.id, "plan_id": d.plan_id, "deal_type": _v(d.deal_type), "revshare_rate": str(d.revshare_rate),
        "cpa_amount": money_out(d.cpa_amount), "min_ftd_amount": money_out(d.min_ftd_amount), "cpa_geo_list": d.cpa_geo_list,
        "carryover": d.carryover, "carryover_cap": None if d.carryover_cap is None else money_out(d.carryover_cap),
        "hold_days": d.hold_days, "tier_table": d.tier_table, "effective_from": _v(d.effective_from),
        "effective_to": _v(d.effective_to), "created_at": _v(d.created_at),
    }


def plan(p: m.AffCommissionPlan) -> Dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "deal_type": _v(p.deal_type), "default_revshare_rate": str(p.default_revshare_rate),
        "default_cpa_amount": money_out(p.default_cpa_amount), "min_ftd_amount": money_out(p.min_ftd_amount),
        "hold_days": p.hold_days, "carryover": p.carryover, "tier_table": p.tier_table, "description": p.description,
        "status": _v(p.status),
    }


def source(s: m.AffSource) -> Dict[str, Any]:
    return {"id": s.id, "partner_id": s.partner_id, "name": s.name, "type": _v(s.type), "url": s.url,
            "description": s.description, "is_default": s.is_default, "status": _v(s.status), "created_at": _v(s.created_at)}


def campaign(c: m.AffCampaign) -> Dict[str, Any]:
    return {"id": c.id, "partner_id": c.partner_id, "source_id": c.source_id, "name": c.name, "code": c.code,
            "destination_url": c.destination_url, "blocked_countries": c.blocked_countries or [], "status": _v(c.status),
            "start_at": _v(c.start_at), "end_at": _v(c.end_at), "created_at": _v(c.created_at)}


def link(l: m.AffTrackingLink, urls: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    return {"id": l.id, "partner_id": l.partner_id, "source_id": l.source_id, "campaign_id": l.campaign_id,
            "link_code": l.link_code, "name": l.name, "destination_url": l.destination_url, "is_default": l.is_default,
            "status": _v(l.status), "urls": urls or {}, "created_at": _v(l.created_at)}


def promo(p: m.AffPromoCode) -> Dict[str, Any]:
    return {"id": p.id, "tracking_link_id": p.tracking_link_id, "code": p.code, "status": _v(p.status), "created_at": _v(p.created_at)}


def qr(q: m.AffQrCode) -> Dict[str, Any]:
    return {"id": q.id, "tracking_link_id": q.tracking_link_id, "name": q.name, "image_url": q.image_url, "created_at": _v(q.created_at)}


def domain(d: m.AffTrackingDomain) -> Dict[str, Any]:
    return {"id": d.id, "domain": d.domain, "is_primary": d.is_primary, "status": _v(d.status), "ssl_ok": d.ssl_ok,
            "last_checked_at": _v(d.last_checked_at), "last_check_error": d.last_check_error}


def wallet(w: m.AffWallet) -> Dict[str, Any]:
    return {"currency": w.currency, "available": money_out(w.available_balance), "pending": money_out(w.pending_balance),
            "reserved": money_out(w.reserved_balance), "status": _v(w.status)}


def ledger_entry(t: m.AffWalletTransaction) -> Dict[str, Any]:
    signed = t.amount if _v(t.direction) == "CREDIT" else -t.amount
    return {"id": t.id, "type": _v(t.type), "bucket": _v(t.bucket), "direction": _v(t.direction), "amount": money_out(signed),
            "balance_after": money_out(t.balance_after), "reference_type": t.reference_type, "reference_id": t.reference_id,
            "description": t.description, "created_at": _v(t.created_at)}


def method(x: m.AffWithdrawalMethod) -> Dict[str, Any]:
    return {"id": x.id, "type": _v(x.type), "label": x.label, "account_name": x.account_name,
            "destination": x.account_identifier_masked, "is_default": x.is_default, "verified": x.verified,
            "usable_after": _v(x.usable_after), "status": _v(x.status), "created_at": _v(x.created_at)}


def withdrawal(w: m.AffWithdrawal) -> Dict[str, Any]:
    return {"id": w.id, "partner_id": w.partner_id, "method_id": w.withdrawal_method_id, "source": _v(w.source),
            "amount": money_out(w.amount), "fee": money_out(w.fee), "net_amount": money_out(w.net_amount), "currency": w.currency,
            "status": _v(w.status), "destination": w.destination_masked, "requested_at": _v(w.requested_at),
            "approved_at": _v(w.approved_at), "processed_at": _v(w.processed_at), "rejection_reason": w.rejection_reason,
            "external_payment_reference": w.external_payment_reference}


def status_history(h: m.AffWithdrawalStatusHistory) -> Dict[str, Any]:
    return {"from": h.from_status, "to": h.to_status, "changed_by": h.changed_by, "note": h.note, "at": _v(h.created_at)}


def period(p: m.AffSettlementPeriod) -> Dict[str, Any]:
    return {"id": p.id, "period_type": _v(p.period_type), "start_date": _v(p.start_date), "end_date": _v(p.end_date),
            "status": _v(p.status), "closed_at": _v(p.closed_at), "closed_by": p.closed_by, "reopened_at": _v(p.reopened_at)}


def period_balance(b: m.AffPartnerPeriodBalance) -> Dict[str, Any]:
    return {k: money_out(getattr(b, k)) for k in ("opening_balance", "cpa_total", "revshare_total", "sub_commission_total",
                                                  "adjustments_total", "withdrawals_total", "carryover_in", "writeoff",
                                                  "closing_balance")} | {"partner_id": b.partner_id, "period_id": b.period_id}


def commission(c: m.AffCommission) -> Dict[str, Any]:
    return {"id": c.id, "partner_id": c.partner_id, "customer_id": c.customer_id or None, "deposit_id": c.deposit_id or None,
            "type": _v(c.commission_type), "revenue_date": _v(c.revenue_date), "base_amount": money_out(c.base_amount),
            "rate": str(c.rate), "amount": money_out(c.commission_amount), "status": _v(c.status), "hold_until": _v(c.hold_until),
            "period_id": c.period_id, "source_partner_id": c.source_partner_id or None}


def adjustment(a: m.AffManualAdjustment) -> Dict[str, Any]:
    return {"id": a.id, "partner_id": a.partner_id, "direction": _v(a.direction), "amount": money_out(a.amount), "reason": a.reason,
            "requested_by": a.requested_by, "approved_by": a.approved_by, "status": _v(a.status), "decision_note": a.decision_note,
            "decided_at": _v(a.decided_at), "created_at": _v(a.created_at)}


def ingest_event(e: m.AffIngestEvent, with_payload: bool = False) -> Dict[str, Any]:
    out = {"id": e.id, "event_type": _v(e.event_type), "idempotency_key": e.idempotency_key, "source": e.source,
           "signature_ok": e.signature_ok, "status": _v(e.status), "error": e.error, "result_ref": e.result_ref,
           "attempts": e.attempts, "received_at": _v(e.received_at), "processed_at": _v(e.processed_at)}
    if with_payload:
        out["payload"] = e.payload
    return out


def risk(r: m.AffRiskEvent) -> Dict[str, Any]:
    return {"id": r.id, "partner_id": r.partner_id, "customer_id": r.customer_id, "event_type": r.event_type,
            "risk_score": r.risk_score, "severity": _v(r.severity), "reason": r.reason, "metadata": r.metadata_json,
            "status": _v(r.status), "reviewed_by": r.reviewed_by, "reviewed_at": _v(r.reviewed_at), "created_at": _v(r.created_at)}


def material(x: m.AffPrMaterial) -> Dict[str, Any]:
    return {"id": x.id, "partner_id": x.partner_id, "campaign_id": x.campaign_id, "type": _v(x.type), "title": x.title,
            "description": x.description, "file_url": x.file_url, "body_text": x.body_text, "width": x.width, "height": x.height,
            "language": x.language, "geo": x.geo or [], "status": _v(x.status), "created_at": _v(x.created_at)}


def faq(f: m.AffFaq) -> Dict[str, Any]:
    return {"id": f.id, "question": f.question, "answer": f.answer, "category": f.category, "language": f.language,
            "status": _v(f.status), "sort_order": f.sort_order}


def blog(b: m.AffBlogPost, full: bool = True) -> Dict[str, Any]:
    out = {"id": b.id, "title": b.title, "slug": b.slug, "excerpt": b.excerpt, "cover_image": b.cover_image,
           "language": b.language, "status": _v(b.status), "published_at": _v(b.published_at), "created_at": _v(b.created_at)}
    if full:
        out["content"] = b.content
    return out


def contact(c: m.AffContact) -> Dict[str, Any]:
    return {"id": c.id, "partner_id": c.partner_id, "name": c.name, "email": c.email, "subject": c.subject, "message": c.message,
            "reply": c.reply, "status": _v(c.status), "assigned_to": c.assigned_to, "created_at": _v(c.created_at),
            "updated_at": _v(c.updated_at)}


def postback(p: m.AffPartnerPostback) -> Dict[str, Any]:
    return {"id": p.id, "event_type": _v(p.event_type), "url_template": p.url_template, "status": _v(p.status),
            "created_at": _v(p.created_at)}


def postback_log(l: m.AffPartnerPostbackLog) -> Dict[str, Any]:
    return {"id": l.id, "postback_id": l.partner_postback_id, "event_ref": l.event_ref, "url_sent": l.url_sent,
            "response_code": l.response_code, "status": l.status, "attempts": l.attempts, "sent_at": _v(l.sent_at),
            "created_at": _v(l.created_at)}


def export_job(j: m.AffExportJob) -> Dict[str, Any]:
    return {"id": j.id, "type": j.type, "params": j.params, "status": _v(j.status), "row_count": j.row_count, "error": j.error,
            "expires_at": _v(j.expires_at), "created_at": _v(j.created_at)}


def terms(t: Optional[m.AffTermsVersion], with_content: bool = False) -> Optional[Dict[str, Any]]:
    if t is None:
        return None
    out = {"id": t.id, "version": t.version, "content_url": t.content_url, "published_at": _v(t.published_at)}
    if with_content:
        out["content"] = t.content
    return out


def click(c: m.AffTrackingClick) -> Dict[str, Any]:
    return {"click_id": c.click_id, "clicked_at": _v(c.clicked_at), "partner_id": c.partner_id, "tracking_link_id": c.tracking_link_id,
            "country": c.country, "device_type": c.device_type, "browser": c.browser, "os": c.os, "ip_hash": c.ip_hash,
            "sub1": c.sub1, "is_bot": c.is_bot, "is_unique": c.is_unique, "is_fraud": c.is_fraud}


def registration(r: m.AffRegistration, external_id: Optional[str] = None) -> Dict[str, Any]:
    return {"id": r.id, "customer_id": r.customer_id, "external_customer_id": external_id, "partner_id": r.partner_id,
            "tracking_link_id": r.tracking_link_id, "attribution_type": _v(r.attribution_type), "click_id": r.click_id,
            "country": r.country, "registered_at": _v(r.registered_at), "status": _v(r.status)}


def deposit(d: m.AffDeposit) -> Dict[str, Any]:
    return {"id": d.id, "customer_id": d.customer_id, "partner_id": d.partner_id, "external_transaction_id": d.external_transaction_id,
            "amount": money_out(d.amount), "currency": d.currency, "amount_usd": money_out(d.amount_usd), "status": _v(d.status),
            "is_first_deposit": d.is_first_deposit, "qualified_for_cpa": d.qualified_for_cpa, "is_fraud": d.is_fraud,
            "completed_at": _v(d.completed_at)}
