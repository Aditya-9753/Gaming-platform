"""AES-256-GCM sealing of ledger and audit rows.

Every wallet transaction and audit log row gets an ``integrity_seal``: the
row's important fields, serialised canonically and encrypted with
AES-256-GCM. The row's own id is the associated data, so a seal cannot be
copied onto another row. Anyone editing the table directly (SQL console, a
leaked DB password) cannot produce a valid seal without the key, so
``verify`` exposes the change.

The key lives only in the ``AUDIT_ENCRYPTION_KEY`` environment variable
(64 hex characters = 32 bytes). Without it rows are stored unsealed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SEAL_VERSION = "v1"


class CryptographicSecurityEngine:
    def __init__(self, master_key_hex: str) -> None:
        key = bytes.fromhex(master_key_hex.strip())
        if len(key) != 32:
            raise ValueError("AUDIT_ENCRYPTION_KEY must be 64 hex characters (32 bytes)")
        self.aesgcm = AESGCM(key)
        # Short public fingerprint so admins can tell which key is active (never the key itself)
        self.key_id = hashlib.sha256(b"key-id:" + key).hexdigest()[:12]

    def encrypt_payload(self, plaintext: str, associated_data: Optional[str] = None) -> str:
        """AES-256-GCM with a random 96-bit nonce; returns base64(nonce + ciphertext + tag)."""
        nonce = os.urandom(12)
        aad = associated_data.encode("utf-8") if associated_data else None
        ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt_payload(self, encrypted_b64: str, associated_data: Optional[str] = None) -> str:
        """Raises ``InvalidTag`` if the ciphertext, nonce or associated data was altered."""
        data = base64.b64decode(encrypted_b64.encode("ascii"))
        nonce, ciphertext = data[:12], data[12:]
        aad = associated_data.encode("utf-8") if associated_data else None
        return self.aesgcm.decrypt(nonce, ciphertext, aad).decode("utf-8")

    @staticmethod
    def generate_provably_fair_hash(server_seed: str, client_seed: str, nonce: int) -> str:
        msg = f"{client_seed}:{nonce}".encode("utf-8")
        return hmac.new(server_seed.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    @staticmethod
    def hash_server_seed(server_seed: str) -> str:
        return hashlib.sha256(server_seed.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------- row seals
    @staticmethod
    def _canonical(fields: Dict[str, Any]) -> str:
        return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)

    def seal(self, kind: str, row_id: str, fields: Dict[str, Any]) -> str:
        sealed = self.encrypt_payload(self._canonical(fields), f"{kind}:{row_id}")
        return f"{SEAL_VERSION}.{self.key_id}.{sealed}"

    def unseal(self, kind: str, row_id: str, seal: str) -> Dict[str, Any]:
        """Return the sealed snapshot; raises ValueError if the seal is invalid."""
        try:
            version, key_id, body = seal.split(".", 2)
        except ValueError as exc:
            raise ValueError("malformed seal") from exc
        if version != SEAL_VERSION:
            raise ValueError("unknown seal version")
        if key_id != self.key_id:
            raise ValueError("sealed with a different key")
        try:
            return json.loads(self.decrypt_payload(body, f"{kind}:{row_id}"))
        except (InvalidTag, ValueError) as exc:
            raise ValueError("seal does not authenticate") from exc

    def check(self, kind: str, row_id: str, seal: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        """Compare a row with its seal: status ok / tampered / unsealed, plus changed fields."""
        if not seal:
            return {"status": "unsealed"}
        try:
            snapshot = self.unseal(kind, row_id, seal)
        except ValueError as exc:
            return {"status": "tampered", "reason": str(exc)}
        current = json.loads(self._canonical(fields))
        changed = sorted(k for k in set(snapshot) | set(current) if snapshot.get(k) != current.get(k))
        if changed:
            return {
                "status": "tampered",
                "reason": "row differs from its seal",
                "changes": {k: {"sealed": snapshot.get(k), "now": current.get(k)} for k in changed},
            }
        return {"status": "ok"}


@lru_cache(maxsize=4)
def _engine_for(key_hex: str) -> CryptographicSecurityEngine:
    return CryptographicSecurityEngine(key_hex)


def get_integrity_engine() -> Optional[CryptographicSecurityEngine]:
    """The configured engine, or None when no key is set (rows are then stored unsealed)."""
    from app.core.config import get_settings

    key = (get_settings().AUDIT_ENCRYPTION_KEY or "").strip()
    return _engine_for(key) if key else None


__all__ = ["CryptographicSecurityEngine", "get_integrity_engine", "SEAL_VERSION"]
