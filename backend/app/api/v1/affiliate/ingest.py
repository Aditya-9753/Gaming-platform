"""Operator S2S ingest API (/api/v1/ingest/...), HMAC-SHA256 signed.

Headers: ``X-Timestamp`` (unix seconds) and ``X-Signature`` =
hex(HMAC_SHA256(secret, "<timestamp>.<raw body>")). Requests older than the
tolerance (5 minutes) are rejected. A duplicate returns 200 with the record of
the first delivery; a new event returns 201.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import of_request as client_ip_of
from app.affiliate import ingest, serialize
from app.affiliate.constants import IngestEventType
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import BadRequestException, ForbiddenException

router = APIRouter(prefix="/ingest", tags=["Operator ingest (S2S)"])

_MAX_BODY = 5 * 1024 * 1024


async def _accept(request: Request, response: Response, db: AsyncSession, event_type: IngestEventType) -> Dict[str, Any]:
    body = await request.body()
    if len(body) > _MAX_BODY:
        raise BadRequestException("Body too large (5 MB max)")
    ingest.verify_signature(body, request.headers.get("x-timestamp"), request.headers.get("x-signature"))
    allowed = {ip.strip() for ip in (get_settings().AFFILIATE_INGEST_IPS or "").split(",") if ip.strip()}
    if allowed and (client_ip_of(request)) not in allowed:
        raise ForbiddenException("Source address not allowed")
    try:
        payload = json.loads(body or b"{}")
    except ValueError as exc:
        raise BadRequestException("Body must be JSON") from exc
    if not isinstance(payload, dict):
        raise BadRequestException("Body must be a JSON object")
    event, duplicate = await ingest.receive(db, event_type, payload, source="S2S", signature_ok=True)
    response.status_code = 200 if duplicate else 201
    return {"duplicate": duplicate, **serialize.ingest_event(event)}


@router.post("/registration")
async def registration(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    return await _accept(request, response, db, IngestEventType.REGISTRATION)


@router.post("/deposit")
async def deposit(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    return await _accept(request, response, db, IngestEventType.DEPOSIT)


@router.post("/revenue")
async def revenue(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    return await _accept(request, response, db, IngestEventType.REVENUE)


@router.post("/reversal")
async def reversal(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    return await _accept(request, response, db, IngestEventType.REVERSAL)
