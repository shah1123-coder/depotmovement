"""Per-workbook extraction pipeline (pure, errors-as-data). Produces extraction
records; batched DB validation + output happen once per run in the persist step.
"""

from __future__ import annotations

from pathlib import Path

from .cache import dedup
from .detect.boundaries import find_boundary
from .detect.headers import detect_headers
from .detect.titles import attach_titles
from .extract.direction import resolve_direction, workbook_fallback
from .extract.gate_in import extract_gate_in
from .extract.gate_out import extract_gate_out
from .extract.tables import extract_table
from .logging import bind, get_logger
from .models import Direction, GateInRecord, GateOutRecord
from .workbook.loader import open_workbook
from .workbook.sheets import select_sheets

log = get_logger("pipeline")


class WorkbookExtraction:
    def __init__(self, file: str, message_id: str, region: str):
        self.file = file
        self.message_id = message_id
        self.region = region
        self.in_records: list[GateInRecord] = []
        self.out_records: list[GateOutRecord] = []
        self.failures: list[dict] = []
        self.skipped = False


def extract_workbook(file_path: str, message_id: str = "") -> WorkbookExtraction:
    p = Path(file_path)
    bind(job_id=p.name)
    result = WorkbookExtraction(file=file_path, message_id=message_id, region="")

    # Dedup: skip already-seen content.
    try:
        h = dedup.content_hash(p)
        if dedup.is_duplicate(h):
            log.info("dedup_skip", file=p.name)
            result.skipped = True
            return result
        dedup.mark_seen(h)
    except Exception as exc:
        log.warning("dedup_unavailable", file=p.name, error=str(exc))

    loaded = open_workbook(p)
    if not loaded.succeeded or loaded.value is None:
        result.failures.extend(f.model_dump() for f in loaded.failures)
        return result
    views = loaded.value

    selected = select_sheets(views)
    if selected:
        result.region = selected[0][1].name

    # Pair detection views with extraction views by title for value reads.
    extraction_by_title = {v.title: v for v in views.extraction}

    pending: list[tuple] = []  # (table, region, sources)
    for view, region, logical_rows in selected:
        ext_view = extraction_by_title.get(view.title)
        ext_rows = logical_rows
        if ext_view is not None:
            from .workbook.grid import build_logical_rows
            ext_rows = build_logical_rows(ext_view)

        headers = attach_titles(detect_headers(view.title, logical_rows), logical_rows)
        for header in headers:
            region_box = find_boundary(header, ext_rows)
            table = extract_table(region, region_box, ext_rows)
            sources = [table.title, view.title, p.name]
            table.direction = resolve_direction(table, region, sources)
            pending.append((table, region))

    # Workbook-level direction fallback for ambiguous tables.
    all_dirs = [t.direction for t, _ in pending]
    fallback = workbook_fallback(all_dirs)
    for table, region in pending:
        direction = table.direction
        if direction == Direction.UNRESOLVED and fallback != Direction.UNRESOLVED:
            direction = fallback
        if direction == Direction.IN:
            result.in_records.extend(extract_gate_in(table, region))
        elif direction == Direction.OUT:
            result.out_records.extend(extract_gate_out(table, region))
        # UNRESOLVED -> quarantined, excluded from results & insertion.

    log.info("extracted", file=p.name, region=result.region,
             in_count=len(result.in_records), out_count=len(result.out_records))
    return result
