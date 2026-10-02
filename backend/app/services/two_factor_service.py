"""Two-Factor Authentication (TOTP) service using pyotp."""

import pyotp


class TwoFactorService:
    """Provides RFC 6238 TOTP secrets, provisioning URIs, and code verification."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a random 32-character base32 secret key."""
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(
        secret: str,
        username: str,
        issuer_name: str = "VirtualGamingPlatform",
    ) -> str:
        """Create a standard otpauth:// URI for QR code generation."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name=issuer_name)

    @staticmethod
    def verify_code(secret: str, code: str, valid_window: int = 1) -> bool:
        """Validate a 6-digit TOTP code against the secret with clock skew tolerance."""
        if not secret or not code:
            return False
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(code.strip(), valid_window=valid_window))


two_factor_service = TwoFactorService()
