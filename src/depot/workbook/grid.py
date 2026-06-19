"""Merged-cell normalization: rebuild each sheet as a logical grid.

Everything downstream reads logical cells, never the raw sheet.
"""

from __future__ import annotations

from ..models import LogicalCell


def _build_merge_map(view) -> dict[tuple[int, int], tuple[int, int, int, int]]:
    """Map every (row,col) inside a merged range to that range's bounds."""
    mp: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for (min_r, min_c, max_r, max_c) in view.merged_ranges():
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                mp[(r, c)] = (min_r, min_c, max_r, max_c)
    return mp


def build_logical_rows(view) -> list[list[LogicalCell]]:
    merge_map = _build_merge_map(view)
    rows: list[list[LogicalCell]] = []
    max_row = view.max_row
    max_col = view.max_col

    for r in range(1, max_row + 1):
        logical_row: list[LogicalCell] = []
        c = 1
        while c <= max_col:
            bounds = merge_map.get((r, c))
            if bounds:
                min_r, min_c, max_r, max_c = bounds
                if (r, c) == (min_r, min_c):
                    value = view.cell(min_r, min_c)
                    logical_row.append(LogicalCell(
                        row=r, end_row=max_r, start_col=c, end_col=max_c,
                        value=value,
                        is_horizontal_merge=max_c > min_c,
                        is_vertical_merge=max_r > min_r,
                    ))
                    c = max_c + 1
                else:
                    # inside a merge but not top-left -> skip
                    c += 1
            else:
                logical_row.append(LogicalCell(
                    row=r, end_row=r, start_col=c, end_col=c,
                    value=view.cell(r, c),
                ))
                c += 1
        rows.append(logical_row)
    return rows
