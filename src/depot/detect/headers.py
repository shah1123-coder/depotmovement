"""Header-run detection: a run of >= min_header_cells consecutive plain-text
logical cells marks the top of a table."""

from __future__ import annotations

from ..models import HeaderRun, LogicalCell
from ..settings import get_settings


def is_plain_text(cell: LogicalCell) -> bool:
    """Plain text only: a non-empty string that is not a formula."""
    v = cell.value
    if not isinstance(v, str):
        return False
    s = v.strip()
    return bool(s) and not s.startswith("=")


def _runs_in_row(row: list[LogicalCell], min_cells: int) -> list[list[LogicalCell]]:
    runs = []
    current: list[LogicalCell] = []
    for cell in row:
        if is_plain_text(cell):
            current.append(cell)
        else:
            if len(current) >= min_cells:
                runs.append(current)
            current = []
    if len(current) >= min_cells:
        runs.append(current)
    return runs


def _row_looks_like_header(row: list[LogicalCell], min_cells: int) -> bool:
    return bool(_runs_in_row(row, min_cells))


def detect_headers(sheet: str, logical_rows: list[list[LogicalCell]]) -> list[HeaderRun]:
    min_cells = get_settings().detection.min_header_cells
    headers: list[HeaderRun] = []
    skip_until = -1

    for idx, row in enumerate(logical_rows):
        if idx <= skip_until:
            continue
        runs = _runs_in_row(row, min_cells)
        if not runs:
            continue
        row_no = idx + 1
        for run in runs:
            headers.append(HeaderRun(
                sheet=sheet,
                row=row_no,
                start_col=run[0].start_col,
                end_col=run[-1].end_col,
                cell_count=len(run),
                values=[str(c.value).strip() for c in run],
                cells=run,
            ))
        # skip following rows that also look like headers (stacked headers)
        j = idx + 1
        while j < len(logical_rows) and _row_looks_like_header(logical_rows[j], min_cells):
            j += 1
        skip_until = j - 1

    return headers
