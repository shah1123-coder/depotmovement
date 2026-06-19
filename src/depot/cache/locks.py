"""Redis distributed locks: per-file (no double processing) and per-booking
(so parallel jobs don't both consume the same booking quota — Section 16)."""

from __future__ import annotations

import contextlib
import uuid

from .redis_client import get_redis

_LOCK_PREFIX = "depot:lock:"


def acquire(key: str, ttl: int = 300) -> str | None:
    """SET key token NX EX ttl. Returns the token if acquired, else None."""
    token = uuid.uuid4().hex
    ok = get_redis().set(_LOCK_PREFIX + key, token, nx=True, ex=ttl)
    return token if ok else None


# Release only if we still own the lock (token matches) — avoids releasing a
# lock that already expired and was re-acquired by another worker.
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def release(key: str, token: str) -> bool:
    result = get_redis().eval(_RELEASE_LUA, 1, _LOCK_PREFIX + key, token)
    return bool(result)


@contextlib.contextmanager
def lock(key: str, ttl: int = 300):
    """Context manager; yields True if the lock was acquired, False otherwise."""
    token = acquire(key, ttl)
    try:
        yield token is not None
    finally:
        if token is not None:
            release(key, token)
