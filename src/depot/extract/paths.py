"""Shared filesystem-path sanitization (Section 12). Used everywhere a path
component is built from sheet/title/workbook text."""

from __future__ import annotations

import re
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, max_len: int = 80) -> str:
    s = _ILLEGAL.sub(" ", name or "")
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    if not s:
        s = "untitled"
    return s[:max_len].strip()


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    """Return a non-colliding path, suffixing _1.._999 if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{ext}"
    if not candidate.exists():
        return candidate
    for i in range(1, 1000):
        candidate = directory / f"{stem}_{i}{ext}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}_{1000}{ext}"
