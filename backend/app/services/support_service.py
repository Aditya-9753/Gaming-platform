"""Customer support service managing help tickets and messages."""

from __future__ import annotations

from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.support import SupportMessage, SupportTicket
from app.repositories.support_repo import SupportRepository


class SupportService:
    """Service handling support tickets, inquiries, and staff responses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.support_repo = SupportRepository(session)

    async def create_ticket(
        self,
        user_id: str,
        subject: str,
        message: str,
        priority: str = "NORMAL",
    ) -> SupportTicket:
        """Submit a new player support ticket."""
        if not subject.strip():
            raise BadRequestException("Subject cannot be empty")
        if not message.strip():
            raise BadRequestException("Message cannot be empty")

        return await self.support_repo.create_ticket(
            user_id=user_id,
            subject=subject.strip(),
            initial_message=message.strip(),
            priority=priority,
        )

    async def get_ticket(self, ticket_id: str) -> SupportTicket:
        """Fetch ticket by ID."""
        ticket = await self.support_repo.get_ticket(ticket_id)
        if not ticket:
            raise NotFoundException("Support ticket not found")
        return ticket

    async def list_user_tickets(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> Tuple[List[SupportTicket], int]:
        """List tickets created by a specific user."""
        return await self.support_repo.list_user_tickets(user_id, limit, offset)

    async def list_all_tickets(
        self,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[SupportTicket], int]:
        """List tickets across platform for support staff."""
        return await self.support_repo.list_all_tickets(status, assigned_to_id, limit, offset)

    async def reply_ticket(
        self,
        ticket_id: str,
        sender_id: str,
        message: str,
        is_internal: bool = False,
    ) -> SupportMessage:
        """Reply to an existing support ticket."""
        await self.get_ticket(ticket_id)
        if not message.strip():
            raise BadRequestException("Message cannot be empty")

        return await self.support_repo.add_message(
            ticket_id=ticket_id,
            sender_id=sender_id,
            message=message.strip(),
            is_internal=is_internal,
        )

    async def update_status(
        self,
        ticket_id: str,
        status: str,
        assigned_to_id: Optional[str] = None,
    ) -> SupportTicket:
        """Update ticket lifecycle state (OPEN, IN_PROGRESS, RESOLVED, CLOSED)."""
        ticket = await self.support_repo.update_ticket_status(
            ticket_id=ticket_id,
            status=status,
            assigned_to_id=assigned_to_id,
        )
        if not ticket:
            raise NotFoundException("Support ticket not found")
        return ticket
