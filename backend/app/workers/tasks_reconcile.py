"""Wallet reconciliation background task."""

from __future__ import annotations

import asyncio
from typing import Dict
from sqlalchemy import func, select

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services.notification_service import NotificationService
from app.workers.celery_app import celery_app

logger = get_logger("worker_reconcile")

_ADMIN_ROLES = ("ADMIN", "SUPERADMIN")


async def _reconcile_all_wallets() -> Dict[str, int]:
    """Compare wallets with the most recent completed ledger balance snapshot."""
    latest_ledger = (
        select(
            WalletTransaction.wallet_id.label("wallet_id"),
            WalletTransaction.balance_after.label("ledger_balance"),
            func.row_number()
            .over(
                partition_by=WalletTransaction.wallet_id,
                order_by=(
                    WalletTransaction.created_at.desc(),
                    WalletTransaction.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .where(WalletTransaction.status == "COMPLETED")
        .subquery()
    )

    async with get_session_factory()() as session:
        result = await session.execute(
            select(
                Wallet,
                func.coalesce(latest_ledger.c.ledger_balance, 0).label(
                    "ledger_balance"
                ),
            )
            .outerjoin(
                latest_ledger,
                (latest_ledger.c.wallet_id == Wallet.id)
                & (latest_ledger.c.row_number == 1),
            )
        )
        wallet_rows = result.all()
        discrepancies = []
        for wallet, ledger_balance in wallet_rows:
            if wallet.balance != ledger_balance:
                discrepancies.append((wallet, int(ledger_balance)))
                logger.error(
                    "WALLET RECONCILIATION ALERT: balance differs from completed ledger",
                    wallet_id=wallet.id,
                    user_id=wallet.user_id,
                    wallet_balance=wallet.balance,
                    ledger_balance=int(ledger_balance),
                    difference=wallet.balance - int(ledger_balance),
                )

        if discrepancies:
            admin_ids = (
                await session.execute(
                    select(User.id)
                    .join(Role, Role.id == User.role_id)
                    .where(
                        func.upper(Role.name).in_(_ADMIN_ROLES),
                        User.is_active.is_(True),
                    )
                )
            ).scalars().all()
            wallet_details = ", ".join(
                f"{wallet.id} (balance={wallet.balance}, ledger={ledger_balance})"
                for wallet, ledger_balance in discrepancies[:10]
            )
            suffix = (
                f" Showing first 10: {wallet_details}"
                if len(discrepancies) > 10
                else f" Wallets: {wallet_details}"
            )
            message = (
                f"Nightly reconciliation found {len(discrepancies)} wallet balance "
                f"mismatch(es).{suffix}"
            )
            notification_service = NotificationService(session)
            for admin_id in admin_ids:
                await notification_service.send_notification(
                    user_id=admin_id,
                    title="Wallet reconciliation mismatch",
                    message=message,
                    notification_type="ALERT",
                )
            await session.commit()

        return {
            "checked": len(wallet_rows),
            "mismatches": len(discrepancies),
        }


@celery_app.task(name="app.workers.tasks_reconcile.reconcile_wallets_task")
def reconcile_wallets_task() -> Dict[str, int]:
    """Periodic task verifying zero discrepancies between wallet balances and ledger rows."""
    logger.info("Starting wallet ledger reconciliation task")
    result = asyncio.run(_reconcile_all_wallets())
    logger.info("Finished wallet ledger reconciliation task", result=result)
    return result
