"""Customer support ticket API routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.support_service import SupportService

router = APIRouter(prefix="/support", tags=["Support"])


class CreateTicketRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=5)
    priority: str = Field("NORMAL", description="LOW, NORMAL, HIGH, URGENT")


class ReplyTicketRequest(BaseModel):
    message: str = Field(..., min_length=1)


@router.post("/tickets")
async def create_ticket(
    payload: CreateTicketRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Submit a support inquiry or issue ticket."""
    svc = SupportService(db)
    ticket = await svc.create_ticket(
        user_id=current_user.id,
        subject=payload.subject,
        message=payload.message,
        priority=payload.priority,
    )
    await db.commit()
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": ticket.created_at.isoformat(),
    }


@router.get("/tickets")
async def list_my_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List support tickets submitted by current user."""
    svc = SupportService(db)
    offset = (page - 1) * page_size
    tickets, total = await svc.list_user_tickets(
        user_id=current_user.id,
        limit=page_size,
        offset=offset,
    )
    items = [
        {
            "id": t.id,
            "subject": t.subject,
            "status": t.status,
            "priority": t.priority,
            "assigned_to_id": t.assigned_to_id,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in tickets
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/tickets/{ticket_id}")
async def get_ticket_details(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Fetch ticket thread with all messages and assignee/status fields."""
    from app.core.exceptions import ForbiddenException

    svc = SupportService(db)
    ticket = await svc.get_ticket(ticket_id)
    if ticket.user_id != current_user.id and (not current_user.role or current_user.role.name not in ("SUPPORT", "ADMIN", "SUPERADMIN")):
        raise ForbiddenException("Access denied to this support ticket")

    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "assigned_to_id": ticket.assigned_to_id,
        "assigned_to_name": ticket.assigned_to.username if ticket.assigned_to else None,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": m.sender.username if m.sender else "Staff",
                "message": m.message,
                "created_at": m.created_at.isoformat(),
            }
            for m in ticket.messages
            if not m.is_internal  # hide internal staff notes from regular players
        ],
    }


@router.post("/tickets/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: str,
    payload: ReplyTicketRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Reply to an open support ticket."""
    from app.core.exceptions import ForbiddenException

    svc = SupportService(db)
    ticket = await svc.get_ticket(ticket_id)
    if ticket.user_id != current_user.id and (not current_user.role or current_user.role.name not in ("SUPPORT", "ADMIN", "SUPERADMIN")):
        raise ForbiddenException("Access denied to this support ticket")

    msg = await svc.reply_ticket(
        ticket_id=ticket_id,
        sender_id=current_user.id,
        message=payload.message,
        is_internal=False,
    )
    await db.commit()
    return {
        "id": msg.id,
        "message": msg.message,
        "created_at": msg.created_at.isoformat(),
    }
