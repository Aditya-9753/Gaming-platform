"""Audit, risk events, notifications and the actor passed through services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.constants import RiskSeverity
from app.models.affiliate import AffRiskEvent
from app.models.audit_log import AuditLog
from app.models.notification import Notification


@dataclass
class Actor:
    """Who is acting: a staff user, a partner user, or the system (user_id None)."""

    user_id: Optional[str] = None
    role: str = "SYSTEM"
    ip: Optional[str] = None
    impersonated_by: Optional[str] = None
    permissions: frozenset = field(default_factory=frozenset)

    @property
    def is_super(self) -> bool:
        return self.role == "SUPERADMIN"

    def can(self, code: str) -> bool:
        return self.is_super or code in self.permissions


SYSTEM = Actor()


def actor_from(current_user: Any, ip: Optional[str] = None) -> Actor:
    return Actor(
        user_id=current_user.id,
        role=(current_user.role or "").upper(),
        ip=ip,
        impersonated_by=getattr(current_user, "impersonated_by", None),
        permissions=frozenset(current_user.permissions or ()),
    )


def _plain(value: Any) -> Any:
    """JSON-safe copy (Decimals / dates become strings)."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


async def audit(
    db: AsyncSession,
    actor: Actor,
    action: str,
    target_type: str,
    target_id: Any = None,
    old: Optional[Dict[str, Any]] = None,
    new: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> None:
    details: Dict[str, Any] = {}
    if old is not None:
        details["old"] = old
    if new is not None:
        details["new"] = new
    if actor.impersonated_by:
        details["impersonated_by"] = actor.impersonated_by
    if actor.user_id is None:
        details["system"] = True
    details.update(extra)
    db.add(
        AuditLog(
            actor_id=actor.user_id,
            action=action,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            details=_plain(details) or None,
            ip_address=actor.ip,
        )
    )
    await db.flush()


async def risk_event(
    db: AsyncSession,
    event_type: str,
    severity: RiskSeverity,
    reason: str,
    partner_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    score: int = 0,
    meta: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[AffRiskEvent]:
    """Record a risk event once per ``dedupe_key``."""
    if dedupe_key:
        existing = (await db.execute(select(AffRiskEvent).where(AffRiskEvent.dedupe_key == dedupe_key))).scalar_one_or_none()
        if existing:
            return existing
    row = AffRiskEvent(
        partner_id=partner_id,
        customer_id=customer_id,
        event_type=event_type,
        severity=severity,
        reason=reason[:255],
        risk_score=score,
        metadata_json=_plain(meta) if meta else None,
        dedupe_key=dedupe_key,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        return None
    return row


async def notify(db: AsyncSession, user_id: Optional[str], title: str, message: str, kind: str = "INFO") -> None:
    if not user_id:
        return
    db.add(Notification(user_id=user_id, title=title[:200], message=message, type=kind))
    await db.flush()
