"""Database seeding script.

Idempotently provisions:
- Roles (USER, SUPPORT, ADMIN, SUPERADMIN, AUDITOR)
- Fine-grained permissions and role_permissions associations
- Core 4 Games (Aviator, Mines, Color, Cricket) with default settings
- System configuration settings (signup bonus, daily faucet credits, etc.)
"""

import asyncio
from typing import Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliate.rbac import AFF_PERMISSIONS_META
from app.core.constants import ROLE_PERMISSIONS, PermissionCode, UserRole
from app.core.database import close_db, get_session_factory, init_db
from app.core.logging import get_logger, setup_logging
from app.models.game import Game, GameSetting
from app.models.role import Permission, Role, RolePermission
from app.models.system_setting import SystemSetting

logger = get_logger("seed_db")

# Permissions metadata definition
PERMISSIONS_DATA: List[Dict[str, str]] = [
    {"code": PermissionCode.WALLET_READ.value, "name": "View Wallet", "description": "View virtual credit wallet and balance"},
    {"code": PermissionCode.WALLET_CLAIM.value, "name": "Claim Faucet", "description": "Claim promotional faucet virtual credits"},
    {"code": PermissionCode.GAME_PLAY.value, "name": "Play Games", "description": "Participate in game rounds with virtual credits"},
    {"code": PermissionCode.HISTORY_READ.value, "name": "View History", "description": "View game round history and user bets"},
    {"code": PermissionCode.USER_READ.value, "name": "View Users", "description": "View user profiles and account statuses"},
    {"code": PermissionCode.TICKET_MANAGE.value, "name": "Manage Tickets", "description": "Respond to and resolve customer support tickets"},
    {"code": PermissionCode.SESSION_READ.value, "name": "View Sessions", "description": "View active user sessions and connections"},
    {"code": PermissionCode.USER_MANAGE.value, "name": "Manage Users", "description": "Suspend, lock, or modify user accounts"},
    {"code": PermissionCode.WALLET_ADJUST.value, "name": "Adjust Wallet", "description": "Administrator virtual credit balance adjustments"},
    {"code": PermissionCode.GAME_MANAGE.value, "name": "Manage Games", "description": "Modify game settings, house edge, and bet limits"},
    {"code": PermissionCode.SYSTEM_CONFIG.value, "name": "System Config", "description": "Modify platform-wide system settings"},
    {"code": PermissionCode.AUDIT_READ.value, "name": "View Audit Logs", "description": "Inspect administrative security audit trail"},
    {"code": PermissionCode.LEDGER_READ.value, "name": "View Ledger", "description": "View full immutable virtual credit movement ledger"},
    {"code": PermissionCode.ROLE_MANAGE.value, "name": "Manage Roles", "description": "Assign roles and manage administrator accounts"},
    {"code": PermissionCode.NOTIFICATION_MANAGE.value, "name": "Manage Notifications", "description": "Send and manage platform notifications"},
    {"code": PermissionCode.REPORT_EXPORT.value, "name": "Export Reports", "description": "Generate and export platform reports"},
    {"code": PermissionCode.PAYMENT_DEPOSIT.value, "name": "Deposit", "description": "Create deposit requests and submit payment UTRs"},
    {"code": PermissionCode.PAYMENT_WITHDRAW.value, "name": "Withdraw", "description": "Add payout accounts and request withdrawals"},
    {"code": PermissionCode.PAYMENT_READ.value, "name": "View Payments", "description": "View deposits, withdrawals and bank credits"},
    {"code": PermissionCode.PAYMENT_MANAGE.value, "name": "Manage Payments", "description": "Own QR collection accounts; verify or reject deposits paid into them"},
] + [
    {"code": code, "name": name, "description": desc}
    for code, (name, desc) in AFF_PERMISSIONS_META.items()
]

# The 4 default games and their settings (amounts in integer paise: 100 paise = 1 Credit)
GAMES_DATA = [
    {
        "id": "aviator",
        "name": "Aviator",
        "type": "CRASH",
        "description": "Multiplayer crash game with real-time curve and provably fair multiplier.",
        "min_bet": 100,  # 1 Credit
        "max_bet": 500000,  # 5,000 Credits
        "house_edge_percent": 300,  # 3.00%
        "config": {
            "tick_rate_ms": 50,
            "betting_duration_sec": 6,
            "growth_rate": 0.08,
            "growth_power": 1.3,
            "min_multiplier": 1.00,
        },
    },
    {
        "id": "mines",
        "name": "Mines",
        "type": "MINES",
        "description": "5x5 grid game with configurable mines and increasing multipliers per gem revealed.",
        "min_bet": 100,  # 1 Credit
        "max_bet": 200000,  # 2,000 Credits
        "house_edge_percent": 300,  # 3.00%
        "config": {"grid_size": 25, "min_mines": 1, "max_mines": 24},
    },
    {
        "id": "color",
        "name": "Color Prediction",
        "type": "COLOR",
        "description": "WinGo: predict Green, Red, Violet, a number 0-9 or Big/Small. 30s, 1, 3 and 5 minute periods.",
        "min_bet": 100,  # 1 Credit
        "max_bet": 500000,  # 5,000 Credits
        "house_edge_percent": 300,  # 3.00%
        "config": {
            "timer_length_seconds": 30,
            "lock_before_end_seconds": 5,
            "payout_multipliers": {"RED": 2, "GREEN": 2, "VIOLET": 4.5},
        },
    },
    {
        "id": "cricket",
        "name": "Cricket Live",
        "type": "CRICKET",
        "description": "Predict the match winner, then follow the game live ball-by-ball.",
        "min_bet": 100,  # 1 Credit
        "max_bet": 300000,  # 3,000 Credits
        "house_edge_percent": 300,  # 3.00%
        "config": {
            "over_balls": 6,
            "multipliers": {"0": 1.95, "1": 2.10, "2": 3.50, "4": 6.00, "6": 10.00, "W": 8.00},
        },
    },
]

GAMES_DATA.append(
    {
        "id": "teen_patti",
        "name": "Teen Patti",
        "type": "CARD",
        "description": "Live Teen Patti: bet on Player A or Player B. New hand every ~30 seconds.",
        "min_bet": 100,
        "max_bet": 500_000,
        "house_edge_percent": 200,
        "config": {"payout": 1.96},
    }
)

# WinGo modes (colour / number / big-small) — the "Color Prediction" lobby card
for _game_id, _label, _desc in [
    ("wingo_30s", "WinGo 30sec", "New period every 30 seconds."),
    ("wingo_1m", "WinGo 1 Min", "New period every minute."),
    ("wingo_3m", "WinGo 3 Min", "New period every 3 minutes."),
    ("wingo_5m", "WinGo 5 Min", "New period every 5 minutes."),
]:
    GAMES_DATA.append(
        {
            "id": _game_id,
            "name": _label,
            "type": "COLOR",
            "description": f"{_desc} Predict colour, number or Big/Small.",
            "min_bet": 100,  # 1 Credit
            "max_bet": 1_000_000,  # 10,000 Credits
            "house_edge_percent": 500,
            "config": {},
        }
    )

# System configuration settings
SYSTEM_SETTINGS_DATA = [
    {
        "key": "signup_bonus_paise",
        "value": "10000",
        "description": "Initial virtual credit faucet awarded to new users upon registration (10,000 paise = 100 credits)",
    },
    {
        "key": "daily_faucet_paise",
        "value": "5000",
        "description": "Daily virtual credit refill amount (5,000 paise = 50 credits)",
    },
    {
        "key": "faucet_cooldown_hours",
        "value": "24",
        "description": "Cooldown period between consecutive daily faucet claims in hours",
    },
    {
        "key": "platform_mode",
        "value": "VIRTUAL_ONLY",
        "description": "Enforce strict virtual-credit platform mode (no real money)",
    },
    {
        "key": "responsible_gaming_max_daily_bet",
        "value": "5000000",
        "description": "Default maximum daily aggregate bet amount in paise (50,000 credits)",
    },
]


async def seed_roles_and_permissions(session: AsyncSession) -> None:
    """Seed roles, permissions, and link them via role_permissions."""
    logger.info("Seeding permissions...")
    perm_map: Dict[str, Permission] = {}

    for pdata in PERMISSIONS_DATA:
        result = await session.execute(
            select(Permission).where(Permission.code == pdata["code"])
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = Permission(
                code=pdata["code"],
                name=pdata["name"],
                description=pdata["description"],
            )
            session.add(perm)
            await session.flush()
        perm_map[perm.code] = perm

    logger.info("Seeding roles and mapping permissions...")
    for role_enum in UserRole:
        result = await session.execute(
            select(Role).where(Role.name == role_enum.value)
        )
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(
                name=role_enum.value,
                description=f"System role for {role_enum.value.lower()}",
            )
            session.add(role)
            await session.flush()

        # Map role permissions
        granted_codes = {code.value for code in ROLE_PERMISSIONS.get(role_enum, set())}
        for code in granted_codes:
            if code in perm_map:
                perm_id = perm_map[code].id
                rp_check = await session.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm_id,
                    )
                )
                if rp_check.scalar_one_or_none() is None:
                    session.add(RolePermission(role_id=role.id, permission_id=perm_id))

    await session.commit()
    logger.info("Roles and permissions successfully seeded")


async def seed_games(session: AsyncSession) -> None:
    """Seed the 4 default games and their default settings."""
    logger.info("Seeding games and settings...")
    for gdata in GAMES_DATA:
        result = await session.execute(select(Game).where(Game.id == gdata["id"]))
        game = result.scalar_one_or_none()

        if game is None:
            game = Game(
                id=gdata["id"],
                name=gdata["name"],
                type=gdata["type"],
                description=gdata["description"],
                is_active=True,
            )
            session.add(game)
            await session.flush()

        # Ensure GameSetting exists
        res_setting = await session.execute(
            select(GameSetting).where(GameSetting.game_id == game.id)
        )
        setting = res_setting.scalar_one_or_none()
        if setting is None:
            setting = GameSetting(
                game_id=game.id,
                min_bet=gdata["min_bet"],
                max_bet=gdata["max_bet"],
                house_edge_percent=gdata["house_edge_percent"],
                config=gdata["config"],
            )
            session.add(setting)

    await session.commit()
    logger.info("Games and settings successfully seeded")


async def seed_system_settings(session: AsyncSession) -> None:
    """Seed default system configuration key-values."""
    logger.info("Seeding system settings...")
    for sdata in SYSTEM_SETTINGS_DATA:
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == sdata["key"])
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            setting = SystemSetting(
                key=sdata["key"],
                value=sdata["value"],
                description=sdata["description"],
            )
            session.add(setting)

    await session.commit()
    logger.info("System settings successfully seeded")


async def main() -> None:
    """Run all database seeding procedures."""
    setup_logging()
    logger.info("Starting database seeding...")

    await init_db()
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            await seed_roles_and_permissions(session)
            await seed_games(session)
            await seed_system_settings(session)

            from app.core.config import get_settings
            if not get_settings().is_production:
                from app.core.bootstrap import seed_default_accounts
                await seed_default_accounts(session)
            logger.info("All database seeds completed successfully!")
        except Exception as exc:
            await session.rollback()
            logger.exception("Seeding encountered an error", error=str(exc))
            raise
        finally:
            await close_db()


if __name__ == "__main__":
    asyncio.run(main())
