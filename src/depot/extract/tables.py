"""Build the clean tabular structure for a detected table region and flag each
row's validity by container match."""

from __future__ import annotations

from ..detect.boundaries import clip_cell_value
from ..errors import ErrorCode
from ..models import ExtractedTable, LogicalCell, RawRow, TableRegion
from ..regions.base import RegionProfile


def extract_table(region: RegionProfile, table_region: TableRegion,
                  logical_rows: list[list[LogicalCell]]) -> ExtractedTable:
    start_col = table_region.start_col
    end_col = table_region.end_col

    header_values = [str(c.value).strip() if c.value is not None else ""
                     for c in table_region.header.cells]

    rows: list[RawRow] = []
    row_errors: list[str] = []

    for r in range(table_region.data_start_row, table_region.data_end_row + 1):
        idx = r - 1
        if idx < 0 or idx >= len(logical_rows):
            continue
        cells: list[str] = []
        for cell in logical_rows[idx]:
            clipped = clip_cell_value(cell, start_col, end_col)
            if clipped is not None:
                cells.append(clipped)
        joined = " ".join(cells)
        error = "" if region.find_container(joined) else ErrorCode.INVALID_CONTAINER_NUMBER.value
        rows.append(RawRow(source_row=r, cells=cells))
        row_errors.append(error)

    return ExtractedTable(
        sheet=table_region.sheet,
        title=table_region.header.title or table_region.sheet,
        header=header_values,
        rows=rows,
        row_errors=row_errors,
    )
