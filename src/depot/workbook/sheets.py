"""Sheet eligibility (Section 10.3): decide which sheets to process and bind
each to its region profile."""

from __future__ import annotations

from ..models import LogicalCell
from ..regions.base import RegionProfile
from ..regions.detector import detect_region
from .grid import build_logical_rows


def _cell_texts(logical_rows: list[list[LogicalCell]]) -> list[str]:
    texts = []
    for row in logical_rows:
        for cell in row:
            if isinstance(cell.value, str) and cell.value.strip():
                texts.append(cell.value)
    return texts


def _detect_in_out(region: RegionProfile, texts: list[str]) -> tuple[bool, bool]:
    has_in = False
    has_out = False
    for t in texts:
        if region.rx_gate_in.search(t) or region.rx_standalone_in.search(t) \
                or any(tok in t for tok in region.direction_in_tokens):
            has_in = True
        if region.rx_gate_out.search(t) or region.rx_standalone_out.search(t) \
                or any(tok in t for tok in region.direction_out_tokens):
            has_out = True
    return has_in, has_out


def select_sheets(views) -> list[tuple[object, RegionProfile, list[list[LogicalCell]]]]:
    """Return (view, region, logical_rows) for each eligible sheet."""
    selected = []
    for view in views.detection:
        region = detect_region(view.title)
        name = view.title.upper()

        if region.is_excluded_sheet(name):
            continue

        logical_rows = build_logical_rows(view)
        texts = _cell_texts(logical_rows)
        has_in, has_out = _detect_in_out(region, texts)

        if region.is_forced_sheet(view.title):
            selected.append((view, region, logical_rows))
            continue

        if region.is_recognized_sheet(view.title):
            if has_in and has_out:
                continue  # ambiguous
            selected.append((view, region, logical_rows))
            continue

        # generic sheet: process only if exactly one of IN/OUT present (XOR)
        if has_in ^ has_out:
            selected.append((view, region, logical_rows))

    return selected
