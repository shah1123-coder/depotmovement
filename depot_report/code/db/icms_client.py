"""ICMS database client. All access via the sqlcmd CLI (no pyodbc)."""

import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

# csv/depot_report/code/db/icms_client.py -> parents[3] == csv root
CSV_ROOT_ENV = Path(__file__).resolve().parents[3]


def _load_env() -> None:
    """Seed os.environ from csv/info.txt without overriding existing variables."""
    env_path = CSV_ROOT_ENV / "info.txt"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env()

CONTAINER_STATUS_MASTER = {
    1:  "AV",    2:  "EY",   3:  "ECP",  4:  "ECP",  5:  "LIP",
    6:  "LOB",   7:  "LAD",  8:  "EM",   9:  "TLAD", 10: "TLOB",
    11: "LDO",  12: "DM",   13: "VSO",  14: "PO",   15: "DDS",
}
RELEVANT_STATUS_IDS = {2, 3, 6, 7}

_SERVER   = os.environ.get("ICMS_SERVER",   "10.1.0.6")
_DATABASE = os.environ.get("ICMS_DATABASE", "ICMS")
_USER     = os.environ.get("ICMS_USER",     "")
_PASSWORD = os.environ.get("ICMS_PASSWORD", "")
_WRITE_DATABASE = os.environ.get("PROCESS_EMAIL_DATABASE", "EMail_Reader_Process_Data")
_SQLCMD   = os.environ.get("SQLCMD_PATH", "sqlcmd")

_CHUNK = 1000
_INSERT_CHUNK = 500  # SQL Server allows at most 1000 row value expressions
_SEP = "|"
_NULL_TOKEN = "~NULL~"


def _lit(value) -> str:
    """Render a Python value as a T-SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    return "N'" + str(value).replace("'", "''") + "'"


def _in_list(values: Iterable) -> str:
    return ",".join(_lit(v) for v in values)


def run_sql(sql: str, database: str | None = None) -> list[str]:
    """Execute T-SQL via sqlcmd and return non-empty output lines."""
    script = "SET NOCOUNT ON; SET QUOTED_IDENTIFIER ON; SET XACT_ABORT ON;\n" + sql
    fd, path = tempfile.mkstemp(suffix=".sql", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(script)
        cmd = [_SQLCMD, "-S", _SERVER, "-d", database or _DATABASE]
        if _USER and _PASSWORD:
            cmd += ["-U", _USER, "-P", _PASSWORD]
        else:
            cmd += ["-E"]
        cmd += ["-C", "-i", path, "-W", "-h", "-1", "-s", _SEP, "-b", "-l", "30"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"sqlcmd failed (exit {result.returncode}): {detail}")
        return [line for line in result.stdout.splitlines() if line.strip()]
    finally:
        os.unlink(path)


def _query_rows(sql: str, database: str | None = None) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for line in run_sql(sql, database=database):
        rows.append([None if part == _NULL_TOKEN else part for part in line.split(_SEP)])
    return rows


def _col(expr: str) -> str:
    """Make a column safe for text transport: cast to NVARCHAR, NULL->sentinel,
    strip the separator character."""
    return (
        f"REPLACE(ISNULL(CAST({expr} AS NVARCHAR(4000)), N'{_NULL_TOKEN}'), N'{_SEP}', N' ')"
    )


def _insert_rows(table_sql: str, rows: list[tuple], database: str) -> int:
    if not rows:
        return 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[i:i + _INSERT_CHUNK]
        values = ",\n".join("(" + ",".join(_lit(v) for v in row) + ")" for row in chunk)
        run_sql(f"{table_sql} VALUES\n{values};", database=database)
    return len(rows)


# ---------- Inserts (write database) ----------

def insert_gate_in_records(payloads: list[dict]) -> int:
    valid = [
        p["values"] for p in payloads
        if not p["values"].get("ErrorCode") and p["values"].get("PlotID") is not None
    ]
    if not valid:
        return 0
    sql = (
        "INSERT INTO dbo.PlotInDetails ("
        "PlotID, ContainerId, PlotInDate, PlotInStatus, CreatedBy, Remarks, BookingId, EditedBy)"
    )
    params = [
        (v.get("PlotID"), v.get("ContainerId"), v.get("PlotInDate"),
         v.get("PlotInStatus"), 1, v.get("Remarks"), v.get("BookingId"), 1)
        for v in valid
    ]
    return _insert_rows(sql, params, _WRITE_DATABASE)


def insert_gate_out_records(payloads: list[dict]) -> int:
    valid = [
        p["values"] for p in payloads
        if not p["values"].get("ErrorCode") and p["values"].get("PlotId") is not None
    ]
    if not valid:
        return 0
    sql = (
        "INSERT INTO dbo.PlotOutDetails ("
        "BookingId, ContainerId, SealNo, Transporter, VehicleNo, "
        "PlotOutDate, PlotOutTime, Remarks, CreatedBy, PlotOutStatus, PlotId, EditedBy)"
    )
    params = [
        (v.get("BookingId"), v.get("ContainerId"), v.get("SealNo"),
         v.get("Transporter"), v.get("VehicleNo"), v.get("PlotOutDate"),
         v.get("PlotOutTime"), v.get("Remarks"), 1, v.get("PlotOutStatus"),
         v.get("PlotId"), 1)
        for v in valid
    ]
    return _insert_rows(sql, params, _WRITE_DATABASE)


def insert_gate_error_records(payloads: list[dict]) -> int:
    valid = [p["values"] for p in payloads if p.get("values")]
    if not valid:
        return 0
    sql = (
        "INSERT INTO dbo.DepotMovementError ("
        "GateType, ErrorCode, ContainerId, PlotID, PlotInID, PlotOutId, "
        "BookingId, PlotInDate, PlotOutDate, PlotOutTime, PlotInStatus, "
        "PlotOutStatus, OutBookingID, CreatedBy, Remarks, SealNo, "
        "Transporter, VehicleNo, ContType, ContainerStatusId)"
    )
    params = [
        (v.get("GateType"), v.get("ErrorCode"), v.get("ContainerId"),
         v.get("PlotID") or v.get("PlotId"), v.get("PlotInID"), v.get("PlotOutId"),
         v.get("BookingId"), v.get("PlotInDate"), v.get("PlotOutDate"),
         v.get("PlotOutTime"), v.get("PlotInStatus"), v.get("PlotOutStatus"),
         v.get("OutBookingID"), v.get("CreatedBy"), v.get("Remarks"),
         v.get("SealNo"), v.get("Transporter"), v.get("VehicleNo"),
         v.get("ContType"), v.get("ContainerStatusId"))
        for v in valid
    ]
    return _insert_rows(sql, params, _WRITE_DATABASE)


# ---------- Container lookups (read database) ----------

def get_container_status_ids(container_nos: Iterable[str]) -> dict[str, int | None]:
    info = get_container_info(container_nos)
    return {cid: (v[0] if v else None) for cid, v in info.items()}


def get_container_info(container_nos: Iterable[str]) -> dict[str, tuple[int | None, int | None, str] | None]:
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, tuple[int | None, int | None, str] | None] = {cid: None for cid in ids}
    if not ids:
        return result

    raw: dict[str, tuple[int | None, int | None]] = {}
    plot_ids: set[int] = set()
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerNo')}, {_col('ContainerStatusId')}, {_col('LocationPlotId')} "
            f"FROM ContainerEntry WHERE ContainerNo IN ({_in_list(chunk)});"
        )
        for container_no, status_id, location_plot_id in _query_rows(sql):
            key = str(container_no).strip().upper().replace(" ", "")
            sid_raw = int(status_id) if status_id is not None else None
            sid = sid_raw if sid_raw in RELEVANT_STATUS_IDS else None
            pid = int(location_plot_id) if location_plot_id is not None else None
            raw[key] = (sid, pid)
            if pid is not None:
                plot_ids.add(pid)

    plot_name_by_id: dict[int, str] = {}
    plot_ids_list = sorted(plot_ids)
    for i in range(0, len(plot_ids_list), _CHUNK):
        chunk = plot_ids_list[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('PlotID')}, {_col('PlotName')} FROM PlotInformationDetails "
            f"WHERE PlotID IN ({_in_list(chunk)});"
        )
        for pid, pname in _query_rows(sql):
            plot_name_by_id[int(pid)] = str(pname).strip() if pname is not None else ""

    for cid, (sid, pid) in raw.items():
        result[cid] = (sid, pid, plot_name_by_id.get(pid, "") if pid is not None else "")
    return result


def get_container_ids(container_nos: Iterable[str]) -> dict[str, int | None]:
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerNo')}, {_col('ContainerId')} FROM ContainerEntry "
            f"WHERE ContainerNo IN ({_in_list(chunk)});"
        )
        for container_no, container_id in _query_rows(sql):
            key = str(container_no).strip().upper().replace(" ", "")
            result[key] = int(container_id) if container_id is not None else None
    return result


def get_container_types(container_nos: Iterable[str]) -> dict[str, str | None]:
    ids = sorted({str(c).strip().upper().replace(" ", "") for c in container_nos if c})
    result: dict[str, str | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerNo')}, {_col('ContainerType')} FROM ContainerEntry "
            f"WHERE ContainerNo IN ({_in_list(chunk)});"
        )
        for container_no, container_type in _query_rows(sql):
            key = str(container_no).strip().upper().replace(" ", "")
            result[key] = str(container_type).strip() if container_type is not None else None
    return result


def container_ids_exist(container_ids: Iterable[int]) -> dict[int, bool]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, bool] = {cid: False for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('ContainerId')} FROM icms.dbo.ContainerEntry "
            f"WHERE ContainerId IN ({_in_list(chunk)});"
        )
        for (container_id,) in _query_rows(sql):
            result[int(container_id)] = True
    return result


# ---------- Booking lookups ----------

_BOOKED_QTY_PART = re.compile(r"(\d+)\s*X\s*(.+)")


def booking_ids_exist(booking_ids: Iterable[int]) -> dict[int, bool]:
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, bool] = {bid: False for bid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingId')} FROM icms.dbo.BookingDetails "
            f"WHERE BookingId IN ({_in_list(chunk)});"
        )
        for (booking_id,) in _query_rows(sql):
            result[int(booking_id)] = True
    return result


def get_booked_qty_by_booking_id(booking_ids: Iterable[int]) -> dict[int, int]:
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, int] = {bid: 0 for bid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingId')}, {_col('BookedContainerQty')} FROM BookingDetails "
            f"WHERE BookingId IN ({_in_list(chunk)});"
        )
        for booking_id, qty_str in _query_rows(sql):
            total = 0
            if qty_str:
                for part in str(qty_str).split(","):
                    m = _BOOKED_QTY_PART.match(part.strip())
                    if m:
                        total += int(m.group(1))
            result[int(booking_id)] = total
    return result


def get_plotout_container_counts(booking_ids: Iterable[int]) -> dict[int, int]:
    ids = sorted({int(bid) for bid in booking_ids if bid is not None})
    result: dict[int, int] = {bid: 0 for bid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingId')}, {_col('COUNT(ContainerId)')} FROM PlotOutDetails "
            f"WHERE BookingId IN ({_in_list(chunk)}) GROUP BY BookingId;"
        )
        for booking_id, cnt in _query_rows(sql):
            result[int(booking_id)] = int(cnt)
    return result


def _booking_lookup_candidates(value: str) -> list[str]:
    ref = str(value).strip()
    candidates = [ref]
    stripped = re.sub(r"[A-Za-z]+$", "", ref).strip()
    if stripped and stripped != ref:
        candidates.append(stripped)
    return candidates


def get_booking_ids_by_reference(booking_refs: Iterable[str]) -> dict[str, int | None]:
    """Numeric values are already BookingId. Non-numeric values match
    BookingDetails.BookingNo (also trying a trailing-letter-stripped variant)."""
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
    for i in range(0, len(names), _CHUNK):
        chunk = names[i:i + _CHUNK]
        sql = (
            f"SELECT {_col('BookingNo')}, {_col('BookingId')} FROM BookingDetails "
            f"WHERE BookingNo IN ({_in_list(chunk)});"
        )
        for booking_no, booking_id in _query_rows(sql):
            booking_by_no[str(booking_no).strip()] = int(booking_id)

    for ref in refs:
        if result[ref] is not None:
            continue
        for candidate in _booking_lookup_candidates(ref):
            if candidate in booking_by_no:
                result[ref] = booking_by_no[candidate]
                break
    return result


# ---------- Latest movement ids & previous booking ----------

def get_previous_gate_out_booking_ids(container_ids: Iterable[int]) -> dict[int, int | None]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = f"""
            WITH latest AS (
                SELECT ContainerId, BookingId,
                       ROW_NUMBER() OVER (
                           PARTITION BY ContainerId
                           ORDER BY PlotOutDate DESC, PlotOutId DESC
                       ) AS rn
                FROM PlotOutDetails
                WHERE ContainerId IN ({_in_list(chunk)})
            )
            SELECT {_col('ContainerId')}, {_col('BookingId')} FROM latest WHERE rn = 1;
        """
        for container_id, booking_id in _query_rows(sql):
            result[int(container_id)] = int(booking_id) if booking_id is not None else None
    return result


def get_latest_plot_in_ids_by_status(container_ids: Iterable[int], plot_in_status: str = "P") -> dict[int, int | None]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = f"""
            WITH latest AS (
                SELECT PlotInID, ContainerId,
                       ROW_NUMBER() OVER (
                           PARTITION BY ContainerId
                           ORDER BY PlotInDate DESC, PlotInID DESC
                       ) AS rn
                FROM PlotInDetails
                WHERE PlotInStatus = {_lit(plot_in_status)}
                  AND ContainerId IN ({_in_list(chunk)})
            )
            SELECT {_col('ContainerId')}, {_col('PlotInID')} FROM latest WHERE rn = 1;
        """
        for container_id, plot_in_id in _query_rows(sql):
            result[int(container_id)] = int(plot_in_id) if plot_in_id is not None else None
    return result


def get_latest_plot_out_ids_by_status(container_ids: Iterable[int], plot_out_status: str = "P") -> dict[int, int | None]:
    ids = sorted({int(cid) for cid in container_ids if cid is not None})
    result: dict[int, int | None] = {cid: None for cid in ids}
    if not ids:
        return result
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        sql = f"""
            WITH latest AS (
                SELECT PlotOutId, ContainerId,
                       ROW_NUMBER() OVER (
                           PARTITION BY ContainerId
                           ORDER BY PlotOutDate DESC, PlotOutId DESC
                       ) AS rn
                FROM PlotOutDetails
                WHERE PlotOutStatus = {_lit(plot_out_status)}
                  AND ContainerId IN ({_in_list(chunk)})
            )
            SELECT {_col('ContainerId')}, {_col('PlotOutId')} FROM latest WHERE rn = 1;
        """
        for container_id, plot_out_id in _query_rows(sql):
            result[int(container_id)] = int(plot_out_id) if plot_out_id is not None else None
    return result


# ---------- Duplicate existence checks ----------

def plotin_records_exist(items: Iterable[tuple[int, str]]) -> set[tuple[int, str]]:
    """Subset of (ContainerId, PlotInDate) already present (PlotInDate as DATE)."""
    pairs = {(int(c), str(d).strip()) for c, d in items if c is not None and d}
    found: set[tuple[int, str]] = set()
    if not pairs:
        return found
    for cid, pdate in pairs:
        sql = (
            f"SELECT {_col('COUNT(*)')} FROM dbo.PlotInDetails "
            f"WHERE ContainerId = {_lit(cid)} AND CAST(PlotInDate AS DATE) = {_lit(pdate)};"
        )
        rows = _query_rows(sql)
        if rows and rows[0][0] is not None and int(rows[0][0]) > 0:
            found.add((cid, pdate))
    return found


def plotout_records_exist(items: Iterable[tuple[int, str, int]]) -> set[tuple[int, str, int]]:
    """Subset of (ContainerId, PlotOutDate, BookingId) already present."""
    triples = {
        (int(c), str(d).strip(), int(b))
        for c, d, b in items
        if c is not None and d and b is not None
    }
    found: set[tuple[int, str, int]] = set()
    if not triples:
        return found
    for cid, pdate, bid in triples:
        sql = (
            f"SELECT {_col('COUNT(*)')} FROM dbo.PlotOutDetails "
            f"WHERE ContainerId = {_lit(cid)} AND CAST(PlotOutDate AS DATE) = {_lit(pdate)} "
            f"AND BookingId = {_lit(bid)};"
        )
        rows = _query_rows(sql)
        if rows and rows[0][0] is not None and int(rows[0][0]) > 0:
            found.add((cid, pdate, bid))
    return found
