"""Application-wide constants, enums, and role-based permissions.

NON-NEGOTIABLE:
- Balances are represented in paise (100 paise = 1 Credit / 1 rupee).
- Deposits are credited only from verified bank credits and withdrawals are
  completed only by a super admin (see app.services.payment_service).
"""

from enum import Enum
from typing import Dict, Set


# Currency / Credit Configuration
PAISE_PER_CREDIT: int = 100


class UserRole(str, Enum):
    """User authorization roles."""

    USER = "USER"
    SUPPORT = "SUPPORT"
    ADMIN = "ADMIN"
    SUPERADMIN = "SUPERADMIN"
    AUDITOR = "AUDITOR"


class PermissionCode(str, Enum):
    """Fine-grained permission codes for RBAC."""

    # Player / User Permissions
    WALLET_READ = "wallet:read"
    WALLET_CLAIM = "wallet:claim"
    GAME_PLAY = "game:play"
    HISTORY_READ = "history:read"

    # Support Operations
    USER_READ = "user:read"
    TICKET_MANAGE = "ticket:manage"
    SESSION_READ = "session:read"

    # Administrative Operations
    USER_MANAGE = "user:manage"
    WALLET_ADJUST = "wallet:adjust"
    GAME_MANAGE = "game:manage"
    SYSTEM_CONFIG = "system:config"
    AUDIT_READ = "audit:read"
    LEDGER_READ = "ledger:read"
    ROLE_MANAGE = "role:manage"
    NOTIFICATION_MANAGE = "notification:manage"
    REPORT_EXPORT = "report:export"

    # Payments (deposits / withdrawals)
    PAYMENT_DEPOSIT = "payment:deposit"
    PAYMENT_WITHDRAW = "payment:withdraw"
    PAYMENT_READ = "payment:read"
    PAYMENT_MANAGE = "payment:manage"


# Mapping from UserRole to granted PermissionCodes
ROLE_PERMISSIONS: Dict[UserRole, Set[PermissionCode]] = {
    UserRole.USER: {
        PermissionCode.WALLET_READ,
        PermissionCode.WALLET_CLAIM,
        PermissionCode.GAME_PLAY,
        PermissionCode.HISTORY_READ,
        PermissionCode.PAYMENT_DEPOSIT,
        PermissionCode.PAYMENT_WITHDRAW,
    },
    UserRole.SUPPORT: {
        PermissionCode.WALLET_READ,
        PermissionCode.HISTORY_READ,
        PermissionCode.PAYMENT_READ,
        PermissionCode.USER_READ,
        PermissionCode.TICKET_MANAGE,
        PermissionCode.SESSION_READ,
    },
    UserRole.AUDITOR: {
        PermissionCode.WALLET_READ,
        PermissionCode.HISTORY_READ,
        PermissionCode.USER_READ,
        PermissionCode.AUDIT_READ,
        PermissionCode.LEDGER_READ,
        PermissionCode.PAYMENT_READ,
    },
    UserRole.ADMIN: {
        PermissionCode.WALLET_READ,
        PermissionCode.WALLET_CLAIM,
        PermissionCode.GAME_PLAY,
        PermissionCode.HISTORY_READ,
        PermissionCode.USER_READ,
        PermissionCode.TICKET_MANAGE,
        PermissionCode.SESSION_READ,
        PermissionCode.USER_MANAGE,
        PermissionCode.WALLET_ADJUST,
        PermissionCode.GAME_MANAGE,
        PermissionCode.SYSTEM_CONFIG,
        PermissionCode.AUDIT_READ,
        PermissionCode.LEDGER_READ,
        PermissionCode.NOTIFICATION_MANAGE,
        PermissionCode.REPORT_EXPORT,
        PermissionCode.PAYMENT_READ,
        PermissionCode.PAYMENT_MANAGE,
    },
    UserRole.SUPERADMIN: set(PermissionCode),  # All permissions
}


class TransactionType(str, Enum):
    """Wallet ledger movement types."""

    BET = "BET"
    WIN = "WIN"
    REFUND = "REFUND"
    FAUCET = "FAUCET"
    BONUS = "BONUS"
    ADJUSTMENT = "ADJUSTMENT"
    DEPOSIT = "DEPOSIT"
    DEPOSIT_REVERSAL = "DEPOSIT_REVERSAL"
    WITHDRAWAL_HOLD = "WITHDRAWAL_HOLD"
    WITHDRAWAL_SETTLE = "WITHDRAWAL_SETTLE"
    WITHDRAWAL_RELEASE = "WITHDRAWAL_RELEASE"


class TransactionStatus(str, Enum):
    """Ledger transaction processing statuses."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class GameType(str, Enum):
    """Supported game types in the platform."""

    AVIATOR = "AVIATOR"
    MINES = "MINES"
    COLOR = "COLOR"
    CRICKET = "CRICKET"


class RoundStatus(str, Enum):
    """Game round lifecycle statuses."""

    SCHEDULED = "SCHEDULED"
    BETTING = "BETTING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class GameRoundLifecycle(str, Enum):
    """Lifecycle states used by real-time Aviator and Color Prediction rounds."""

    WAITING = "WAITING"
    BETTING_OPEN = "BETTING_OPEN"
    CREATED = "CREATED"
    OPEN = "OPEN"
    LOCKED = "LOCKED"
    CRASHED = "CRASHED"
    SETTLING = "SETTLING"
    RESULT = "RESULT"
    SETTLED = "SETTLED"
    HISTORY = "HISTORY"
