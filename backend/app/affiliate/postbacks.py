"""Outbound partner postbacks (registration / FTD / deposit) with retry.

Partners save a URL template per event with macros {click_id}, {sub1}..{sub5},
{amount}, {customer}, {event}. Events are queued as log rows and sent by the
worker. URLs must be public http(s): private / loopback / link-local hosts are
refused at save time and again at send time (SSRF protection).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from datetime import timedelta
from typing import Any, Dict
from urllib.parse import quote, urlsplit

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.constants import PostbackEvent, RecordStatus
from app.affiliate.util import utcnow
from app.core.exceptions import BadRequestException
from app.core.logging import get_logger
from app.models.affiliate import AffPartnerPostback, AffPartnerPostbackLog

logger = get_logger("aff_postbacks")

MACROS = ("click_id", "sub1", "sub2", "sub3", "sub4", "sub5", "amount", "customer", "event")
MAX_ATTEMPTS = 5


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


def validate_template(url: str) -> str:
    url = (url or "").strip()
    parts = urlsplit(url.replace("{", "").replace("}", ""))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BadRequestException("Postback URL must start with http:// or https://")
    if len(url) > 1000:
        raise BadRequestException("Postback URL is too long")
    host = parts.hostname.lower()
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        raise BadRequestException("Postback URL must be a public address")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise BadRequestException("Postback URL must be a public address")
    except ValueError:
        pass
    return url


def render(template: str, macros: Dict[str, Any]) -> str:
    url = template
    for name in MACROS:
        value = macros.get(name)
        url = url.replace("{" + name + "}", quote("" if value is None else str(value), safe=""))
    return url


async def queue(db: AsyncSession, partner_id: int, event: PostbackEvent, event_ref: str, macros: Dict[str, Any]) -> int:
    templates = (
        await db.execute(
            select(AffPartnerPostback).where(
                AffPartnerPostback.partner_id == partner_id, AffPartnerPostback.event_type == event,
                AffPartnerPostback.status == RecordStatus.ACTIVE,
            )
        )
    ).scalars().all()
    created = 0
    for pb in templates:
        log = AffPartnerPostbackLog(partner_postback_id=pb.id, event_ref=event_ref,
                                    url_sent=render(pb.url_template, {**macros, "event": event.value})[:2000],
                                    status="PENDING", next_attempt_at=utcnow())
        try:
            async with db.begin_nested():
                db.add(log)
                await db.flush()
            created += 1
        except IntegrityError:
            continue
    return created


async def send_pending(db: AsyncSession, limit: int = 100) -> int:
    import httpx

    now = utcnow()
    logs = (
        await db.execute(
            select(AffPartnerPostbackLog)
            .where(AffPartnerPostbackLog.status == "PENDING",
                   or_(AffPartnerPostbackLog.next_attempt_at.is_(None), AffPartnerPostbackLog.next_attempt_at <= now))
            .order_by(AffPartnerPostbackLog.id)
            .limit(limit)
        )
    ).scalars().all()
    if not logs:
        return 0
    sent = 0
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        for log in logs:
            log.attempts = (log.attempts or 0) + 1
            host = urlsplit(log.url_sent).hostname or ""
            public = await asyncio.get_running_loop().run_in_executor(None, _host_is_public, host)
            if not public:
                log.status, log.response_code = "FAILED", None
                continue
            try:
                resp = await client.get(log.url_sent)
                log.response_code = resp.status_code
                if resp.status_code < 400:
                    log.status, log.sent_at = "SENT", utcnow()
                    sent += 1
                    continue
            except Exception as exc:
                logger.info("Postback attempt failed", log_id=log.id, error=str(exc))
            if log.attempts >= MAX_ATTEMPTS:
                log.status = "FAILED"
            else:
                log.next_attempt_at = utcnow() + timedelta(minutes=2 ** log.attempts)
    await db.commit()
    return sent


async def test_fire(template: str) -> Dict[str, Any]:
    """Partner-triggered test call with sample macros (same SSRF checks)."""
    import httpx

    url = render(validate_template(template), {"click_id": "TESTCLICKID0000000000000000", "sub1": "test", "amount": "10.00",
                                               "customer": "0", "event": "TEST"})
    host = urlsplit(url).hostname or ""
    if not await asyncio.get_running_loop().run_in_executor(None, _host_is_public, host):
        raise BadRequestException("Postback URL must resolve to a public address")
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            resp = await client.get(url)
        return {"url": url, "status_code": resp.status_code}
    except Exception as exc:
        return {"url": url, "status_code": None, "error": str(exc)[:200]}

