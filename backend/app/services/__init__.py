"""Application services package."""

from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.daily_credit_service import DailyCreditService
from app.services.email_service import ConsoleEmailService, EmailServiceInterface, get_email_service
from app.services.fairness_service import FairnessService
from app.services.game_service import GameService
from app.services.notification_service import NotificationService
from app.services.report_service import ReportService
from app.services.responsible_play_service import ResponsiblePlayService
from app.services.support_service import SupportService
from app.services.two_factor_service import TwoFactorService
from app.services.user_service import UserService
from app.services.wallet_service import WalletService

__all__ = [
    "AdminService",
    "AuthService",
    "DailyCreditService",
    "EmailServiceInterface",
    "ConsoleEmailService",
    "get_email_service",
    "FairnessService",
    "GameService",
    "NotificationService",
    "ReportService",
    "ResponsiblePlayService",
    "SupportService",
    "TwoFactorService",
    "UserService",
    "WalletService",
]
