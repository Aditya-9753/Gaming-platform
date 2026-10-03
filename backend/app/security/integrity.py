"""Tamper evidence for the money ledger and the audit trail.

ORM listeners seal every new ``WalletTransaction`` and ``AuditLog`` row with
AES-256-GCM (``app.security.crypto_engine``). ``verify`` re-reads rows and
reports any whose current values no longer match their seal, i.e. rows that
were edited outside the application.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.wallet import WalletTransaction
from app.security.crypto_engine import get_integrity_engine

# kind -> (model, sealed columns). Server-generated columns (created_at) are not sealed.
SEALED: Dict[str, Any] = {
    "ledger": (WalletTransaction, (
        "id", "wallet_id", "idempotency_key", "type", "amount",
        "balance_before", "balance_after", "status", "reference",
    )),
    "audit": (AuditLog, ("id", "actor_id", "action", "target_type", "target_id", "details", "ip_address")),
}
_KIND_BY_MODEL = {model: kind for kind, (model, _cols) in SEALED.items()}


def row_fields(kind: str, row: Any) -> Dict[str, Any]:
    return {col: getattr(row, col) for col in SEALED[kind][1]}


def _seal_target(target: Any) -> None:
    engine = get_integrity_engine()
    if engine is None:
        return
    if not target.id:
        target.id = str(uuid.uuid4())
    kind = _KIND_BY_MODEL[type(target)]
    target.integrity_seal = engine.seal(kind, target.id, row_fields(kind, target))


@event.listens_for(WalletTransaction, "before_insert")
@event.listens_for(WalletTransaction, "before_update")
@event.listens_for(AuditLog, "before_insert")
def _seal_on_write(_mapper: Any, _connection: Any, target: Any) -> None:
    _seal_target(target)


async def status(db: AsyncSession) -> Dict[str, Any]:
    engine = get_integrity_engine()
    counts = {}
    for kind, (model, _cols) in SEALED.items():
        total, sealed = (await db.execute(
            select(func.count(model.id), func.count(model.integrity_seal))
        )).one()
        counts[kind] = {"total": int(total), "sealed": int(sealed), "unsealed": int(total) - int(sealed)}
    return {
        "configured": engine is not None,
        "algorithm": "AES-256-GCM (96-bit nonce, row id as associated data)",
        "key_id": engine.key_id if engine else None,
        "tables": counts,
    }


async def verify(db: AsyncSession, kind: str, limit: int = 5000) -> Dict[str, Any]:
    """Check the newest ``limit`` rows of one table against their seals."""
    engine = get_integrity_engine()
    if engine is None:
        raise RuntimeError("AUDIT_ENCRYPTION_KEY is not configured")
    model, _cols = SEALED[kind]
    rows = (await db.execute(select(model).order_by(model.created_at.desc()).limit(limit))).scalars().all()
    summary = {"ok": 0, "tampered": 0, "unsealed": 0}
    problems: List[Dict[str, Any]] = []
    for row in rows:
        result = engine.check(kind, row.id, row.integrity_seal, row_fields(kind, row))
        summary[result["status"]] += 1
        if result["status"] == "tampered" and len(problems) < 50:
            problems.append({
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "label": getattr(row, "action", None) or f"{getattr(row, 'type', '')} {getattr(row, 'amount', '')}",
                **result,
            })
    return {"kind": kind, "checked": len(rows), **summary, "tampered_rows": problems}


async def seal_unsealed(db: AsyncSession, kind: str, limit: int = 20000) -> int:
    """Seal rows written before the key existed. Uses a core UPDATE (audit rows are append-only in the ORM)."""
    engine = get_integrity_engine()
    if engine is None:
        raise RuntimeError("AUDIT_ENCRYPTION_KEY is not configured")
    model, _cols = SEALED[kind]
    rows = (await db.execute(select(model).where(model.integrity_seal.is_(None)).limit(limit))).scalars().all()
    for row in rows:
        await db.execute(
            update(model).where(model.id == row.id)
            .values(integrity_seal=engine.seal(kind, row.id, row_fields(kind, row)))
            .execution_options(synchronize_session=False)
        )
    return len(rows)


__all__ = ["SEALED", "row_fields", "status", "verify", "seal_unsealed"]
