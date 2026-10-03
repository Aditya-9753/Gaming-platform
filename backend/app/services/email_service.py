"""Transactional email: Brevo / Resend HTTP APIs, SMTP, or console (dev).

Render's free instances block outbound SMTP ports, so production should use an
HTTP provider: set BREVO_API_KEY (free 300 mails/day) or RESEND_API_KEY, plus
EMAIL_FROM (a sender address verified with that provider).
"""

from __future__ import annotations

import html
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("email_service")


class EmailDeliveryError(RuntimeError):
    """The provider refused or could not deliver the message."""


def _otp_bodies(code: str, purpose: str, brand: str) -> tuple[str, str, str]:
    action = {
        "setup": "finish setting up two-step verification",
        "payment": "approve a payment action",
    }.get(purpose, "sign in to the admin panel")
    subject = f"{brand} verification code: {code}"
    text = (
        f"Your {brand} verification code is {code}\n\n"
        f"Use it to {action}. It expires in 10 minutes and can be used once.\n"
        "If you did not try to sign in, change your password immediately."
    )
    body = f"""
<div style="font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:24px;border:1px solid #eee;border-radius:12px">
  <h2 style="margin:0 0 8px;color:#111">{html.escape(brand)}</h2>
  <p style="color:#444">Use this code to {html.escape(action)}:</p>
  <p style="font-size:34px;letter-spacing:8px;font-weight:bold;color:#e11d48;margin:16px 0">{code}</p>
  <p style="color:#666;font-size:13px">It expires in 10 minutes and can be used once.<br>
  If you did not try to sign in, change your password immediately.</p>
</div>"""
    return subject, text, body


class EmailServiceInterface(ABC):
    """Abstract interface for transactional email notifications."""

    @abstractmethod
    async def send(self, to_email: str, subject: str, text: str, html_body: Optional[str] = None) -> None:
        """Deliver one message or raise EmailDeliveryError."""

    async def send_otp_email(self, to_email: str, code: str, purpose: str = "login") -> None:
        subject, text, body = _otp_bodies(code, purpose, get_settings().EMAIL_FROM_NAME)
        await self.send(to_email, subject, text, body)

    async def send_password_reset_email(self, to_email: str, reset_token: str) -> None:
        await self.send(to_email, "Reset your password", f"Your password reset token: {reset_token}")

    async def send_verification_email(self, to_email: str, verify_token: str) -> None:
        await self.send(to_email, "Verify your email", f"Your verification token: {verify_token}")


class ConsoleEmailService(EmailServiceInterface):
    """Development / test: write the message to the log instead of sending it."""

    async def send(self, to_email: str, subject: str, text: str, html_body: Optional[str] = None) -> None:
        logger.info("SIMULATED EMAIL", recipient=to_email, subject=subject, body=text)


class BrevoEmailService(EmailServiceInterface):
    def __init__(self, api_key: str, sender: str, sender_name: str) -> None:
        self.api_key, self.sender, self.sender_name = api_key, sender, sender_name

    async def send(self, to_email: str, subject: str, text: str, html_body: Optional[str] = None) -> None:
        payload = {
            "sender": {"email": self.sender, "name": self.sender_name},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": text,
            "htmlContent": html_body or f"<pre>{html.escape(text)}</pre>",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://api.brevo.com/v3/smtp/email", json=payload, headers={"api-key": self.api_key})
        if response.status_code >= 300:
            raise EmailDeliveryError(f"Brevo rejected the email ({response.status_code}): {response.text[:200]}")


class ResendEmailService(EmailServiceInterface):
    def __init__(self, api_key: str, sender: str, sender_name: str) -> None:
        self.api_key, self.sender, self.sender_name = api_key, sender, sender_name

    async def send(self, to_email: str, subject: str, text: str, html_body: Optional[str] = None) -> None:
        payload = {"from": f"{self.sender_name} <{self.sender}>", "to": [to_email], "subject": subject, "text": text}
        if html_body:
            payload["html"] = html_body
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers={"Authorization": f"Bearer {self.api_key}"})
        if response.status_code >= 300:
            raise EmailDeliveryError(f"Resend rejected the email ({response.status_code}): {response.text[:200]}")


class SmtpEmailService(EmailServiceInterface):
    """Plain SMTP (works locally / on paid hosts; Render free blocks SMTP ports)."""

    def __init__(self, host: str, port: int, user: Optional[str], password: Optional[str], sender: str, sender_name: str) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.sender_name = sender, sender_name

    async def send(self, to_email: str, subject: str, text: str, html_body: Optional[str] = None) -> None:
        import aiosmtplib

        message = EmailMessage()
        message["From"] = f"{self.sender_name} <{self.sender}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        try:
            await aiosmtplib.send(
                message, hostname=self.host, port=self.port, username=self.user, password=self.password,
                start_tls=self.port == 587, use_tls=self.port == 465, timeout=15,
            )
        except Exception as exc:  # pragma: no cover - network
            raise EmailDeliveryError(f"SMTP delivery failed: {exc}") from exc


def build_email_service() -> EmailServiceInterface:
    s = get_settings()
    provider = (s.EMAIL_PROVIDER or "").lower() or (
        "brevo" if s.BREVO_API_KEY else "resend" if s.RESEND_API_KEY else "smtp" if s.SMTP_HOST else "console"
    )
    sender = s.EMAIL_FROM or ""
    if provider != "console" and not sender:
        logger.warning("EMAIL_FROM is not set; falling back to console email")
        return ConsoleEmailService()
    if provider == "brevo" and s.BREVO_API_KEY:
        return BrevoEmailService(s.BREVO_API_KEY, sender, s.EMAIL_FROM_NAME)
    if provider == "resend" and s.RESEND_API_KEY:
        return ResendEmailService(s.RESEND_API_KEY, sender, s.EMAIL_FROM_NAME)
    if provider == "smtp" and s.SMTP_HOST:
        return SmtpEmailService(s.SMTP_HOST, s.SMTP_PORT, s.SMTP_USER, s.SMTP_PASSWORD, sender, s.EMAIL_FROM_NAME)
    return ConsoleEmailService()


_email_service_instance: Optional[EmailServiceInterface] = None


def get_email_service() -> EmailServiceInterface:
    """Return the configured email service instance."""
    global _email_service_instance
    if _email_service_instance is None:
        _email_service_instance = build_email_service()
    return _email_service_instance


def email_delivery_configured() -> bool:
    return not isinstance(get_email_service(), ConsoleEmailService)
