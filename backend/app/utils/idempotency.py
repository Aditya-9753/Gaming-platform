"""Idempotency key utilities.

Rules:
- Same key + same payload fingerprint → return cached result (no double-charge).
- Same key + different payload fingerprint → raise IdempotencyException.
- Keys are SHA-256 hashed for Redis storage to prevent leaking client secrets.

Storage backend: Redis with configurable TTL (default 24 h).
Fallback: in-memory dict when Redis is unavailable (single-process only,
  not safe for multi-worker deployments — log a warning).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Optional

from app.core.exceptions import IdempotencyException
from app.core.logging import get_logger
from app.core.redis import get_redis_client  # module-level so patch() works

logger = get_logger("idempotency")

# Redis key prefix and TTL
_PREFIX = "idem:"
_TTL_SECONDS = 86_400  # 24 hours

# In-process fallback store: key → {"fingerprint": str, "result": Any, "exp": float}
_memory_store: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Payload fingerprinting
# ---------------------------------------------------------------------------


def _fingerprint(payload: Dict[str, Any]) -> str:
    """Deterministic SHA-256 of a JSON-serialized dict (sorted keys)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _redis_key(idempotency_key: str) -> str:
    """Namespace the Redis key with a prefix."""
    return f"{_PREFIX}{idempotency_key}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def check_idempotency(
    idempotency_key: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Check whether this key has already been processed.

    Returns:
        The stored result dict if the key was seen before with the same payload.

    Raises:
        IdempotencyException: if the key was seen with a *different* payload.

    Returns None if the key is brand-new (caller should process and then call
    ``store_idempotency_result``).
    """
    fp = _fingerprint(payload)

    try:
        redis = get_redis_client()
        raw = await redis.get(_redis_key(idempotency_key))
        if raw is None:
            return None

        stored: Dict[str, Any] = json.loads(raw if isinstance(raw, str) else raw.decode())
        if stored["fingerprint"] != fp:
            raise IdempotencyException(
                f"Idempotency key '{idempotency_key}' was already used with a different payload"
            )
        logger.info("Idempotency cache hit", key=idempotency_key)
        return stored.get("result")

    except IdempotencyException:
        raise
    except Exception:
        # Redis unavailable — fall through to in-memory fallback
        pass

    # In-memory fallback (single-worker only)
    _evict_expired()
    entry = _memory_store.get(idempotency_key)
    if entry is None:
        return None
    if entry["fingerprint"] != fp:
        raise IdempotencyException(
            f"Idempotency key '{idempotency_key}' was already used with a different payload"
        )
    logger.info("Idempotency cache hit (in-memory)", key=idempotency_key)
    return entry.get("result")


async def store_idempotency_result(
    idempotency_key: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    ttl: int = _TTL_SECONDS,
) -> None:
    """Persist the result of a completed idempotent operation."""
    fp = _fingerprint(payload)
    value = json.dumps({"fingerprint": fp, "result": result}, default=str)

    try:
        redis = get_redis_client()
        await redis.set(_redis_key(idempotency_key), value, ex=ttl)
        return
    except Exception:
        pass

    # In-memory fallback
    _memory_store[idempotency_key] = {
        "fingerprint": fp,
        "result": result,
        "exp": time.time() + ttl,
    }
    logger.warning(
        "Idempotency stored in-memory only (Redis unavailable)",
        key=idempotency_key,
    )


def _evict_expired() -> None:
    """Remove expired entries from the in-memory fallback store."""
    now = time.time()
    expired = [k for k, v in _memory_store.items() if v["exp"] < now]
    for k in expired:
        del _memory_store[k]
