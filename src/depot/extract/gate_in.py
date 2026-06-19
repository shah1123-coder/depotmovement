"""Field extraction for Gate-In tables. Container is the anchor; date/time use
the FIRST match in the row (Section 14.2)."""

from __future__ import annotations

from ..models import ExtractedTable, GateInRecord
from ..regions.base import RegionProfile
from . import columns


def extract_gate_in(table: ExtractedTable, region: RegionProfile) -> list[GateInRecord]:
    remark_col = columns.resolve_column(
        table, markers=region.markers.get("in_remark", []))

    records: list[GateInRecord] = []
    for row in table.rows:
        joined = " ".join(row.cells)
        container = region.find_container(joined)
        if not container:  # no container = skip row (anchor rule)
            continue
        date = region.find_date(joined) or ""
        time = region.find_time(joined) or ""
        remark = ""
        if remark_col is not None and remark_col < len(row.cells):
            remark = row.cells[remark_col]
        records.append(GateInRecord(
            container_no=container, date=date, time=time,
            remark=remark, container_status="", error_code=""))
    return records
