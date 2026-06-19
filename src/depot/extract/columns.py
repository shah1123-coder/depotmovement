"""Generic column resolver reused for every field (booking, seal, transporter,
remarks, vehicle). Do NOT write a separate finder per field."""

from __future__ import annotations

from typing import Optional, Pattern

from ..models import ExtractedTable


def _col_count(table: ExtractedTable) -> int:
    n = len(table.header)
    for row in table.rows:
        n = max(n, len(row.cells))
    return n


def _column_values(table: ExtractedTable, col: int) -> list[str]:
    return [row.cells[col] for row in table.rows if col < len(row.cells)]


def resolve_column(table: ExtractedTable, *,
                   regex: Optional[Pattern] = None,
                   markers: Optional[list[str]] = None,
                   fallback_regex: Optional[Pattern] = None) -> Optional[int]:
    n = _col_count(table)

    # 1. Regex column — rightmost column whose cells match `regex`.
    if regex is not None:
        for col in range(n - 1, -1, -1):
            if any(regex.search(v) for v in _column_values(table, col) if v):
                return col

    # 2. Marker column — a column whose header matches one of `markers`.
    if markers:
        lowered = [m.lower() for m in markers]
        for col, head in enumerate(table.header):
            h = (head or "").lower()
            if any(m in h for m in lowered):
                return col

    # 3. Fallback regex column.
    if fallback_regex is not None:
        for col in range(n - 1, -1, -1):
            if any(fallback_regex.search(v) for v in _column_values(table, col) if v):
                return col

    return None
