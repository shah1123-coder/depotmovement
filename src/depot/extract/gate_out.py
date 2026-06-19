"""Field extraction for Gate-Out tables. Container is the anchor; date/time use
the LAST match in the row (Section 14.3). Booking failure sets NO_BOOKING_ID
now and that code must survive later validation."""

from __future__ import annotations

from ..errors import ErrorCode
from ..models import ExtractedTable, GateOutRecord
from ..regions.base import RegionProfile
from . import columns


def _last(matches: list[str]) -> str:
    return matches[-1] if matches else ""


def extract_gate_out(table: ExtractedTable, region: RegionProfile) -> list[GateOutRecord]:
    booking_col = columns.resolve_column(
        table, regex=region.rx_booking_main,
        markers=region.markers.get("out_booking", []),
        fallback_regex=region.rx_booking_fallback)
    seal_col = columns.resolve_column(table, markers=region.markers.get("seal", []))
    transporter_col = columns.resolve_column(
        table, markers=region.markers.get("transporter", []))
    remark_col = columns.resolve_column(
        table, markers=region.markers.get("out_remark", []))
    vehicle_col = columns.resolve_column(
        table, markers=region.markers.get("vehicle", []),
        fallback_regex=region.rx_vehicle)

    def cell(col, row):
        return row.cells[col] if col is not None and col < len(row.cells) else ""

    records: list[GateOutRecord] = []
    for row in table.rows:
        joined = " ".join(row.cells)
        container = region.find_container(joined)
        if not container:
            continue

        booking_raw = cell(booking_col, row)
        booking = region.find_booking(booking_raw) or region.find_booking(joined) or ""
        error_code = "" if booking else ErrorCode.NO_BOOKING_ID.value

        dates = region.rx_date.findall(joined)
        date = ""
        if dates:
            m = list(region.rx_date.finditer(joined))
            date = m[-1].group(0)
        times = list(region.rx_time.finditer(joined))
        time = times[-1].group(0) if times else ""

        records.append(GateOutRecord(
            container_id=container,
            booking_id=booking,
            seal_no=cell(seal_col, row),
            plot_out_date=date,
            plot_out_time=time,
            transporter=cell(transporter_col, row),
            vehicle_no=cell(vehicle_col, row) or (region.find_vehicle(joined) or ""),
            remarks=cell(remark_col, row),
            error_code=error_code,
        ))
    return records
