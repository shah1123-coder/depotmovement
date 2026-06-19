"""Content-hash dedup so we never process the same file twice (15k/day)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..settings import get_settings
from .redis_client import get_redis

_PREFIX = "depot:seen:"


def content_hash(file_path: str | Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate(file_hash: str) -> bool:
    return bool(get_redis().exists(_PREFIX + file_hash))


def mark_seen(file_hash: str) -> None:
    ttl_seconds = get_settings().redis.dedup_ttl_days * 24 * 3600
    get_redis().set(_PREFIX + file_hash, "1", ex=ttl_seconds)
