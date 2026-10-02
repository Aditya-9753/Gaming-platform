"""Repository for AuditLog database operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit_log import AuditLog


class AuditRepository:
    """Repository handling AuditLog records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_log(
        self,
        action: str,
        target_type: str,
        actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        """Create an immutable audit log entry."""
        log = AuditLog(
            action=action,
            target_type=target_type,
            actor_id=actor_id,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_logs(
        self,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Tuple[List[AuditLog], int]:
        """Query audit trail with filtering, free-text search and pagination."""
        stmt = select(AuditLog).options(selectinload(AuditLog.actor))
        count_stmt = select(func.count(AuditLog.id))

        filters = []
        if actor_id:
            filters.append(AuditLog.actor_id == actor_id)
        if action:
            filters.append(AuditLog.action == action)
        if target_type:
            filters.append(AuditLog.target_type == target_type)
        if from_date:
            filters.append(AuditLog.created_at >= from_date)
        if to_date:
            filters.append(AuditLog.created_at <= to_date)
        if search:
            from sqlalchemy import or_

            from app.models.user import User

            term = f"%{search.strip()}%"
            actor_ids = select(User.id).where(User.username.ilike(term))
            filters.append(
                or_(
                    AuditLog.action.ilike(term),
                    AuditLog.target_type.ilike(term),
                    AuditLog.target_id.ilike(term),
                    AuditLog.ip_address.ilike(term),
                    AuditLog.actor_id.in_(actor_ids),
                )
            )

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar_one() or 0

        stmt = stmt.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
        logs_res = await self.session.execute(stmt)
        return list(logs_res.scalars().all()), total
