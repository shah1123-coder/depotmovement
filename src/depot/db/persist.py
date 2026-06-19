"""Transactional bulk inserts (insert mode only). One transaction per table per
run, executemany for throughput (Section 18.4)."""

from __future__ import annotations

from ..errors import ErrorCode
from ..logging import get_logger
from ..models import GateInValues, GateOutValues
from .connection import write_connection

log = get_logger("db.persist")

_IN_BLOCKED = {ErrorCode.NO_CONTAINER_ID.value, ErrorCode.DUPLICATE_RECORD.value,
               ErrorCode.INVALID_CONTAINER_STATUS_ID.value}
_OUT_BLOCKED = {ErrorCode.NO_BOOKING_ID.value, ErrorCode.NO_CONTAINER_ID.value,
                ErrorCode.DUPLICATE_RECORD.value, ErrorCode.INVALID_ECP_COUNT.value}


def plot_id_from_filename(filename: str) -> int | None:
    """Integer prefix before the first underscore: 123_1.xlsx -> 123."""
    import os
    stem = os.path.splitext(os.path.basename(filename))[0]
    prefix = stem.split("_", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def insert_gate_in(records: list[GateInValues]) -> int:
    rows = [r for r in records
            if not r.ErrorCode and r.PlotID is not None and r.ContainerId is not None]
    if not rows:
        return 0
    with write_connection() as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO dbo.PlotInDetails "
            "(PlotID, ContainerId, PlotInDate, PlotInStatus, CreatedBy, Remarks, "
            " BookingId, EditedBy) VALUES (?,?,?,?,?,?,?,?)",
            [(r.PlotID, r.ContainerId, r.PlotInDate, "P", 1, r.Remarks,
              r.BookingId, 1) for r in rows])
        conn.commit()
    log.info("inserted_gate_in", count=len(rows))
    return len(rows)


def insert_gate_out(records: list[GateOutValues]) -> int:
    rows = [r for r in records
            if not r.ErrorCode and r.PlotId is not None and r.ContainerId is not None]
    if not rows:
        return 0
    with write_connection() as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO dbo.PlotOutDetails "
            "(BookingId, ContainerId, SealNo, Transporter, VehicleNo, PlotOutDate, "
            " PlotOutTime, Remarks, CreatedBy, PlotOutStatus, PlotId, EditedBy) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r.BookingId, r.ContainerId, r.SealNo, r.Transporter, r.VehicleNo,
              r.PlotOutDate, r.PlotOutTime, r.Remarks, 1, "P", r.PlotId, 1)
             for r in rows])
        conn.commit()
    log.info("inserted_gate_out", count=len(rows))
    return len(rows)


def insert_errors(error_rows: list[dict]) -> int:
    rows = [e for e in error_rows
            if e.get("ErrorCode") and e["ErrorCode"] != ErrorCode.DUPLICATE_RECORD.value]
    if not rows:
        return 0
    cols = ["GateType", "ErrorCode", "ContainerId", "PlotID", "PlotInID", "PlotOutId",
            "BookingId", "PlotInDate", "PlotOutDate", "PlotOutTime", "PlotInStatus",
            "PlotOutStatus", "OutBookingID", "CreatedBy", "Remarks", "SealNo",
            "Transporter", "VehicleNo", "ContType", "ContainerStatusId"]
    placeholders = ",".join("?" * len(cols))
    with write_connection() as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(
            f"INSERT INTO dbo.DepotMovementError ({','.join(cols)}) VALUES ({placeholders})",
            [tuple(e.get(c) for c in cols) for e in rows])
        conn.commit()
    log.info("inserted_errors", count=len(rows))
    return len(rows)
