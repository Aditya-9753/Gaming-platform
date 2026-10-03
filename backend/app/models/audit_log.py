"""SQLAlchemy model for administrative and system audit logs."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """Immutable audit trail of administrator, system, and security actions."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    actor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # AES-256-GCM seal of this row (see app.security.integrity)
    integrity_seal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Required audit log compound index
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
    )

    # Relationships
    actor: Mapped[Optional["User"]] = relationship("User")


from sqlalchemy import event


@event.listens_for(AuditLog, "before_update")
def _prevent_audit_log_update(mapper: Any, connection: Any, target: AuditLog) -> None:
    """Enforce append-only: audit log entries cannot be modified once written."""
    raise PermissionError("AuditLog records are append-only and cannot be modified.")


@event.listens_for(AuditLog, "before_delete")
def _prevent_audit_log_delete(mapper: Any, connection: Any, target: AuditLog) -> None:
    """Enforce append-only: audit log entries cannot be deleted."""
    raise PermissionError("AuditLog records are append-only and cannot be deleted.")
