"""Rate limiting and account lockout service with Redis and in-memory fallback."""

import time
from typing import Dict, Optional, Tuple
from app.core.exceptions import RateLimitException
from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger("rate_limit")

# In-memory storage fallback if Redis is unavailable
_memory_store: Dict[str, Tuple[int, float]] = {}  # key -> (count, expiry_timestamp)
_lockout_store: Dict[str, float] = {}  # key -> lockout_until_timestamp

# Defaults
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes


def _clean_memory_store() -> None:
    now = time.time()
    expired_keys = [k for k, v in _memory_store.items() if v[1] < now]
    for k in expired_keys:
        del _memory_store[k]

    expired_lockouts = [k for k, v in _lockout_store.items() if v < now]
    for k in expired_lockouts:
        del _lockout_store[k]


async def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
) -> bool:
    """Check if an action is within allowed rate limits.

    Returns True if allowed, False if exceeded.
    """
    redis = get_redis_client()
    now = time.time()

    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window_seconds)
        return current <= max_requests
    except Exception as exc:
        # Fallback to in-memory store
        _clean_memory_store()
        if key not in _memory_store or _memory_store[key][1] < now:
            _memory_store[key] = (1, now + window_seconds)
            return True
        count, expiry = _memory_store[key]
        if count >= max_requests:
            return False
        _memory_store[key] = (count + 1, expiry)
        return True


async def is_locked_out(identifier: str, ip: str) -> Tuple[bool, int]:
    """Check if an account or IP is temporarily locked out due to repeated failures.

    Returns (is_locked, remaining_lockout_seconds).
    """
    redis = get_redis_client()
    lock_key = f"lockout:{identifier}:{ip}"
    now = time.time()

    try:
        ttl = await redis.ttl(lock_key)
        if ttl > 0:
            return True, ttl
        return False, 0
    except Exception:
        # In-memory fallback
        _clean_memory_store()
        lockout_until = _lockout_store.get(lock_key)
        if lockout_until and lockout_until > now:
            return True, int(lockout_until - now)
        return False, 0


async def record_failed_login(identifier: str, ip: str) -> int:
    """Increment failed login counter and enforce lockout if threshold reached.

    Returns current failed attempt count.
    """
    redis = get_redis_client()
    attempts_key = f"failed_logins:{identifier}:{ip}"
    lock_key = f"lockout:{identifier}:{ip}"
    now = time.time()

    try:
        attempts = await redis.incr(attempts_key)
        if attempts == 1:
            await redis.expire(attempts_key, LOCKOUT_DURATION_SECONDS)

        if attempts >= MAX_FAILED_LOGINS:
            await redis.set(lock_key, "1", ex=LOCKOUT_DURATION_SECONDS)
            logger.warning("Account/IP locked out due to failed logins", identifier=identifier, ip=ip)
        return attempts
    except Exception:
        # In-memory fallback
        _clean_memory_store()
        count, expiry = _memory_store.get(attempts_key, (0, now + LOCKOUT_DURATION_SECONDS))
        new_count = count + 1
        _memory_store[attempts_key] = (new_count, now + LOCKOUT_DURATION_SECONDS)

        if new_count >= MAX_FAILED_LOGINS:
            _lockout_store[lock_key] = now + LOCKOUT_DURATION_SECONDS
            logger.warning("Account/IP locked out (in-memory)", identifier=identifier, ip=ip)
        return new_count


async def reset_failed_attempts(identifier: str, ip: str) -> None:
    """Clear failed attempts and lockout on successful login."""
    redis = get_redis_client()
    attempts_key = f"failed_logins:{identifier}:{ip}"
    lock_key = f"lockout:{identifier}:{ip}"

    try:
        await redis.delete(attempts_key, lock_key)
    except Exception:
        _memory_store.pop(attempts_key, None)
        _lockout_store.pop(lock_key, None)
