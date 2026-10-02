"""CLI script to provision or promote a platform Super Administrator."""

import argparse
import asyncio
from getpass import getpass
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionStatus, TransactionType, UserRole
from app.core.database import close_db, get_session_factory, init_db
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.services.two_factor_service import two_factor_service

logger = get_logger("create_super_admin")


async def create_or_promote_super_admin(
    username: str,
    email: str,
    password: str,
    reset_authenticator: bool = False,
) -> None:
    """Create a new super administrator or promote existing user."""
    await init_db()
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            # 1. Ensure SUPERADMIN role exists
            res_role = await session.execute(
                select(Role).where(Role.name == UserRole.SUPERADMIN.value)
            )
            superadmin_role = res_role.scalar_one_or_none()
            if not superadmin_role:
                superadmin_role = Role(
                    name=UserRole.SUPERADMIN.value,
                    description="Super Administrator with unrestricted access",
                )
                session.add(superadmin_role)
                await session.flush()

            # 2. Check if user already exists
            res_user = await session.execute(
                select(User).where((User.username == username) | (User.email == email))
            )
            user = res_user.scalar_one_or_none()

            if user and (user.username != username or user.email.lower() != email.lower()):
                raise ValueError(
                    "Username and email resolve to different account details; "
                    "provide the exact username and email of the same account."
                )

            hashed_pw = hash_password(password)

            if user:
                user.role_id = superadmin_role.id
                user.password_hash = hashed_pw
                user.is_active = True
                user.is_verified = True
                logger.info(f"Existing user '{username}' promoted to SUPERADMIN")
            else:
                user_id = str(uuid.uuid4())
                user = User(
                    id=user_id,
                    username=username,
                    email=email,
                    password_hash=hashed_pw,
                    role_id=superadmin_role.id,
                    is_active=True,
                    is_verified=True,
                )
                session.add(user)
                await session.flush()

                # Provision admin starting virtual credit wallet
                initial_paise = 1000000  # 10,000 Credits
                wallet = Wallet(
                    user_id=user.id,
                    balance=initial_paise,
                    locked_balance=0,
                    currency="VIRTUAL",
                    is_frozen=False,
                )
                session.add(wallet)
                await session.flush()

                # Record immutable ledger entry for wallet grant
                tx = WalletTransaction(
                    wallet_id=wallet.id,
                    idempotency_key=f"init-superadmin-{user.id}",
                    type=TransactionType.BONUS.value,
                    amount=initial_paise,
                    balance_before=0,
                    balance_after=initial_paise,
                    status=TransactionStatus.COMPLETED.value,
                    description="Initial administrator credit grant",
                    reference="SYSTEM_PROVISION",
                )
                session.add(tx)
                logger.info(f"Created new SUPERADMIN user '{username}' with wallet")

            provisioning_uri = None
            if reset_authenticator:
                user.totp_secret = two_factor_service.generate_secret()
                user.totp_enabled = True
                provisioning_uri = two_factor_service.get_provisioning_uri(
                    user.totp_secret, user.username
                )

            # 3. Create AuditLog entry
            audit = AuditLog(
                actor_id=user.id,
                action="SUPERADMIN_PROVISIONED",
                target_type="USER",
                target_id=user.id,
                details={"username": username, "email": email},
            )
            session.add(audit)

            await session.commit()
            print(f"SUCCESS: Super Administrator '{username}' is configured and ready.")
            if provisioning_uri:
                print(
                    "Authenticator provisioning URI (import into your authenticator "
                    f"app; keep private): {provisioning_uri}"
                )

        except Exception as exc:
            await session.rollback()
            logger.exception("Failed to provision super administrator", error=str(exc))
            print(f"ERROR: {exc}")
            raise
        finally:
            await close_db()


def main() -> None:
    """CLI entrypoint."""
    setup_logging()
    parser = argparse.ArgumentParser(description="Create or promote a platform Super Administrator")
    parser.add_argument("--username", required=True, help="Username to create or promote")
    parser.add_argument("--email", required=True, help="Email address to create or promote")
    parser.add_argument(
        "--reset-authenticator",
        action="store_true",
        help="Rotate 2FA and print a one-time authenticator provisioning URI",
    )

    args = parser.parse_args()
    username = args.username.strip()
    email = args.email.strip().lower()

    if not username or not email:
        parser.error("username and email must not be blank")

    password = getpass("New super-admin password (12-128 characters): ")
    confirmation = getpass("Confirm new super-admin password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    if not 12 <= len(password) <= 128:
        parser.error("password must be between 12 and 128 characters")

    asyncio.run(
        create_or_promote_super_admin(
            username=username,
            email=email,
            password=password,
            reset_authenticator=args.reset_authenticator,
        )
    )


if __name__ == "__main__":
    main()
