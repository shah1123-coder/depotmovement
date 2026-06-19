"""Determine each table's data region: from header+1 down to the first fully
blank logical row, clipped to the header's column window."""

from __future__ import annotations

from ..models import HeaderRun, LogicalCell, TableRegion


def _row_is_blank(row: list[LogicalCell]) -> bool:
    for cell in row:
        if cell.value is not None and str(cell.value).strip():
            return False
    return True


def find_boundary(header: HeaderRun,
                  logical_rows: list[list[LogicalCell]]) -> TableRegion:
    data_start = header.row + 1
    data_end = header.row  # default: empty table
    idx = data_start - 1
    while idx < len(logical_rows):
        if _row_is_blank(logical_rows[idx]):
            break
        data_end = idx + 1
        idx += 1

    return TableRegion(
        sheet=header.sheet,
        header=header,
        data_start_row=data_start,
        data_end_row=data_end,
        start_col=header.start_col,
        end_col=header.end_col,
    )


def clip_cell_value(cell: LogicalCell, start_col: int, end_col: int) -> str | None:
    """Return the cell's normalized value if it overlaps [start_col, end_col]."""
    start = max(cell.start_col, start_col)
    end = min(cell.end_col, end_col)
    if start > end:
        return None
    return "" if cell.value is None else str(cell.value).strip()
