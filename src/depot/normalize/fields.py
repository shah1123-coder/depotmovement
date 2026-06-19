"""Shared normalization for both directions. Applied after extraction, before
validation (Section 15)."""

from __future__ import annotations

import re
from datetime import date, datetime, time

from ..regions.base import RegionProfile

_WS = re.compile(r"\s+")

_DATE_FORMATS = []
for _sep in (".", "/", "-", " "):
    for _order in ("%d{0}%m{0}%Y", "%m{0}%d{0}%Y", "%Y{0}%m{0}%d",
                   "%d{0}%m{0}%y", "%m{0}%d{0}%y"):
        _DATE_FORMATS.append(_order.format(_sep))
_DATE_FORMATS += ["%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"]

_TIME_FORMATS = ["%I:%M %p", "%I:%M%p"]


def normalize_container(text: str) -> str:
    """Output uppercase, spaces removed (used as lookup key)."""
    if not text:
        return ""
    return text.upper().replace(" ", "")


def normalize_date(value, region: RegionProfile | None = None) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if value is None:
        return ""
    text = str(value)
    if region is not None:
        m = region.rx_date.search(text)
        if m:
            text = m.group(0)
    text = _WS.sub(" ", text.replace(",", " ")).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text  # all formats failed -> raw matched text


def normalize_time(value, region: RegionProfile | None = None) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S.000")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S.000")
    if value is None:
        return ""
    text = str(value).strip()
    matched = text
    if region is not None:
        m = region.rx_time.search(text)
        if m:
            matched = m.group(0)
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(matched.strip(), fmt).strftime("%H:%M:%S.000")
        except ValueError:
            continue
    if region is not None:
        m = region.rx_time.search(matched)
        if m:
            hh = int(m.group(1))
            mm = m.group(2)
            ss = (m.group(3) or ":00").lstrip(":")
            return f"{hh:02d}:{mm}:{ss}.000"
    return matched


def normalize_empty(value) -> str:
    if value is None:
        return ""
    return str(value).strip()
