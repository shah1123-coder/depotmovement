"""Attach a title to each header by scanning up to N rows above it."""

from __future__ import annotations

from ..models import HeaderRun, LogicalCell
from ..settings import get_settings


def attach_titles(headers: list[HeaderRun],
                  logical_rows: list[list[LogicalCell]]) -> list[HeaderRun]:
    scan = get_settings().detection.title_scan_rows
    for header in headers:
        header_idx = header.row - 1  # 0-based
        for up in range(1, scan + 1):
            idx = header_idx - up
            if idx < 0:
                break
            values = [str(c.value).strip() for c in logical_rows[idx]
                      if c.value is not None and str(c.value).strip()]
            if values:
                header.title = " ".join(values)
                break
    return headers
