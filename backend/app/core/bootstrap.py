"""Local/dev bootstrap: seed reference data and hard-coded staff accounts.

Runs on application startup when APP_ENV is not production and
SEED_DEFAULT_ACCOUNTS is true. Idempotent: existing accounts are re-aligned
to the role / password below so these credentials always work locally.

DO NOT rely on these accounts in production — they are never seeded there.
"""

from __future__ import annotations

import uuid
from typing import List, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import TransactionStatus, TransactionType, UserRole
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction

logger = get_logger("bootstrap")


class StaffAccount(TypedDict):
    username: str
    email: str
    password: str
    role: UserRole


# Hard-coded local accounts (login with email + password).
DEFAULT_ACCOUNTS: List[StaffAccount] = [
    {"username": "superadmin", "email": "superadmin@gamingplatform.com", "password": "SuperAdmin@123", "role": UserRole.SUPERADMIN},
    {"username": "admin", "email": "admin@gamingplatform.com", "password": "Admin@12345", "role": UserRole.ADMIN},
    {"username": "support", "email": "support@gamingplatform.com", "password": "Support@123", "role": UserRole.SUPPORT},
    {"username": "auditor", "email": "auditor@gamingplatform.com", "password": "Auditor@123", "role": UserRole.AUDITOR},
    {"username": "player", "email": "player@gamingplatform.com", "password": "Player@123", "role": UserRole.USER},
]

_INITIAL_STAFF_BALANCE = 1_000_000  # 10,000 credits in paise


async def _get_or_create_role(session: AsyncSession, role: UserRole) -> Role:
    result = await session.execute(select(Role).where(Role.name == role.value))
    db_role = result.scalar_one_or_none()
    if db_role is None:
        db_role = Role(name=role.value, description=f"System role for {role.value.lower()}")
        session.add(db_role)
        await session.flush()
    return db_role


async def seed_default_accounts(session: AsyncSession) -> None:
    """Create or re-align every account in DEFAULT_ACCOUNTS."""
    for account in DEFAULT_ACCOUNTS:
        role = await _get_or_create_role(session, account["role"])
        email = account["email"].lower()

        result = await session.execute(
            select(User).where((User.email == email) | (User.username == account["username"]))
        )
        user = result.scalars().first()

        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                username=account["username"],
                email=email,
                password_hash=hash_password(account["password"]),
                role_id=role.id,
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            await session.flush()

            wallet = Wallet(
                id=str(uuid.uuid4()),
                user_id=user.id,
                balance=_INITIAL_STAFF_BALANCE,
                locked_balance=0,
                currency="VIRTUAL",
            )
            session.add(wallet)
            await session.flush()
            session.add(
                WalletTransaction(
                    id=str(uuid.uuid4()),
                    wallet_id=wallet.id,
                    idempotency_key=f"bootstrap-{user.id}",
                    type=TransactionType.BONUS.value,
                    amount=_INITIAL_STAFF_BALANCE,
                    balance_before=0,
                    balance_after=_INITIAL_STAFF_BALANCE,
                    status=TransactionStatus.COMPLETED.value,
                    description="Initial bootstrap credit grant",
                    reference="SYSTEM_PROVISION",
                )
            )
            logger.info("Default account created", username=account["username"], role=role.name)
            continue

        user.role_id = role.id
        user.is_active = True
        user.is_verified = True
        if not verify_password(account["password"], user.password_hash):
            user.password_hash = hash_password(account["password"])

    await session.commit()


async def bootstrap_dev_data() -> None:
    """Seed roles/permissions, games, settings and default accounts (non-prod only)."""
    settings = get_settings()
    if settings.is_production or not settings.SEED_DEFAULT_ACCOUNTS:
        return

    async with get_session_factory()() as session:
        try:
            try:
                from scripts.seed_db import (
                    seed_games,
                    seed_roles_and_permissions,
                    seed_system_settings,
                )

                await seed_roles_and_permissions(session)
                await seed_games(session)
                await seed_system_settings(session)
            except ImportError:
                logger.warning("scripts.seed_db not importable; skipping reference data seed")

            await seed_default_accounts(session)
            logger.info("Development bootstrap completed")
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Development bootstrap failed (is PostgreSQL running and migrated?)",
                error=str(exc),
            )
