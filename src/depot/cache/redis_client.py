"""One shared Redis connection pool built from REDIS_URL."""

from __future__ import annotations

from functools import lru_cache

import redis

from ..settings import get_settings


@lru_cache(maxsize=1)
def get_redis() -> "redis.Redis":
    url = get_settings().redis_url()
    pool = redis.ConnectionPool.from_url(url, decode_responses=True)
    return redis.Redis(connection_pool=pool)
