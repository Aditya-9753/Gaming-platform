"""Super-admin operations: staff lifecycle, platform settings, live risk, credit flow.

Operator controls here are transparent and outcome-neutral: the super admin can
watch exposure, pause games, void a round (refunding every stake) and change
limits/payout tables for future rounds — but can never steer a result. Round
outcomes stay provably fair (seed committed before betting opens).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import PermissionCode, TransactionStatus, TransactionType, UserRole
from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.core.redis import get_redis_client
from app.core.security import hash_password
from app.models.game import Game, GameEntry, GameRound
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.audit_repo import AuditRepository
from app.services import platform_settings

router = APIRouter(prefix="/admin", tags=["Super Admin"])
public_router = APIRouter(prefix="/system", tags=["System"])

NON_STAFF_ROLES = {UserRole.USER.value}
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_\-#^]).{12,128}$")


async def require_superadmin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != UserRole.SUPERADMIN.value:
        raise ForbiddenException("Super admin access required")
    return current_user


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _audit(db: AsyncSession, actor: CurrentUser, action: str, target_type: str, target_id: Optional[str], details: Dict[str, Any], request: Request) -> None:
    await AuditRepository(db).create_log(
        action=action, target_type=target_type, actor_id=actor.id, target_id=target_id, details=details, ip_address=_ip(request)
    )


async def _staff(db: AsyncSession, user_id: str, allow_superadmin: bool = False) -> User:
    user = (await db.execute(select(User).options(selectinload(User.role)).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.role:
        raise NotFoundException("Admin account not found")
    role_name = user.role.name.upper()
    if role_name in NON_STAFF_ROLES or (role_name == UserRole.SUPERADMIN.value and not allow_superadmin):
        raise ForbiddenException("This action only applies to staff accounts (not players or the super admin)")
    return user


# =====================================================================
# Public platform config (branding + maintenance banner)
# =====================================================================


@public_router.get("/config")
async def public_config(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    values = await platform_settings.get_all(db)
    return {key: values[key] for key in platform_settings.PUBLIC_KEYS}


# =====================================================================
# Platform settings
# =====================================================================


@router.get("/system-settings")
async def get_system_settings(
    _: CurrentUser = Depends(require_superadmin), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    values = await platform_settings.get_all(db, fresh=True)
    return {
        "values": values,
        "schema": {k: {"type": t.__name__, "description": d} for k, (t, _v, d) in platform_settings.SETTINGS_SCHEMA.items()},
    }


class SettingsUpdate(BaseModel):
    values: Dict[str, Any]


@router.put("/system-settings")
async def update_system_settings(
    payload: SettingsUpdate,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    before = await platform_settings.get_all(db, fresh=True)
    values = await platform_settings.update(db, payload.values, actor.id)
    changed = {k: {"from": before.get(k), "to": values.get(k)} for k in payload.values if before.get(k) != values.get(k)}
    await _audit(db, actor, "SYSTEM_SETTINGS_UPDATED", "SYSTEM", None, {"changes": changed}, request)
    await db.commit()
    return {"values": values}


# =====================================================================
# Staff lifecycle
# =====================================================================


class StaffUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = None
    password: Optional[str] = Field(None, min_length=12, max_length=128)


@router.patch("/admins/{user_id}")
async def update_staff(
    user_id: str,
    payload: StaffUpdate,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    user = await _staff(db, user_id)
    changes: Dict[str, Any] = {}
    if payload.full_name is not None:
        name = payload.full_name.strip() or None
        changes["full_name"] = {"from": user.full_name, "to": name}
        user.full_name = name
    if payload.email is not None:
        email = payload.email.strip().lower() or None
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise BadRequestException("Enter a valid email address")
        if email and email != user.email:
            taken = (await db.execute(select(User.id).where(User.email == email, User.id != user.id))).scalar_one_or_none()
            if taken:
                raise ConflictException("Email is already used by another account")
        changes["email"] = {"from": user.email, "to": email}
        user.email = email
    if payload.role is not None:
        role_name = payload.role.upper()
        if role_name in NON_STAFF_ROLES or role_name == UserRole.SUPERADMIN.value:
            raise BadRequestException("Choose a staff role (not USER or SUPERADMIN)")
        role = (await db.execute(select(Role).where(func.upper(Role.name) == role_name))).scalar_one_or_none()
        if role is None:
            raise BadRequestException(f"Role {role_name} does not exist")
        changes["role"] = {"from": user.role.name, "to": role_name}
        user.role_id = role.id
    if payload.password is not None:
        if not PASSWORD_RE.match(payload.password):
            raise BadRequestException("Password needs 12+ chars with upper, lower, number and symbol")
        user.password_hash = hash_password(payload.password)
        changes["password"] = "reset"
        from app.repositories.token_repo import TokenRepository

        await TokenRepository(db).revoke_all_for_user(user.id)
    if not changes:
        raise BadRequestException("Nothing to update")
    await _audit(db, actor, "ADMIN_UPDATED", "USER", user.id, {"username": user.username, "changes": changes}, request)
    await db.commit()
    return {"id": user.id, "username": user.username, "email": user.email, "role": payload.role.upper() if payload.role else user.role.name}


class StaffStatus(BaseModel):
    is_active: bool
    reason: Optional[str] = Field(None, max_length=255)


@router.patch("/admins/{user_id}/status")
async def set_staff_status(
    user_id: str,
    payload: StaffStatus,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    user = await _staff(db, user_id)
    user.is_active = payload.is_active
    if not payload.is_active:
        from app.repositories.token_repo import TokenRepository

        await TokenRepository(db).revoke_all_for_user(user.id)
    await _audit(db, actor, "ADMIN_UNBLOCKED" if payload.is_active else "ADMIN_BLOCKED", "USER", user.id,
                 {"username": user.username, "reason": payload.reason}, request)
    await db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.delete("/admins/{user_id}")
async def remove_staff(
    user_id: str,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Remove admin access. The account is demoted + disabled (history and ledger are kept)."""
    user = await _staff(db, user_id)
    previous = user.role.name
    player_role = (await db.execute(select(Role).where(Role.name == UserRole.USER.value))).scalar_one()
    user.role_id = player_role.id
    user.is_active = False
    from app.repositories.token_repo import TokenRepository

    await TokenRepository(db).revoke_all_for_user(user.id)
    await _audit(db, actor, "ADMIN_REMOVED", "USER", user.id, {"username": user.username, "previous_role": previous}, request)
    await db.commit()
    return {"id": user.id, "removed": True}


@router.get("/admins/{user_id}/activity")
async def staff_activity(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    user = await _staff(db, user_id, allow_superadmin=True)
    logs, total = await AuditRepository(db).list_logs(actor_id=user.id, limit=page_size, offset=(page - 1) * page_size)
    return {
        "user": {"id": user.id, "username": user.username, "role": user.role.name, "is_active": user.is_active,
                 "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None},
        "items": [
            {"id": l.id, "action": l.action, "target_type": l.target_type, "target_id": l.target_id,
             "details": l.details, "ip_address": l.ip_address, "created_at": l.created_at.isoformat()}
            for l in logs
        ],
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


class DemoCredit(BaseModel):
    amount_paise: int = Field(..., gt=0, le=100_000_000)
    note: Optional[str] = Field(None, max_length=200)


@router.post("/admins/{user_id}/demo-credit")
async def demo_credit(
    user_id: str,
    payload: DemoCredit,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Give an admin account virtual demo credits to test the games."""
    from app.services.wallet_service import WalletService

    user = await _staff(db, user_id, allow_superadmin=True)
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
    if wallet is None:
        db.add(Wallet(id=str(uuid.uuid4()), user_id=user.id, balance=0, locked_balance=0, currency="VIRTUAL"))
        await db.flush()
    tx = await WalletService(db).credit_bonus(
        user_id=user.id,
        amount_paise=payload.amount_paise,
        idempotency_key=f"demo-credit:{uuid.uuid4()}",
        reference="ADMIN_DEMO_CREDIT",
        description=payload.note or f"Demo credits from {actor.username}",
        tx_type=TransactionType.BONUS,
    )
    await _audit(db, actor, "ADMIN_DEMO_CREDIT", "USER", user.id,
                 {"username": user.username, "amount_paise": payload.amount_paise, "note": payload.note}, request)
    await db.commit()
    return {"user_id": user.id, "credited_paise": payload.amount_paise, "balance_after": tx.balance_after}


# =====================================================================
# Live risk monitor (read-only exposure + transparent controls)
# =====================================================================


async def _username_map(db: AsyncSession, ids: List[str]) -> Dict[str, str]:
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(set(ids))))
    return dict(rows.all())


async def _aviator_exposure(db: AsyncSession, state: Any) -> Dict[str, Any]:
    from app.games.aviator.rules import elapsed_since, multiplier_x100_at

    snapshot = await state.get_round_state("aviator")
    if not snapshot:
        return {"status": "IDLE"}
    round_obj = await db.get(GameRound, snapshot.round_id)
    entries = (await db.execute(select(GameEntry).where(GameEntry.round_id == snapshot.round_id))).scalars().all()
    multiplier = 1.0
    params = (round_obj.result or {}) if round_obj else {}
    if round_obj and snapshot.status == "RUNNING" and round_obj.started_at and params.get("growth_rate"):
        multiplier = multiplier_x100_at(
            elapsed_since(round_obj.started_at, datetime.now(timezone.utc)),
            float(params["growth_rate"]), float(params.get("growth_power", 1.0)), str(params.get("growth_model", "power")),
        ) / 100
    names = await _username_map(db, [e.user_id for e in entries])
    active = [e for e in entries if e.status == "PLACED"]
    return {
        "status": snapshot.status,
        "round_id": snapshot.round_id,
        "round_no": snapshot.round_no,
        "multiplier": round(multiplier, 2),
        "bets": len(entries),
        "total_bet": sum(e.bet_amount for e in entries),
        "active_bets": len(active),
        "active_stake": sum(e.bet_amount for e in active),
        "paid_out": sum(e.payout_amount for e in entries if e.status == "WON"),
        "liability_now": int(sum(e.bet_amount for e in active) * multiplier),
        "top": [
            {"username": names.get(e.user_id, "?"), "amount": e.bet_amount, "status": e.status,
             "auto_cashout": (e.selection or {}).get("auto_cashout"), "payout": e.payout_amount}
            for e in sorted(entries, key=lambda e: e.bet_amount, reverse=True)[:25]
        ],
    }


async def _wingo_exposure(db: AsyncSession, state: Any, game_id: str) -> Dict[str, Any]:
    """Read-only aggregate of the open period: one GROUP BY over the bets.

    P/L per number is a pure display calculation from those totals and the
    period's (already fixed) payout table. Nothing here touches the engine or
    the RNG; the outcome was committed before betting opened.
    """
    from app.games.wingo.rules import WingoOutcome, number_colours, number_size, payout_x100, payouts_from_config

    snapshot = await state.get_round_state(game_id)
    if not snapshot:
        return {"game_id": game_id, "status": "IDLE"}
    round_obj = await db.get(GameRound, snapshot.round_id)
    payouts = ((round_obj.result or {}).get("payouts_x100") if round_obj else None) or payouts_from_config(None)

    pick_type = GameEntry.selection["type"].as_string()
    pick_value = GameEntry.selection["value"].as_string()
    rows = (await db.execute(
        select(pick_type, pick_value, func.count(GameEntry.id), func.coalesce(func.sum(GameEntry.bet_amount), 0))
        .where(GameEntry.round_id == snapshot.round_id)
        .group_by(pick_type, pick_value)
    )).all()
    groups = [(str(t or ""), str(v or ""), int(c), int(a)) for t, v, c, a in rows]
    by_pick = {f"{t}:{v}": {"count": c, "amount": a} for t, v, c, a in groups}
    total = sum(a for *_x, a in groups)

    numbers = []
    for n in range(10):
        drawn = WingoOutcome(n, number_colours(n), number_size(n))
        payout = sum(a * payout_x100(t, v, drawn, payouts) // 100 for t, v, _c, a in groups)
        direct = by_pick.get(f"NUMBER:{n}", {"count": 0, "amount": 0})
        numbers.append({
            "number": n,
            "bets": direct["count"],          # bets placed on this exact number
            "staked": direct["amount"],
            "payout": payout,                 # paid to everyone if n is drawn
            "house_net": total - payout,      # house P/L if n is drawn
        })
    return {
        "game_id": game_id,
        "status": snapshot.status,
        "round_id": snapshot.round_id,
        "period": (snapshot.metadata or {}).get("period"),
        "bets": sum(c for _t, _v, c, _a in groups),
        "total_bet": total,
        "by_pick": by_pick,
        "outcomes": numbers,
    }


async def _mines_exposure(db: AsyncSession) -> Dict[str, Any]:
    rows = (await db.execute(
        select(GameEntry).join(GameRound, GameRound.id == GameEntry.round_id)
        .where(GameRound.game_id == "mines", GameEntry.status == "PLACED")
    )).scalars().all()
    names = await _username_map(db, [e.user_id for e in rows])
    sessions = [
        {"username": names.get(e.user_id, "?"), "amount": e.bet_amount,
         "mine_count": (e.selection or {}).get("mine_count"),
         "revealed": len((e.selection or {}).get("revealed_tiles", [])),
         "multiplier": (e.multiplier or 100) / 100,
         "potential_payout": e.bet_amount * (e.multiplier or 100) // 100}
        for e in rows
    ]
    return {
        "active_sessions": len(rows),
        "total_stake": sum(s["amount"] for s in sessions),
        "potential_payout": sum(s["potential_payout"] for s in sessions),
        "sessions": sorted(sessions, key=lambda s: s["potential_payout"], reverse=True)[:25],
    }


@router.get("/risk/live")
async def live_risk(
    _: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    from app.games.base.state import RedisRoundStateManager
    from app.games.wingo.rules import MODES

    state = RedisRoundStateManager(get_redis_client())
    games = {g.id: g.is_active for g in (await db.execute(select(Game))).scalars().all()}
    return {
        "games": games,
        "aviator": await _aviator_exposure(db, state),
        "wingo": [await _wingo_exposure(db, state, game_id) for game_id in MODES],
        "mines": await _mines_exposure(db),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


class VoidRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)


@router.post("/rounds/{round_id}/void")
async def void_round(
    round_id: str,
    payload: VoidRequest,
    request: Request,
    actor: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Refund every still-open stake in a round (e.g. after an incident). Outcome is untouched."""
    from app.repositories.entry_repo import EntryRepository
    from app.services.wallet_service import WalletService

    round_obj = await db.get(GameRound, round_id)
    if not round_obj:
        raise NotFoundException("Round not found")
    entries = (await db.execute(select(GameEntry).where(GameEntry.round_id == round_id, GameEntry.status == "PLACED"))).scalars().all()
    wallet, repo = WalletService(db), EntryRepository(db)
    refunded = 0
    for entry in entries:
        await wallet.refund(
            user_id=entry.user_id, amount_paise=entry.bet_amount,
            reference=f"void:{round_id}:{entry.id}", idempotency_key=f"void:{round_id}:{entry.id}",
        )
        await repo.update_settlement(entry_id=entry.id, status="REFUNDED", payout_amount=entry.bet_amount, multiplier=100)
        refunded += entry.bet_amount
    round_obj.result = {**(round_obj.result or {}), "voided": True, "void_reason": payload.reason}
    await _audit(db, actor, "ROUND_VOIDED", "ROUND", round_id,
                 {"game_id": round_obj.game_id, "round_no": round_obj.round_no, "entries": len(entries),
                  "refunded_paise": refunded, "reason": payload.reason}, request)
    await db.commit()
    return {"round_id": round_id, "refunded_entries": len(entries), "refunded_paise": refunded}


# =====================================================================
# Credit flow (virtual economy) — super admin only
# =====================================================================


@router.get("/finance/overview")
async def finance_overview(
    days: int = Query(1, ge=1, le=3650),
    _: CurrentUser = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    wallets = (await db.execute(select(func.count(Wallet.id), func.coalesce(func.sum(Wallet.balance), 0), func.coalesce(func.sum(Wallet.locked_balance), 0)))).one()
    tx_rows = (await db.execute(
        select(WalletTransaction.type, func.count(WalletTransaction.id), func.coalesce(func.sum(WalletTransaction.amount), 0))
        .where(WalletTransaction.created_at >= since, WalletTransaction.status == TransactionStatus.COMPLETED.value)
        .group_by(WalletTransaction.type)
    )).all()
    game_rows = (await db.execute(
        select(GameRound.game_id, func.count(GameEntry.id), func.coalesce(func.sum(GameEntry.bet_amount), 0), func.coalesce(func.sum(GameEntry.payout_amount), 0))
        .join(GameRound, GameRound.id == GameEntry.round_id)
        .where(GameEntry.created_at >= since, GameEntry.status.in_(["WON", "LOST"]))
        .group_by(GameRound.game_id)
    )).all()
    demo = (await db.execute(
        select(func.count(WalletTransaction.id), func.coalesce(func.sum(WalletTransaction.amount), 0))
        .where(WalletTransaction.created_at >= since, WalletTransaction.reference == "ADMIN_DEMO_CREDIT")
    )).one()
    games = [
        {"game_id": g, "bets": n, "wagered": int(w), "paid_out": int(p), "house_net": int(w) - int(p)}
        for g, n, w, p in game_rows
    ]
    return {
        "window_days": days,
        "wallets": {"count": wallets[0], "total_balance": int(wallets[1]), "locked": int(wallets[2])},
        "transactions": {t: {"count": n, "amount": int(a)} for t, n, a in tx_rows},
        "games": sorted(games, key=lambda g: g["wagered"], reverse=True),
        "totals": {
            "wagered": sum(g["wagered"] for g in games),
            "paid_out": sum(g["paid_out"] for g in games),
            "house_net": sum(g["house_net"] for g in games),
        },
        "demo_credits": {"count": demo[0], "amount": int(demo[1])},
    }
