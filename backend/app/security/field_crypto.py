"""Field-level encryption for payout details (bank account numbers, UPI ids).

Values are AES-256-GCM encrypted with the row id as associated data, so a
ciphertext copied onto another row does not decrypt. ``fingerprint`` is a
keyed hash used to spot the same payout account across different players
without decrypting anything.

Key: ``PII_ENCRYPTION_KEY`` (64 hex), else ``AUDIT_ENCRYPTION_KEY``. Outside
production a fixed development key is used so local setups work; production
refuses to store payout details without a configured key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableException
from app.security.crypto_engine import CryptographicSecurityEngine, _engine_for

_PREFIX = "pii1"
_DEV_KEY = hashlib.sha256(b"rudra247-development-only-pii-key").hexdigest()


def _key_hex() -> str:
    settings = get_settings()
    key = (settings.PII_ENCRYPTION_KEY or settings.AUDIT_ENCRYPTION_KEY or "").strip()
    if key:
        return key
    if settings.is_production:
        raise ServiceUnavailableException("Payout encryption key is not configured (set PII_ENCRYPTION_KEY)")
    return _DEV_KEY


def _engine() -> CryptographicSecurityEngine:
    return _engine_for(_key_hex())


def encrypt_json(value: Dict[str, Any], row_id: str) -> str:
    engine = _engine()
    body = engine.encrypt_payload(json.dumps(value, sort_keys=True), f"pii:{row_id}")
    return f"{_PREFIX}.{engine.key_id}.{body}"


def decrypt_json(token: str, row_id: str) -> Dict[str, Any]:
    engine = _engine()
    try:
        prefix, key_id, body = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("malformed encrypted field") from exc
    if prefix != _PREFIX or key_id != engine.key_id:
        raise ValueError("encrypted with a different key")
    return json.loads(engine.decrypt_payload(body, f"pii:{row_id}"))


def fingerprint(value: str) -> str:
    return hmac.new(bytes.fromhex(_key_hex()), value.encode("utf-8"), hashlib.sha256).hexdigest()
