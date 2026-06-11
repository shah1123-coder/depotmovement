#!/usr/bin/env python3
"""Build and publish gate-movement JSON payloads from extracted records."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pyodbc


DEPOT_REPORT_CODE = Path(__file__).resolve().parents[2] / "depot report" / "code"
sys.path.insert(0, str(DEPOT_REPORT_CODE))

from db.icms_client import (  # noqa: E402
    get_booking_ids_by_reference,
    get_container_ids,
    get_container_status_ids,
    get_container_types,
    get_latest_plot_in_ids_by_status,
    get_latest_plot_out_ids_by_status,
    get_previous_gate_out_booking_ids,
    insert_gate_error_records,
    insert_gate_in_records,
    insert_gate_out_records,
)


CSV_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = CSV_ROOT / "results"
GATE_IN_JSON = RESULTS_DIR / "gate_in.json"
GATE_OUT_JSON = RESULTS_DIR / "gate_out.json"
GATE_ERRORS_JSON = RESULTS_DIR / "gate_errors.json"
PROCESS_EMAIL_DATABASE = "EMail_Reader_Process_Data"


def mark_process_emails_completed(
    internet_message_ids: Iterable[str],
    completed_at: datetime,
) -> int:
    message_ids = sorted(
        {str(message_id).strip() for message_id in internet_message_ids if str(message_id).strip()}
    )
    if not message_ids:
        return 0

    server = os.environ.get("ICMS_SERVER", "10.10.0.72")
    user = os.environ.get("ICMS_USER", "Sa")
    password = os.environ.get("ICMS_PASSWORD", "pass@2020$")
    driver = os.environ.get("ICMS_DRIVER", "ODBC Driver 17 for SQL Server")
    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={PROCESS_EMAIL_DATABASE};"
        f"UID={user};PWD={password}"
    )
    sql = """
        UPDATE dbo.tbl_Process_Emails
        SET completed_at = ?
        WHERE internet_message_id = ?
          AND completed_at IS NULL
    """
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        updated = 0
        for message_id in message_ids:
            cursor.execute(sql, completed_at, message_id)
            updated += max(cursor.rowcount, 0)
        conn.commit()
    return updated


def _value(record: Any, name: str, default: Any = None) -> Any:
    return getattr(record, name, default)


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def plot_id_from_attachment_name(name: str) -> int | None:
    stem = Path(str(name).strip()).stem
    plot_id = stem.split("_", 1)[0].strip()
    return int(plot_id) if plot_id.isdigit() else None


def _write_json(path: Path, payloads: list[dict[str, dict[str, Any]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payloads, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _read_json(path: Path) -> list[dict[str, dict[str, Any]]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def build_gate_in_payloads(
    records_by_depot: Iterable[tuple[str, Iterable[Any]]],
) -> list[dict[str, dict[str, Any]]]:
    rows = [(depot, record) for depot, records in records_by_depot for record in records]
    container_ids = get_container_ids(_value(record, "container_no") for _depot, record in rows)
    internal_ids = [container_id for container_id in container_ids.values() if container_id is not None]
    booking_ids = get_previous_gate_out_booking_ids(internal_ids)
    plot_in_ids = get_latest_plot_in_ids_by_status(internal_ids)

    payloads: list[dict[str, dict[str, Any]]] = []
    for depot, record in rows:
        container_no = _value(record, "container_no")
        container_id = container_ids.get(container_no)
        values = {
            "PlotInID": plot_in_ids.get(container_id) if container_id else None,
            "PlotID": plot_id_from_attachment_name(depot),
            "ContainerId": container_id,
            "PlotInDate": _blank_to_none(_value(record, "date")),
            "PlotInStatus": "P",
            "CreatedBy": 1,
            "Remarks": _blank_to_none(_value(record, "remark")),
            "BookingId": booking_ids.get(container_id) if container_id else None,
            "OutBookingID": None,
            "ContainerStatusId": _blank_to_none(_value(record, "container_status")),
        }
        error_code = _blank_to_none(_value(record, "error_code"))
        if error_code:
            values["ErrorCode"] = error_code
        payloads.append({"values": values})
    return payloads


def build_gate_out_payloads(
    records_by_depot: Iterable[tuple[str, Iterable[Any]]],
) -> list[dict[str, dict[str, Any]]]:
    rows = [(depot, record) for depot, records in records_by_depot for record in records]
    container_nos = [_value(record, "container_id") for _depot, record in rows]
    container_ids = get_container_ids(container_nos)
    internal_ids = [container_id for container_id in container_ids.values() if container_id is not None]
    booking_refs = [
        _value(record, "booking_id")
        for _depot, record in rows
        if _blank_to_none(_value(record, "booking_id"))
    ]
    booking_ids = get_booking_ids_by_reference(booking_refs)
    container_types = get_container_types(container_nos)
    status_ids = get_container_status_ids(container_nos)
    plot_out_ids = get_latest_plot_out_ids_by_status(internal_ids)

    payloads: list[dict[str, dict[str, Any]]] = []
    for depot, record in rows:
        container_no = _value(record, "container_id")
        container_id = container_ids.get(container_no)
        booking_ref = _blank_to_none(_value(record, "booking_id"))
        values = {
            "PlotOutId": plot_out_ids.get(container_id) if container_id else None,
            "BookingId": booking_ref,
            "ContainerId": container_id,
            "SealNo": _blank_to_none(_value(record, "seal_no")),
            "Transporter": _blank_to_none(_value(record, "transporter")),
            "VehicleNo": _blank_to_none(_value(record, "vehicle_no")),
            "PlotOutDate": _blank_to_none(_value(record, "plot_out_date")),
            "PlotOutTime": _blank_to_none(_value(record, "plot_out_time")),
            "Remarks": _blank_to_none(_value(record, "remarks")),
            "CreatedBy": 1,
            "PlotOutStatus": "P",
            "PlotId": plot_id_from_attachment_name(depot),
            "ContType": container_types.get(container_no),
            "ContainerStatusId": status_ids.get(container_no),
        }
        error_code = _blank_to_none(_value(record, "error_code"))
        if error_code:
            values["ErrorCode"] = error_code
        payloads.append({"values": values})
    return payloads


def build_error_payloads(
    gate_in_payloads: Iterable[dict[str, dict[str, Any]]],
    gate_out_payloads: Iterable[dict[str, dict[str, Any]]],
) -> list[dict[str, dict[str, Any]]]:
    errors: list[dict[str, dict[str, Any]]] = []
    for gate_type, payloads in (("IN", gate_in_payloads), ("OUT", gate_out_payloads)):
        for payload in payloads:
            values = payload.get("values", {})
            error_codes = {
                code.strip()
                for code in str(values.get("ErrorCode") or "").split(",")
                if code.strip()
            }
            if not error_codes or "DUPLICATE_RECORD" in error_codes:
                continue
            error_values = dict(values)
            error_values["GateType"] = gate_type
            errors.append({"values": error_values})
    return errors


def refresh_error_output() -> Path:
    errors = build_error_payloads(_read_json(GATE_IN_JSON), _read_json(GATE_OUT_JSON))
    return _write_json(GATE_ERRORS_JSON, errors)


def reset_generated_payloads() -> None:
    for path in (GATE_IN_JSON, GATE_OUT_JSON, GATE_ERRORS_JSON):
        if path.exists():
            path.unlink()


def write_gate_in_payloads(
    records_by_depot: Iterable[tuple[str, Iterable[Any]]],
) -> tuple[Path, list[dict[str, dict[str, Any]]]]:
    payloads = build_gate_in_payloads(records_by_depot)
    path = _write_json(GATE_IN_JSON, payloads)
    refresh_error_output()
    return path, payloads


def write_gate_out_payloads(
    records_by_depot: Iterable[tuple[str, Iterable[Any]]],
) -> tuple[Path, list[dict[str, dict[str, Any]]]]:
    payloads = build_gate_out_payloads(records_by_depot)
    path = _write_json(GATE_OUT_JSON, payloads)
    refresh_error_output()
    return path, payloads


def insert_generated_payloads() -> dict[str, int]:
    gate_in = _read_json(GATE_IN_JSON)
    gate_out = _read_json(GATE_OUT_JSON)
    errors = build_error_payloads(gate_in, gate_out)
    _write_json(GATE_ERRORS_JSON, errors)
    return {
        "gate_in_inserted": insert_gate_in_records(gate_in),
        "gate_out_inserted": insert_gate_out_records(gate_out),
        "gate_errors_inserted": insert_gate_error_records(errors),
    }
