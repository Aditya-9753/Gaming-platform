"""Repository for support tickets and ticket messages."""

from __future__ import annotations

from typing import List, Optional, Tuple
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.support import SupportMessage, SupportTicket


class SupportRepository:
    """Repository handling SupportTicket and SupportMessage database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_ticket(
        self,
        user_id: str,
        subject: str,
        initial_message: str,
        priority: str = "NORMAL",
    ) -> SupportTicket:
        """Create ticket with initial user message."""
        ticket = SupportTicket(
            user_id=user_id,
            subject=subject,
            priority=priority,
            status="OPEN",
        )
        self.session.add(ticket)
        await self.session.flush()

        msg = SupportMessage(
            ticket_id=ticket.id,
            sender_id=user_id,
            message=initial_message,
            is_internal=False,
        )
        self.session.add(msg)
        await self.session.flush()
        return ticket

    async def get_ticket(self, ticket_id: str) -> Optional[SupportTicket]:
        """Fetch ticket by ID with messages and sender loaded."""
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .options(
                selectinload(SupportTicket.messages).selectinload(SupportMessage.sender),
                selectinload(SupportTicket.user),
                selectinload(SupportTicket.assigned_to),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_user_tickets(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> Tuple[List[SupportTicket], int]:
        """List tickets created by a specific user."""
        stmt = select(SupportTicket).where(SupportTicket.user_id == user_id)
        count_stmt = select(func.count(SupportTicket.id)).where(
            SupportTicket.user_id == user_id
        )

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = (
            stmt.order_by(desc(SupportTicket.created_at))
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def list_all_tickets(
        self,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[SupportTicket], int]:
        """List tickets across the platform (for support / admin)."""
        stmt = select(SupportTicket).options(selectinload(SupportTicket.user))
        count_stmt = select(func.count(SupportTicket.id))

        filters = []
        if status:
            filters.append(SupportTicket.status == status)
        if assigned_to_id:
            filters.append(SupportTicket.assigned_to_id == assigned_to_id)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = (
            stmt.order_by(desc(SupportTicket.created_at))
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    async def add_message(
        self,
        ticket_id: str,
        sender_id: str,
        message: str,
        is_internal: bool = False,
    ) -> SupportMessage:
        """Add a reply or internal note to a ticket."""
        msg = SupportMessage(
            ticket_id=ticket_id,
            sender_id=sender_id,
            message=message,
            is_internal=is_internal,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        assigned_to_id: Optional[str] = None,
    ) -> Optional[SupportTicket]:
        """Update ticket status or assign agent."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            return None

        ticket.status = status
        if assigned_to_id is not None:
            ticket.assigned_to_id = assigned_to_id

        await self.session.flush()
        return ticket
