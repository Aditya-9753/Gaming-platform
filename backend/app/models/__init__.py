"""SQLAlchemy ORM models export package."""

from app.core.database import Base
from app.models.audit_log import AuditLog
from app.models.game import Game, GameEntry, GameResult, GameRound, GameSetting
from app.models.game_archive import GameArchive
from app.models.cricket import CricketMatchRecord, CricketPrediction
from app.models.leaderboard import Leaderboard
from app.models.notification import Notification
from app.models.payment import (
    BankCredit,
    Beneficiary,
    Deposit,
    PaymentAccount,
    PaymentStatusHistory,
    PaymentWebhookEvent,
    Withdrawal,
)
from app.models.refresh_token import RefreshToken
from app.models.role import Permission, Role, RolePermission
from app.models.self_exclusion import SelfExclusion
from app.models.support import SupportMessage, SupportTicket
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.models import affiliate  # noqa: F401  (registers the aff_* tables on Base.metadata)

# Seal ledger and audit rows on write (needs the models above)
import app.security.integrity  # noqa: E402,F401

__all__ = [
    "Base",
    "Role",
    "Permission",
    "RolePermission",
    "User",
    "RefreshToken",
    "Wallet",
    "WalletTransaction",
    "Game",
    "GameSetting",
    "GameRound",
    "GameResult",
    "GameEntry",
    "GameArchive",
    "CricketMatchRecord",
    "CricketPrediction",
    "Notification",
    "SupportTicket",
    "SupportMessage",
    "Leaderboard",
    "SelfExclusion",
    "AuditLog",
    "SystemSetting",
    "PaymentAccount",
    "Deposit",
    "BankCredit",
    "PaymentWebhookEvent",
    "Beneficiary",
    "Withdrawal",
    "PaymentStatusHistory",
]
