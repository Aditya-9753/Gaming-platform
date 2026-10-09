"""Administrative API endpoints protected by RBAC permissions with mandatory audit logging."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import of_request as client_ip_of
from app.core.constants import PermissionCode, UserRole
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.exceptions import BadRequestException, NotFoundException
from app.games.cricket.market_service import CricketMarketService
from app.games.cricket.providers.mock import MockCricketDataProvider
from app.games.cricket.schemas import CricketSettlementOverrideRequest
from app.models.audit_log import AuditLog
from app.services.admin_service import AdminService
from app.schemas.auth import PASSWORD_PATTERN

router = APIRouter(prefix="/admin", tags=["Admin"])


# =========================================================================
# Request Schemas
# =========================================================================


class UpdateGameSettingsRequest(BaseModel):
    min_bet: Optional[int] = Field(None, gt=0, description="Minimum bet in paise")
    max_bet: Optional[int] = Field(None, gt=0, description="Maximum bet in paise")
    house_edge_percent: Optional[int] = Field(None, ge=0, le=5000, description="House edge in basis points (0-50%)")
    config: Optional[dict] = Field(None)
    is_active: Optional[bool] = Field(None, description="Enable or disable this game")


class SetGameStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Active status of game")


class UpdateUserStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Active or suspended account status")
    reason: str = Field(..., min_length=3, description="Audit reason for status change")


class AdjustBalanceRequest(BaseModel):
    amount: int = Field(..., description="Paise amount to credit (positive) or debit (negative)")
    reason: str = Field(..., min_length=5, description="Mandatory audit reason for adjustment")


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: str = Field(..., min_length=3, max_length=200)
    permission_codes: List[str] = Field(default_factory=list)


class UpdateRolePermissionsRequest(BaseModel):
    permission_codes: List[str] = Field(..., description="List of permission codes to assign to role")


class AssignRoleRequest(BaseModel):
    role_id: int = Field(..., description="Role ID to assign to user")


class CreateAdminUserRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    # Any staff role from the Roles system (not USER / SUPERADMIN)
    role: str = Field(..., min_length=2, max_length=50)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not PASSWORD_PATTERN.fullmatch(value):
            raise ValueError(
                "Password must contain uppercase, lowercase, digit and special character"
            )
        return value


class AdminReplyTicketRequest(BaseModel):
    message: str = Field(..., min_length=1)
    is_internal: bool = Field(False, description="True for internal staff note hidden from player")


class AssignTicketRequest(BaseModel):
    assigned_to_id: Optional[str] = Field(None, description="Staff user ID to assign, or null to unassign")


class UpdateTicketStatusRequest(BaseModel):
    status: str = Field(..., description="OPEN, IN_PROGRESS, RESOLVED, CLOSED")


class BroadcastNotificationRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    message: str = Field(..., min_length=3)
    notification_type: str = Field("SYSTEM", description="SYSTEM, RESULT, ACCOUNT, INFO")
    role_id: Optional[int] = Field(None, description="Optional target role ID filter")


# =========================================================================
# 1. Dashboard Statistics
# =========================================================================


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve comprehensive platform metrics and 7-day activity series."""
    svc = AdminService(db)
    return await svc.get_dashboard_stats()


@router.get("/dashboard/live")
async def get_live_dashboard(
    include_bots: bool = Query(False, description="Include simulated players in the figures"),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Real-time operations view built from live tables (polled by the dashboard)."""
    from app.services.live_dashboard import LiveDashboard

    return await LiveDashboard(db, include_bots=include_bots).build()


@router.get("/dashboard/live/games/{game_id}")
async def get_live_game(
    game_id: str,
    include_bots: bool = Query(False),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Everything in play for one game: current round, its bets, recent results."""
    from app.services.live_dashboard import LiveDashboard

    data = await LiveDashboard(db, include_bots=include_bots).game_detail(game_id)
    if data is None:
        raise NotFoundException("Game not found")
    return data


@router.get("/reports/live")
async def get_live_reports(
    days: int = Query(7, ge=1, le=90),
    include_bots: bool = Query(False),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.REPORT_EXPORT)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Reports & Analytics figures (polled every few seconds by the reports page)."""
    from app.services.live_dashboard import LiveDashboard

    return await LiveDashboard(db, include_bots=include_bots).reports(days)


@router.get("/dashboard/live/drilldown/{kind}")
async def get_live_drilldown(
    kind: str,
    hour: Optional[int] = Query(None, ge=0, le=23),
    include_bots: bool = Query(False),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """The rows behind a dashboard card or chart hour."""
    from app.services.live_dashboard import LiveDashboard

    data = await LiveDashboard(db, include_bots=include_bots).drilldown(kind, hour)
    if data is None:
        raise NotFoundException("Unknown list")
    return data


@router.get("/dashboard/live/bets/{entry_id}")
async def get_live_bet(
    entry_id: str,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """One bet with its round (seed revealed only once the round is finished)."""
    from app.services.live_dashboard import LiveDashboard

    data = await LiveDashboard(db, include_bots=True).bet_detail(entry_id)
    if data is None:
        raise NotFoundException("Bet not found")
    return data


# =========================================================================
# 2. Users Management
# =========================================================================


@router.get("/users")
async def list_users(
    q: Optional[str] = Query(None, description="Search by username, email, or user ID"),
    role_id: Optional[int] = Query(None, description="Filter by role ID"),
    is_active: Optional[bool] = Query(None, description="Filter active/suspended users"),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Search, filter, and paginate platform users."""
    svc = AdminService(db)
    offset = (page - 1) * page_size
    users, total = await svc.search_users(
        q=q,
        role_id=role_id,
        is_active=is_active,
        from_date=from_date,
        to_date=to_date,
        limit=page_size,
        offset=offset,
    )
    items = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role_id": u.role_id,
            "role": u.role.name if u.role else None,
            "is_active": u.is_active,
            "balance": u.wallet.balance if u.wallet else 0,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/users/{user_id}")
async def get_user_details(
    user_id: str,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve full user profile, wallet summary, permissions, and active exclusion."""
    svc = AdminService(db)
    return await svc.get_user_details(user_id)


@router.patch("/users/{user_id}/status")
async def set_user_status(
    user_id: str,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Activate or suspend user account with mandatory audit log."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    user = await svc.set_user_status(
        actor_id=current_user.id,
        target_user_id=user_id,
        is_active=payload.is_active,
        reason=payload.reason,
        ip_address=ip_addr,
    )
    await db.commit()
    return {
        "user_id": user.id,
        "username": user.username,
        "is_active": user.is_active,
        "reason": payload.reason,
    }


@router.get("/users/{user_id}/wallet")
async def get_user_wallet(
    user_id: str,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Inspect user virtual credit wallet balances."""
    svc = AdminService(db)
    return await svc.get_user_wallet(user_id)


@router.get("/users/{user_id}/history")
async def get_user_history(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Inspect user game wager entries."""
    svc = AdminService(db)
    offset = (page - 1) * page_size
    items, total = await svc.get_user_history(user_id=user_id, limit=page_size, offset=offset)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/users/{user_id}/transactions")
async def get_user_transactions(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Inspect user immutable wallet transaction ledger."""
    svc = AdminService(db)
    offset = (page - 1) * page_size
    items, total = await svc.get_user_transactions(user_id=user_id, limit=page_size, offset=offset)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.post("/users/{user_id}/adjust-balance")
async def adjust_user_balance(
    user_id: str,
    payload: AdjustBalanceRequest,
    request: Request,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.WALLET_ADJUST)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually credit or debit user virtual credits with mandatory reason and ledger entry."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    res = await svc.adjust_user_balance(
        actor_id=current_user.id,
        target_user_id=user_id,
        amount=payload.amount,
        reason=payload.reason,
        idempotency_key=idempotency_key,
        ip_address=ip_addr,
    )
    await db.commit()
    return res


# =========================================================================
# 3. Games Management
# =========================================================================


@router.get("/games")
async def list_games_admin(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all games with current operational parameters."""
    svc = AdminService(db)
    return await svc.list_all_games()


@router.patch("/games/{game_id}/status")
async def set_game_status(
    game_id: str,
    payload: SetGameStatusRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Enable or disable game availability with audit log."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    game = await svc.set_game_status(
        actor_id=current_user.id,
        game_id=game_id,
        is_active=payload.is_active,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"game_id": game.id, "is_active": game.is_active}


@router.get("/games/{game_id}/settings")
async def get_game_settings(
    game_id: str,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """View game configuration, limits, and house edge."""
    svc = AdminService(db)
    return await svc.get_game_settings(game_id)


@router.patch("/games/{game_id}/settings")
async def update_game_settings(
    game_id: str,
    payload: UpdateGameSettingsRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update game configuration, bet limits, and house edge with validation and audit log."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    settings = await svc.update_game_settings(
        actor_id=current_user.id,
        game_id=game_id,
        min_bet=payload.min_bet,
        max_bet=payload.max_bet,
        house_edge_percent=payload.house_edge_percent,
        config=payload.config,
        is_active=payload.is_active,
        ip_address=ip_addr,
    )
    await db.commit()
    return {
        "game_id": settings.game_id,
        "min_bet": settings.min_bet,
        "max_bet": settings.max_bet,
        "house_edge_percent": settings.house_edge_percent,
        "config": settings.config,
        "is_active": (await svc.game_repo.get_by_id(game_id)).is_active,
    }


@router.post("/cricket/matches/{match_id}/settle")
async def override_cricket_settlement(
    match_id: str,
    payload: CricketSettlementOverrideRequest,
    request: Request,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=100
    ),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Settle an open winner market manually with before/after audit details."""
    from app.models.cricket import CricketMatchRecord

    match = await db.get(CricketMatchRecord, match_id)
    if not match:
        raise BadRequestException("Cricket match has not been synchronized yet")
    before = {
        "status": match.status,
        "winner": match.winner,
        "abandoned": match.abandoned,
    }
    db.add(
        AuditLog(
            actor_id=current_user.id,
            action="CRICKET_SETTLEMENT_OVERRIDE",
            target_type="CRICKET_MATCH",
            target_id=match_id,
            details={
                "before": before,
                "after": {
                    "status": "ABANDONED" if payload.abandoned else "COMPLETED",
                    "winner": payload.winner,
                    "abandoned": payload.abandoned,
                },
                "reason": payload.reason,
                "idempotency_key": idempotency_key,
            },
            ip_address=client_ip_of(request),
        )
    )
    settled = await CricketMarketService(
        db, provider=MockCricketDataProvider()
    ).settle_match(
        match_id,
        winner=payload.winner,
        abandoned=payload.abandoned,
        source="ADMIN_OVERRIDE",
    )
    return {"match_id": match_id, "settled_predictions": settled, **before}


# =========================================================================
# 4. Live Games & Rounds
# =========================================================================


@router.get("/games/live")
async def get_live_games(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List currently active game rounds across all games with player counts."""
    svc = AdminService(db)
    return await svc.get_live_rounds()


@router.get("/rounds/{round_id}")
async def get_round_details(
    round_id: str,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Fetch complete round details, player bets, and outcomes."""
    svc = AdminService(db)
    return await svc.get_round_details(round_id)


@router.get("/rounds")
async def list_historical_rounds(
    game_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.GAME_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Query historical rounds across all games with filters and pagination."""
    svc = AdminService(db)
    offset = (page - 1) * page_size
    items, total = await svc.list_historical_rounds(
        game_id=game_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=page_size,
        offset=offset,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


# =========================================================================
# 5. Roles, Permissions & Admin Management (Super Admin)
# =========================================================================


@router.get("/roles")
async def list_roles(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all platform roles and permissions (Super Admin only)."""
    svc = AdminService(db)
    return await svc.list_roles()


@router.post("/roles")
async def create_role(
    payload: CreateRoleRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create new custom role with permissions (Super Admin only)."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    role = await svc.create_role(
        actor_id=current_user.id,
        name=payload.name,
        description=payload.description,
        permission_codes=payload.permission_codes,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"id": role.id, "name": role.name, "description": role.description}


@router.put("/roles/{role_id}/permissions")
async def update_role_permissions(
    role_id: int,
    payload: UpdateRolePermissionsRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update assigned permissions for a role (Super Admin only)."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    role = await svc.update_role_permissions(
        actor_id=current_user.id,
        role_id=role_id,
        permission_codes=payload.permission_codes,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"id": role.id, "name": role.name, "permissions": payload.permission_codes}


@router.get("/permissions")
async def list_permissions(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all available platform permissions (Super Admin only)."""
    svc = AdminService(db)
    return await svc.list_permissions()


@router.get("/admins")
async def list_admin_users(
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List administrative and support staff users (Super Admin only)."""
    svc = AdminService(db)
    return await svc.list_admin_users()


@router.post("/admins", status_code=201)
async def create_admin_user(
    payload: CreateAdminUserRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create an administrator/support account; only SUPERADMIN can do this."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    user = await svc.create_admin_user(
        actor_id=current_user.id,
        username=payload.username,
        email=str(payload.email).lower(),
        password=payload.password,
        role_name=payload.role,
        ip_address=ip_addr,
        full_name=payload.full_name,
    )
    await db.commit()
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.name if user.role else payload.role,
        "is_active": user.is_active,
        "totp_enabled": user.totp_enabled,
    }


@router.post("/admins/assign")
async def assign_user_role(
    payload: AssignRoleRequest,
    user_id: str = Query(..., description="Target user ID to promote/demote"),
    request: Request = None,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.ROLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Assign or modify user role (Super Admin only)."""
    ip_addr = client_ip_of(request) if request else None
    svc = AdminService(db)
    user = await svc.assign_user_role(
        actor_id=current_user.id,
        target_user_id=user_id,
        role_id=payload.role_id,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"user_id": user.id, "role_id": user.role_id}


# =========================================================================
# 6. Support Administration
# =========================================================================


@router.get("/support/tickets")
async def list_all_support_tickets(
    status: Optional[str] = Query(None),
    assigned_to_id: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.TICKET_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List all user tickets across the platform."""
    svc = AdminService(db)
    offset = (page - 1) * page_size
    items, total = await svc.list_support_tickets(
        status=status,
        assigned_to_id=assigned_to_id,
        priority=priority,
        limit=page_size,
        offset=offset,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/support/tickets/{ticket_id}")
async def get_admin_ticket_details(
    ticket_id: str,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.TICKET_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Fetch ticket thread including internal staff notes."""
    svc = AdminService(db)
    return await svc.get_admin_ticket_details(ticket_id)


@router.post("/support/tickets/{ticket_id}/reply")
async def reply_support_ticket(
    ticket_id: str,
    payload: AdminReplyTicketRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.TICKET_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Staff reply to customer ticket with optional internal staff note."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    msg = await svc.admin_reply_ticket(
        actor_id=current_user.id,
        ticket_id=ticket_id,
        message=payload.message,
        is_internal=payload.is_internal,
        ip_address=ip_addr,
    )
    await db.commit()
    return {
        "id": msg.id,
        "message": msg.message,
        "is_internal": msg.is_internal,
        "created_at": msg.created_at.isoformat(),
    }


@router.patch("/support/tickets/{ticket_id}/assign")
async def assign_support_ticket(
    ticket_id: str,
    payload: AssignTicketRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.TICKET_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Assign ticket to a staff member with audit log."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    ticket = await svc.assign_ticket(
        actor_id=current_user.id,
        ticket_id=ticket_id,
        assigned_to_id=payload.assigned_to_id,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"id": ticket.id, "assigned_to_id": ticket.assigned_to_id}


@router.patch("/support/tickets/{ticket_id}/status")
async def update_support_ticket_status(
    ticket_id: str,
    payload: UpdateTicketStatusRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.TICKET_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update ticket resolution status with audit log."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    ticket = await svc.update_ticket_status(
        actor_id=current_user.id,
        ticket_id=ticket_id,
        status=payload.status,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"id": ticket.id, "status": ticket.status}


# =========================================================================
# 7. Notifications Broadcast
# =========================================================================


@router.post("/notifications/broadcast")
async def broadcast_notification(
    payload: BroadcastNotificationRequest,
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PermissionCode.NOTIFICATION_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Broadcast in-app notification to all active players with audit log."""
    ip_addr = client_ip_of(request)
    svc = AdminService(db)
    count = await svc.broadcast_notification(
        actor_id=current_user.id,
        title=payload.title,
        message=payload.message,
        notification_type=payload.notification_type,
        role_id=payload.role_id,
        ip_address=ip_addr,
    )
    await db.commit()
    return {"message": "Notification broadcast complete", "recipients_count": count}


# =========================================================================
# 8. Reports & CSV Exports
# =========================================================================


@router.get("/reports/export/{report_type}")
async def export_report_csv(
    report_type: str,
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.REPORT_EXPORT)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export date-range records as CSV (transactions, wagers, users)."""
    svc = AdminService(db)
    csv_data = await svc.export_report_csv(
        report_type=report_type,
        from_date=from_date,
        to_date=to_date,
    )
    filename = f"{report_type}_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# =========================================================================
# 9. Audit Logs Listing (Read-Only)
# =========================================================================


@router.get("/audit-logs")
async def list_audit_logs(
    actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search admin username, action, target or IP"),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(require_permission(PermissionCode.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Inspect immutable audit log records (read-only, filterable)."""
    svc = AdminService(db)
    offset = (page - 1) * page_size
    logs, total = await svc.get_audit_logs(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        limit=page_size,
        offset=offset,
        search=q,
        from_date=from_date,
        to_date=to_date,
    )
    items = [
        {
            "id": l.id,
            "actor_id": l.actor_id,
            "actor_username": l.actor.username if l.actor else None,
            "action": l.action,
            "target_type": l.target_type,
            "target_id": l.target_id,
            "details": l.details,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }
