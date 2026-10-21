"""Super admin: bonus promo codes (create, pause / resume, see who used them).

New accounts get no automatic bonus; these codes are the only way a player receives one.
Every redemption is a BONUS ledger row, once per player per code.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.superadmin import _audit, require_superadmin
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models.promo import PromoCode, PromoRedemption
from app.models.user import User
from app.services import promo_service

router = APIRouter(prefix="/admin/promo-codes", tags=["Super Admin"])

MAX_AMOUNT_PAISE = 10_000_00  # ₹10,000 per redemption


class PromoCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=32)
    amount_paise: int = Field(..., gt=0, le=MAX_AMOUNT_PAISE)
    max_uses: Optional[int] = Field(None, gt=0, le=1_000_000)
    expires_at: Optional[datetime] = None
    note: Optional[str] = Field(None, max_length=200)


class PromoUpdate(BaseModel):
    is_active: Optional[bool] = None
    max_uses: Optional[int] = Field(None, gt=0, le=1_000_000)
    clear_max_uses: bool = False
    expires_at: Optional[datetime] = None
    clear_expiry: bool = False
    note: Optional[str] = Field(None, max_length=200)


def _future(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if value <= datetime.now(timezone.utc):
        raise BadRequestException("Expiry must be in the future")
    return value


async def _get(db: AsyncSession, promo_id: str) -> PromoCode:
    promo = await db.get(PromoCode, promo_id)
    if promo is None:
        raise NotFoundException("Promo code not found")
    return promo


@router.get("")
async def list_promo_codes(
    _actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    promos = (await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))).scalars().all()
    return {"items": [promo_service.to_dict(p) for p in promos]}


@router.post("", status_code=201)
async def create_promo_code(
    payload: PromoCreate,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    code = promo_service.normalize(payload.code)
    if not promo_service.CODE_RE.match(code):
        raise BadRequestException("Use 3-32 letters, numbers, - or _ for the code")
    if await promo_service.find(db, code):
        raise ConflictException("A promo code with this name already exists")
    promo = PromoCode(
        id=str(uuid.uuid4()), code=code, amount_paise=payload.amount_paise, max_uses=payload.max_uses,
        used_count=0, expires_at=_future(payload.expires_at), is_active=True,
        note=(payload.note or "").strip() or None, created_by_id=actor.id,
    )
    db.add(promo)
    await db.flush()
    await _audit(db, actor, "PROMO_CODE_CREATED", "PROMO_CODE", promo.id,
                 {"code": code, "amount_paise": promo.amount_paise, "max_uses": promo.max_uses,
                  "expires_at": promo.expires_at.isoformat() if promo.expires_at else None}, request)
    await db.commit()
    await db.refresh(promo)
    return promo_service.to_dict(promo)


@router.patch("/{promo_id}")
async def update_promo_code(
    promo_id: str,
    payload: PromoUpdate,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    promo = await _get(db, promo_id)
    changes: Dict[str, Any] = {}
    if payload.is_active is not None:
        promo.is_active = changes["is_active"] = payload.is_active
    if payload.clear_max_uses:
        promo.max_uses = changes["max_uses"] = None
    elif payload.max_uses is not None:
        promo.max_uses = changes["max_uses"] = payload.max_uses
    if payload.clear_expiry:
        promo.expires_at = None
        changes["expires_at"] = None
    elif payload.expires_at is not None:
        promo.expires_at = _future(payload.expires_at)
        changes["expires_at"] = promo.expires_at.isoformat()
    if payload.note is not None:
        promo.note = changes["note"] = payload.note.strip() or None
    if changes:
        await _audit(db, actor, "PROMO_CODE_UPDATED", "PROMO_CODE", promo.id, {"code": promo.code, **changes}, request)
        await db.commit()
        await db.refresh(promo)
    return promo_service.to_dict(promo)


@router.get("/{promo_id}/redemptions")
async def promo_redemptions(
    promo_id: str,
    _actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    promo = await _get(db, promo_id)
    rows = (await db.execute(
        select(PromoRedemption, User.username, User.phone)
        .join(User, User.id == PromoRedemption.user_id)
        .where(PromoRedemption.promo_code_id == promo.id)
        .order_by(PromoRedemption.created_at.desc())
        .limit(500)
    )).all()
    items: List[Dict[str, Any]] = [
        {"user_id": r.user_id, "username": username, "phone": phone, "amount_paise": r.amount_paise,
         "redeemed_at": r.created_at.isoformat() if r.created_at else None}
        for r, username, phone in rows
    ]
    return {"promo": promo_service.to_dict(promo), "items": items}
