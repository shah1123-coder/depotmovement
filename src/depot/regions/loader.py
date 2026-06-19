"""Discover, validate and cache every region profile at startup (fail fast)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..settings import get_settings
from .base import RegionProfile


def _load_dir(regions_dir: Path) -> dict[str, RegionProfile]:
    profiles: dict[str, RegionProfile] = {}
    files = sorted(regions_dir.glob("*.yaml"))
    if not files:
        raise RuntimeError(f"No region files found in {regions_dir}")
    for path in files:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        # Fail fast: a malformed region file raises here, before processing.
        profile = RegionProfile.build(data)
        profiles[profile.name] = profile
    return profiles


@lru_cache(maxsize=1)
def get_region_profiles() -> dict[str, RegionProfile]:
    return _load_dir(get_settings().regions_dir)


def get_region(name: str) -> RegionProfile:
    profiles = get_region_profiles()
    if name not in profiles:
        raise KeyError(f"Unknown region '{name}'. Known: {list(profiles)}")
    return profiles[name]
