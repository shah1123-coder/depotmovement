"""ICMS database client for container status lookup.

Queries ContainerEntry.ContainerStatusId for a set of container numbers
(see status.md section 8.1 / 8.2). Only IDs in {2, 3, 6, 7} are considered
relevant for gate-move reconciliation; anything else is returned as None.
"""
import os
import re
from typing import Iterable

import pyodbc

# Reference master table from status.md section 5.
CONTAINER_STATUS_MASTER = {
    1:  "AV",    2:  "EY",   3:  "ECP",  4:  "ECP",  5:  "LIP",
    6:  "LOB",   7:  "LAD",  8:  "EM",   9:  "TLAD", 10: "TLOB",
    11: "LDO",  12: "DM",   13: "VSO",  14: "PO",   15: "DDS",
}

RELEVANT_STATUS_IDS = {2, 3, 6, 7}

_SERVER   = os.environ.get("ICMS_SERVER",   "10.10.0.72")
_DATABASE = os.environ.get("ICMS_DATABASE", "ICMS")
_USER     = os.environ.get("ICMS_USER",     "Sa")
_PASSWORD = os.environ.get("ICMS_PASSWORD", "pass@2020$")
_DRIVER   = os.environ.get("ICMS_DRIVER",   "ODBC Driver 17 for SQL Server")

_CHUNK = 1000


def _connect():
    if _USER and _PASSWORD:
        conn_str = (
            f"DRIVER={{{_DRIVER}}};SERVER={_SERVER};DATABASE={_DATABASE};"
            f"UID={_USER};PWD={_PASSWORD}"
        )
    else:
        conn_str = (
            f"DRIVER={{{_DRIVER}}};SERVER={_SERVER};DATABASE={_DATABASE};"
            "Trusted_Connection=yes"
        )
    return pyodbc.connect(conn_str)


def _connect_archeet():
    """Specific connection for the archeet database."""
    conn_str = (
        f"DRIVER={{{_DRIVER}}};SERVER={_SERVER};DATABASE=archeet;"
        f"UID={_USER};PWD={_PASSWORD}"
    )
    return pyodbc.connect(conn_str)


def insert_gate_in_records(payloads: list[dict]) -> int:
    """Insert error-free Gate In records into archeet.dbo.PlotInDetails.
    Returns the count of records inserted.
    """
    valid = [
        p["values"] for p in payloads 
        if not p["values"].get("ErrorCode") and p["values"].get("PlotID") is not None
    ]
    if not valid:
        return 0

    sql = """
        INSERT INTO dbo.PlotInDetails (
            PlotID, ContainerId, PlotInDate, PlotInStatus, CreatedBy, Remarks, BookingId, EditedBy
        ) VALUES (?, ?, ?, ?, 1, ?, ?, 1)
    """
    params = [
        (
            v.get("PlotID"),
            v.get("ContainerId"),
            v.get("PlotInDate"),
            v.get("PlotInStatus"),
            v.get("Remarks"),
            v.get("BookingId")
        )
        for v in valid
    ]
    
    with _connect_archeet() as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, params)
        conn.commit()
    return len(params)


def insert_gate_error_records(payloads: list[dict]) -> int:
    """Insert gate movement error records into archeet.dbo.DepotMovementError.
    Returns the count of records inserted.
    """
    valid = [p["values"] for p in payloads if p.get("values")]
    if not valid:
        return 0

    sql = """
        INSERT INTO dbo.DepotMovementError (
            GateType, ErrorCode, ContainerId, PlotID, PlotInID, PlotOutId,
            BookingId, PlotInDate, PlotOutDate, PlotOutTime, PlotInStatus,
            PlotOutStatus, OutBookingID, CreatedBy, Remarks, SealNo,
            Transporter, VehicleNo, ContType, ContainerStatusId
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = [
        (
            v.get("GateType"),
            v.get("ErrorCode"),
            v.get("ContainerId"),
            v.get("PlotID") or v.get("PlotId"),
            v.get("PlotInID"),
            v.get("PlotOutId"),
            v.get("BookingId"),
            v.get("PlotInDate"),
            v.get("PlotOutDate"),
            v.get("PlotOutTime"),
            v.get("PlotInStatus"),
            v.get("PlotOutStatus"),
            v.get("OutBookingID"),
            v.get("CreatedBy"),
            v.get("Remarks"),
            v.get("SealNo"),
            v.get("Transporter"),
            v.get("VehicleNo"),
            v.get("ContType"),
            v.get("ContainerStatusId")
        )
        for v in valid
    ]

    with _connect_archeet() as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, params)
        conn.commit()
    return len(params)


def insert_gate_out_records(payloads: list[dict]) -> int:
    """Insert error-free Gate Out records into archeet.dbo.PlotOutDetails.
    Returns the count of records inserted.
    """
    valid = [
        p["values"] for p in payloads 
        if not p["values"].get("ErrorCode") and p["values"].get("PlotId") is not None
    ]
    if not valid:
        return 0

    sql = """
        INSERT INTO dbo.PlotOutDetails (
            BookingId, ContainerId, SealNo, Transporter, VehicleNo, 
            PlotOutDate, PlotOutTime, Remarks, CreatedBy, PlotOutStatus, PlotId, EditedBy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1)
    """
    params = [
        (
            v.get("BookingId"),
            v.get("ContainerId"),
            v.get("SealNo"),
            v.get("Transporter"),
            v.get("VehicleNo"),
            v.get("PlotOutDate"),
            v.get("PlotOutTime"),
            v.get("Remarks"),
            v.get("PlotOutStatus"),
            v.get("PlotId")
        )
        for v in valid
    ]

    with _connect_archeet() as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, params)
        conn.commit()
    return len(params)


def get_container_status_ids(container_nos: Iterable[str]) -> dict[str, int | None]:
    """Return {container_no: ContainerStatusId} for ids in RELEVANT_STATUS_IDS,
    else None. Containers not found in ContainerEntry are also returned as None."""
    info = get_container_info(container_nos)
    return {cid: (v[0] if v else None) for cid, v in info.items()}


def get_container_info(container_nos: Iterable[str]) -> dict[str, tuple[int | None, int | None, str] | None]:
    """Return {container_no: (status_id_or_None, location_plot_id_or_None, plot_name)}.
    status_id is the ContainerStatusId if in RELEVANT_STATUS_IDS else None.
    location_plot_id is the raw ContainerEntry.LocationPlotId (or None).
    plot_name is resolved via PlotInformationDetails; empty string if unknown.
    Containers absent from ContainerEntry map to None."""
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, tuple[int | None, int | None, str] | None] = {cid: None for cid in ids}
    if not ids:
        return result

    raw: dict[str, tuple[int | None, int | None]] = {}
    plot_ids: set[int] = set()
    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            sql = (
                f"SELECT ContainerNo, ContainerStatusId, LocationPlotId "
                f"FROM ContainerEntry WHERE ContainerNo IN ({placeholders})"
            )
            cursor.execute(sql, chunk)
            for container_no, status_id, location_plot_id in cursor.fetchall():
                key = str(container_no).strip().upper().replace(" ", "")
                sid = int(status_id) if status_id in RELEVANT_STATUS_IDS else None
                pid = int(location_plot_id) if location_plot_id is not None else None
                raw[key] = (sid, pid)
                if pid is not None:
                    plot_ids.add(pid)

        plot_name_by_id: dict[int, str] = {}
        plot_ids_list = sorted(plot_ids)
        for i in range(0, len(plot_ids_list), _CHUNK):
            chunk = plot_ids_list[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            sql = (
                f"SELECT PlotID, PlotName FROM PlotInformationDetails "
                f"WHERE PlotID IN ({placeholders})"
            )
            cursor.execute(sql, chunk)
            for pid, pname in cursor.fetchall():
                plot_name_by_id[int(pid)] = str(pname).strip() if pname is not None else ""

    for cid, (sid, pid) in raw.items():
        result[cid] = (sid, pid, plot_name_by_id.get(pid, "") if pid is not None else "")
    return result


def get_latest_depot_names(container_nos: Iterable[str]) -> dict[str, str | None]:
    """Return {container_no: depot_name} using the latest PlotInDetails event
    joined to PortDetails.PortName (see plotname.md decision rule #1).

    Containers absent from the join (no plot-in event, or no PortDetails row)
    map to None. This is the authoritative depot for the container; do NOT
    use ContainerEntry.LocationPlotId for this.
    """
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, str | None] = {cid: None for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            sql = f"""
                WITH latest AS (
                    SELECT ce.ContainerNo,
                           dp.PortName AS DepotName,
                           ROW_NUMBER() OVER (
                               PARTITION BY ce.ContainerNo
                               ORDER BY pi.PlotInDate DESC
                           ) AS rn
                    FROM icms.dbo.ContainerEntry ce
                    INNER JOIN icms.dbo.PlotInDetails pi
                        ON pi.ContainerId = ce.ContainerId
                    INNER JOIN icms.dbo.PortDetails dp
                        ON dp.PortId = pi.PlotID
                    INNER JOIN icms.dbo.LocationPortMapping LPM
                        ON LPM.LocationId = dp.PortId
                       AND LPM.IsActive = 1
                       AND LPM.IsPrimary = 1
                    INNER JOIN icms.dbo.LocationTypeMapping LTM
                        ON LTM.LocationTypeId = 2
                       AND LTM.PortId = dp.PortId
                       AND LTM.IsActive = 1
                    INNER JOIN icms.dbo.PortDetails pd
                        ON pd.PortId = LPM.PortId
                    WHERE ce.ContainerNo IN ({placeholders})
                )
                SELECT ContainerNo, DepotName FROM latest WHERE rn = 1
            """
            cursor.execute(sql, chunk)
            for container_no, depot_name in cursor.fetchall():
                key = str(container_no).strip().upper().replace(" ", "")
                result[key] = str(depot_name).strip() if depot_name is not None else None
    return result


def get_container_ids(container_nos: Iterable[str]) -> dict[str, int | None]:
    """Return {container_no: ContainerId}; absent containers map to None."""
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, int | None] = {cid: None for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT ContainerNo, ContainerId FROM ContainerEntry "
                f"WHERE ContainerNo IN ({placeholders})",
                chunk,
            )
            for container_no, container_id in cursor.fetchall():
                key = str(container_no).strip().upper().replace(" ", "")
                result[key] = int(container_id) if container_id is not None else None
    return result


def container_ids_exist(container_ids: Iterable[int]) -> dict[int, bool]:
    """Return {ContainerId: True/False} using an EXISTS check against ContainerEntry."""
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, bool] = {cid: False for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for cid in ids:
            cursor.execute(
                """
                SELECT CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM icms.dbo.ContainerEntry
                        WHERE ContainerId = ?
                    )
                    THEN 1
                    ELSE 0
                END AS ContainerIdExists
                """,
                cid,
            )
            row = cursor.fetchone()
            result[cid] = bool(row[0]) if row else False
    return result


def booking_ids_exist(booking_ids: Iterable[int]) -> dict[int, bool]:
    """Return {BookingId: True/False} using an EXISTS check against BookingDetails."""
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, bool] = {bid: False for bid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for bid in ids:
            cursor.execute(
                """
                SELECT CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM icms.dbo.BookingDetails
                        WHERE BookingId = ?
                    )
                    THEN 1
                    ELSE 0
                END AS BookingIdExists
                """,
                bid,
            )
            row = cursor.fetchone()
            result[bid] = bool(row[0]) if row else False
    return result


_BOOKED_QTY_PART = re.compile(r"(\d+)\s*X\s*(.+)")


def get_booked_qty_by_booking_id(booking_ids: Iterable[int]) -> dict[int, int]:
    """Return {BookingId: total booked container count} by parsing the
    BookingDetails.BookedContainerQty string (format: "N X TYPE, M X TYPE, ...").
    Port of ecp/extract_booked_qty.ps1.
    """
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, int] = {bid: 0 for bid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT BookingId, BookedContainerQty FROM BookingDetails "
                f"WHERE BookingId IN ({placeholders})",
                chunk,
            )
            for booking_id, qty_str in cursor.fetchall():
                total = 0
                if qty_str:
                    for part in str(qty_str).split(","):
                        m = _BOOKED_QTY_PART.match(part.strip())
                        if m:
                            total += int(m.group(1))
                result[int(booking_id)] = total
    return result


def get_plotout_container_counts(booking_ids: Iterable[int]) -> dict[int, int]:
    """Return {BookingId: COUNT(ContainerId) in PlotOutDetails}."""
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, int] = {bid: 0 for bid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT BookingId, COUNT(ContainerId) FROM PlotOutDetails "
                f"WHERE BookingId IN ({placeholders}) GROUP BY BookingId",
                chunk,
            )
            for booking_id, cnt in cursor.fetchall():
                result[int(booking_id)] = int(cnt)
    return result


def get_depot_ids_by_name(depot_names: Iterable[str]) -> dict[str, int | None]:
    """Return {depot_name: PortDetails.PortId} using exact depot-name lookup."""
    names = sorted({str(name).strip() for name in depot_names if str(name).strip()})
    result: dict[str, int | None] = {name: None for name in names}
    if not names:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(names), _CHUNK):
            chunk = names[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT PortName, PortId FROM PortDetails WHERE PortName IN ({placeholders})",
                chunk,
            )
            for port_name, port_id in cursor.fetchall():
                key = str(port_name).strip()
                result[key] = int(port_id) if port_id is not None else None
    return result


def get_previous_gate_out_booking_ids(container_ids: Iterable[int]) -> dict[int, int | None]:
    """Return {ContainerId: latest PlotOutDetails.BookingId}.

    This follows plotname.md: order by PlotOutDate DESC, then PlotOutId DESC.
    """
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            sql = f"""
                WITH latest AS (
                    SELECT ContainerId,
                           BookingId,
                           ROW_NUMBER() OVER (
                               PARTITION BY ContainerId
                               ORDER BY PlotOutDate DESC, PlotOutId DESC
                           ) AS rn
                    FROM PlotOutDetails
                    WHERE ContainerId IN ({placeholders})
                )
                SELECT ContainerId, BookingId FROM latest WHERE rn = 1
            """
            cursor.execute(sql, chunk)
            for container_id, booking_id in cursor.fetchall():
                result[int(container_id)] = int(booking_id) if booking_id is not None else None
    return result


def get_latest_plot_in_ids_by_status(
    container_ids: Iterable[int],
    plot_in_status: str = "P",
) -> dict[int, int | None]:
    """Return {ContainerId: latest PlotInID for PlotInStatus}.

    Uses the same ordering pattern as the provided latest-row query:
    PlotInDate DESC, PlotInID DESC.
    """
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            sql = f"""
                WITH latest AS (
                    SELECT PlotInID,
                           ContainerId,
                           ROW_NUMBER() OVER (
                               PARTITION BY ContainerId
                               ORDER BY PlotInDate DESC, PlotInID DESC
                           ) AS rn
                    FROM PlotInDetails
                    WHERE PlotInStatus = ?
                      AND ContainerId IN ({placeholders})
                )
                SELECT ContainerId, PlotInID FROM latest WHERE rn = 1
            """
            cursor.execute(sql, [plot_in_status, *chunk])
            for container_id, plot_in_id in cursor.fetchall():
                result[int(container_id)] = int(plot_in_id) if plot_in_id is not None else None
    return result


def get_latest_plot_out_ids_by_status(
    container_ids: Iterable[int],
    plot_out_status: str = "P",
) -> dict[int, int | None]:
    """Return {ContainerId: latest PlotOutId for PlotOutStatus}.

    Uses PlotOutDate DESC, PlotOutId DESC as provided.
    """
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            sql = f"""
                WITH latest AS (
                    SELECT PlotOutId,
                           ContainerId,
                           ROW_NUMBER() OVER (
                               PARTITION BY ContainerId
                               ORDER BY PlotOutDate DESC, PlotOutId DESC
                           ) AS rn
                    FROM PlotOutDetails
                    WHERE PlotOutStatus = ?
                      AND ContainerId IN ({placeholders})
                )
                SELECT ContainerId, PlotOutId FROM latest WHERE rn = 1
            """
            cursor.execute(sql, [plot_out_status, *chunk])
            for container_id, plot_out_id in cursor.fetchall():
                result[int(container_id)] = int(plot_out_id) if plot_out_id is not None else None
    return result


def get_container_types(container_nos: Iterable[str]) -> dict[str, str | None]:
    """Return {container_no: ContainerEntry.ContainerType}; absent rows map to None."""
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, str | None] = {cid: None for cid in ids}
    if not ids:
        return result

    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT ContainerNo, ContainerType FROM ContainerEntry "
                f"WHERE ContainerNo IN ({placeholders})",
                chunk,
            )
            for container_no, container_type in cursor.fetchall():
                key = str(container_no).strip().upper().replace(" ", "")
                result[key] = str(container_type).strip() if container_type is not None else None
    return result


def plotin_records_exist(items: Iterable[tuple[int, str]]) -> set[tuple[int, str]]:
    """Return the subset of (ContainerId, PlotInDate) pairs already present in
    dbo.PlotInDetails. PlotInDate is compared as DATE."""
    pairs = {(int(c), str(d).strip()) for c, d in items if c is not None and d}
    found: set[tuple[int, str]] = set()
    if not pairs:
        return found
    with _connect() as conn:
        cursor = conn.cursor()
        for cid, pdate in pairs:
            cursor.execute(
                "SELECT COUNT(*) FROM dbo.PlotInDetails "
                "WHERE ContainerId = ? AND CAST(PlotInDate AS DATE) = ?",
                cid, pdate,
            )
            row = cursor.fetchone()
            if row and int(row[0]) > 0:
                found.add((cid, pdate))
    return found


def plotout_records_exist(items: Iterable[tuple[int, str, int]]) -> set[tuple[int, str, int]]:
    """Return the subset of (ContainerId, PlotOutDate, BookingId) triples already
    present in dbo.PlotOutDetails. PlotOutDate is compared as DATE."""
    triples = {
        (int(c), str(d).strip(), int(b))
        for c, d, b in items
        if c is not None and d and b is not None
    }
    found: set[tuple[int, str, int]] = set()
    if not triples:
        return found
    with _connect() as conn:
        cursor = conn.cursor()
        for cid, pdate, bid in triples:
            cursor.execute(
                "SELECT COUNT(*) FROM dbo.PlotOutDetails "
                "WHERE ContainerId = ? AND CAST(PlotOutDate AS DATE) = ? AND BookingId = ?",
                cid, pdate, bid,
            )
            row = cursor.fetchone()
            if row and int(row[0]) > 0:
                found.add((cid, pdate, bid))
    return found


def _booking_lookup_candidates(value: str) -> list[str]:
    ref = str(value).strip()
    candidates = [ref]
    stripped = re.sub(r"[A-Za-z]+$", "", ref).strip()
    if stripped and stripped != ref:
        candidates.append(stripped)
    return candidates


def get_booking_ids_by_reference(booking_refs: Iterable[str]) -> dict[str, int | None]:
    """Return integer BookingId for report booking values.

    Numeric values are already BookingId values. Non-numeric values are matched
    to BookingDetails.BookingNo, also trying a trailing-letter-stripped variant
    because some depot reports append suffixes like ``A``.
    """
    refs = sorted({str(ref).strip() for ref in booking_refs if str(ref).strip()})
    result: dict[str, int | None] = {}
    lookup_refs: set[str] = set()

    for ref in refs:
        if ref.isdigit():
            result[ref] = int(ref)
        else:
            result[ref] = None
            lookup_refs.update(_booking_lookup_candidates(ref))

    if not lookup_refs:
        return result

    booking_by_no: dict[str, int] = {}
    names = sorted(lookup_refs)
    with _connect() as conn:
        cursor = conn.cursor()
        for i in range(0, len(names), _CHUNK):
            chunk = names[i:i + _CHUNK]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT BookingNo, BookingId FROM BookingDetails "
                f"WHERE BookingNo IN ({placeholders})",
                chunk,
            )
            for booking_no, booking_id in cursor.fetchall():
                booking_by_no[str(booking_no).strip()] = int(booking_id)

    for ref in refs:
        if result[ref] is not None:
            continue
        for candidate in _booking_lookup_candidates(ref):
            if candidate in booking_by_no:
                result[ref] = booking_by_no[candidate]
                break
    return result
