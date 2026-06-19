"""Direction resolution (Section 13): one shared resolver for sheet hints and
final table routing. Never guess — ambiguous tables are quarantined."""

from __future__ import annotations

from ..models import Direction, ExtractedTable
from ..regions.base import RegionProfile


def _direction_from_text(region: RegionProfile, text: str) -> Direction:
    if not text:
        return Direction.UNRESOLVED
    has_in = bool(region.rx_standalone_in.search(text) or region.rx_gate_in.search(text)) \
        or any(tok in text for tok in region.direction_in_tokens)
    has_out = bool(region.rx_standalone_out.search(text) or region.rx_gate_out.search(text)) \
        or any(tok in text for tok in region.direction_out_tokens)
    if has_in and has_out:
        return Direction.UNRESOLVED
    if has_in:
        return Direction.IN
    if has_out:
        return Direction.OUT
    return Direction.UNRESOLVED


def resolve_direction(table: ExtractedTable, region: RegionProfile,
                      sources: list[str]) -> Direction:
    """Check sources (filename, parent folder, workbook name) in priority order;
    return the first decisive (non-ambiguous, non-empty) hit."""
    for src in sources:
        d = _direction_from_text(region, src)
        if d in (Direction.IN, Direction.OUT):
            return d
        # If both tokens present in this source -> genuinely ambiguous, stop.
        has_in = bool(region.rx_standalone_in.search(src or "") or region.rx_gate_in.search(src or "")) \
            or any(tok in (src or "") for tok in region.direction_in_tokens)
        has_out = bool(region.rx_standalone_out.search(src or "") or region.rx_gate_out.search(src or "")) \
            or any(tok in (src or "") for tok in region.direction_out_tokens)
        if has_in and has_out:
            return Direction.UNRESOLVED
    return Direction.UNRESOLVED


def workbook_fallback(directions: list[Direction]) -> Direction:
    """If exactly one direction appears across all tables, apply it to ambiguous
    ones; otherwise stay UNRESOLVED."""
    resolved = {d for d in directions if d in (Direction.IN, Direction.OUT)}
    if len(resolved) == 1:
        return next(iter(resolved))
    return Direction.UNRESOLVED
