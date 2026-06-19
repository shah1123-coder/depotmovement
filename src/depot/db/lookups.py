"""Read-only, batched ICMS lookups (Section 16.2). Never query per record."""

from __future__ import annotations

import re

from ..settings import get_settings
from .connection import chunked, read_connection

_BOOKED_QTY = re.compile(r"(\d+)\s*X\s*(.+)", re.IGNORECASE)


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def get_container_ids(container_nos: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    keys = list({c for c in container_nos if c})
    with read_connection() as conn:
        cur = conn.cursor()
        for chunk in chunked(keys):
            cur.execute(
                f"SELECT ContainerNo, ContainerId FROM ContainerEntry "
                f"WHERE ContainerNo IN ({_placeholders(len(chunk))})", chunk)
            for row in cur.fetchall():
                out[str(row[0]).upper()] = int(row[1])
    return out


def get_container_info(container_nos: list[str]) -> dict[str, dict]:
    """Returns {ContainerNo: {status_id, plot_id, plot_name}} keeping only rows
    whose status is in the relevant set."""
    relevant = set(get_settings().relevant_status_ids)
    out: dict[str, dict] = {}
    keys = list({c for c in container_nos if c})
    with read_connection() as conn:
        cur = conn.cursor()
        for chunk in chunked(keys):
            cur.execute(
                f"SELECT ContainerNo, ContainerStatusId, LocationPlotId, PlotName "
                f"FROM ContainerEntry WHERE ContainerNo IN ({_placeholders(len(chunk))})",
                chunk)
            for row in cur.fetchall():
                status = int(row[1]) if row[1] is not None else None
                if status is not None and status not in relevant:
                    continue
                out[str(row[0]).upper()] = {
                    "status_id": status,
                    "plot_id": int(row[2]) if row[2] is not None else None,
                    "plot_name": row[3] or "",
                }
    return out


def get_container_types(container_nos: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    keys = list({c for c in container_nos if c})
    with read_connection() as conn:
        cur = conn.cursor()
        for chunk in chunked(keys):
            cur.execute(
                f"SELECT ContainerNo, ContainerType FROM ContainerEntry "
                f"WHERE ContainerNo IN ({_placeholders(len(chunk))})", chunk)
            for row in cur.fetchall():
                out[str(row[0]).upper()] = row[1] or ""
    return out


def get_depot_names(container_nos: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    keys = list({c for c in container_nos if c})
    sql = (
        "WITH ranked AS ("
        "  SELECT ce.ContainerNo, pd.PortName, "
        "    ROW_NUMBER() OVER (PARTITION BY ce.ContainerNo ORDER BY pid.PlotInDate DESC) rn "
        "  FROM ContainerEntry ce "
        "  JOIN PlotInDetails pid ON pid.ContainerId = ce.ContainerId "
        "  JOIN PortDetails pd ON pd.PortId = pid.PortId "
        "  JOIN LocationPortMapping lpm ON lpm.PortId = pd.PortId AND lpm.IsActive=1 AND lpm.IsPrimary=1 "
        "  JOIN LocationTypeMapping ltm ON ltm.LocationId = lpm.LocationId AND ltm.LocationTypeId=2 "
        "  WHERE ce.ContainerNo IN ({ph})"
        ") SELECT ContainerNo, PortName FROM ranked WHERE rn=1"
    )
    with read_connection() as conn:
        cur = conn.cursor()
        for chunk in chunked(keys):
            cur.execute(sql.format(ph=_placeholders(len(chunk))), chunk)
            for row in cur.fetchall():
                out[str(row[0]).upper()] = row[1] or ""
    return out


def get_booking_ids(refs: list[str]) -> dict[str, int]:
    """Numeric refs resolve as-is; non-numeric resolve against BookingNo, also
    trying a trailing-letters-stripped variant."""
    out: dict[str, int] = {}
    non_numeric: set[str] = set()
    for ref in refs:
        if not ref:
            continue
        if ref.isdigit():
            out[ref] = int(ref)
        else:
            non_numeric.add(ref)
            stripped = re.sub(r"[A-Za-z]+$", "", ref)
            if stripped and stripped != ref:
                non_numeric.add(stripped)
    if non_numeric:
        keys = list(non_numeric)
        with read_connection() as conn:
            cur = conn.cursor()
            for chunk in chunked(keys):
                cur.execute(
                    f"SELECT BookingNo, BookingId FROM BookingDetails "
                    f"WHERE BookingNo IN ({_placeholders(len(chunk))})", chunk)
                for row in cur.fetchall():
                    out[str(row[0])] = int(row[1])
    return out


def get_booked_quantities(booking_ids: list[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    keys = list({b for b in booking_ids if b is not None})
    with read_connection() as conn:
        cur = conn.cursor()
        for chunk in chunked(keys):
            cur.execute(
                f"SELECT BookingId, BookedContainerQty FROM BookingDetails "
                f"WHERE BookingId IN ({_placeholders(len(chunk))})", chunk)
            for row in cur.fetchall():
                total = 0
                for m in _BOOKED_QTY.finditer(str(row[1] or "")):
                    total += int(m.group(1))
                out[int(row[0])] = total
    return out


def get_plotted_counts(booking_ids: list[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    keys = list({b for b in booking_ids if b is not None})
    with read_connection() as conn:
        cur = conn.cursor()
        for chunk in chunked(keys):
            cur.execute(
                f"SELECT BookingId, COUNT(ContainerId) FROM PlotOutDetails "
                f"WHERE BookingId IN ({_placeholders(len(chunk))}) GROUP BY BookingId",
                chunk)
            for row in cur.fetchall():
                out[int(row[0])] = int(row[1])
    return out


def check_in_duplicate(container_id: int, date_str: str) -> bool:
    with read_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 1 FROM PlotInDetails "
            "WHERE ContainerId=? AND CAST(PlotInDate AS DATE)=?", container_id, date_str)
        return cur.fetchone() is not None


def check_out_duplicate(container_id: int, date_str: str, booking_id) -> bool:
    with read_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 1 FROM PlotOutDetails "
            "WHERE ContainerId=? AND CAST(PlotOutDate AS DATE)=? AND BookingId=?",
            container_id, date_str, booking_id)
        return cur.fetchone() is not None
