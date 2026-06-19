"""The ONLY place where language -> region is decided.

If a sheet title contains any CJK character -> China; otherwise -> India.
"""

from __future__ import annotations

from .base import RegionProfile
from .loader import get_region

_CJK_RANGES = (
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # Extension A
    (0xF900, 0xFAFF),   # Compatibility Ideographs
    (0x3000, 0x303F),   # CJK symbols and punctuation
)


def _has_cjk(text: str) -> bool:
    for ch in text or "":
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _CJK_RANGES):
            return True
    return False


def detect_region(sheet_title: str) -> RegionProfile:
    return get_region("china") if _has_cjk(sheet_title) else get_region("india")
