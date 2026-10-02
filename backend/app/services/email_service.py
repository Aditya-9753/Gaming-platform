"""Email notification service interface and console logger implementation."""

from abc import ABC, abstractmethod
from app.core.logging import get_logger

logger = get_logger("email_service")


class EmailServiceInterface(ABC):
    """Abstract interface for transactional email notifications."""

    @abstractmethod
    async def send_password_reset_email(self, to_email: str, reset_token: str) -> None:
        """Send password reset instructions containing secure reset token."""
        pass

    @abstractmethod
    async def send_verification_email(self, to_email: str, verify_token: str) -> None:
        """Send account email verification link."""
        pass


class ConsoleEmailService(EmailServiceInterface):
    """Console/log implementation for development and testing environments."""

    async def send_password_reset_email(self, to_email: str, reset_token: str) -> None:
        logger.info(
            "SIMULATED EMAIL: Password Reset",
            recipient=to_email,
            reset_token=reset_token,
            reset_link=f"http://localhost:3000/reset-password?token={reset_token}",
        )

    async def send_verification_email(self, to_email: str, verify_token: str) -> None:
        logger.info(
            "SIMULATED EMAIL: Account Verification",
            recipient=to_email,
            verify_token=verify_token,
            verification_link=f"http://localhost:3000/verify-email?token={verify_token}",
        )


_email_service_instance: EmailServiceInterface = ConsoleEmailService()


def get_email_service() -> EmailServiceInterface:
    """Return the configured email service instance."""
    return _email_service_instance
