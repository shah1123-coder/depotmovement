"""Write the three required JSON outputs (Section 17/18). Field names are frozen
by the DB schema — do not change them."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import ErrorCode
from ..models import GateInValues, GateOutValues


def _dump(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)


def _in_values(rec: GateInValues) -> dict:
    d = {
        "PlotInID": rec.PlotInID,
        "PlotID": rec.PlotID,
        "ContainerId": rec.ContainerId,
        "PlotInDate": rec.PlotInDate,
        "PlotInStatus": "P",
        "CreatedBy": 1,
        "Remarks": rec.Remarks,
        "BookingId": rec.BookingId,
        "OutBookingID": None,
        "ContainerStatusId": rec.ContainerStatusId,
    }
    if rec.ErrorCode:
        d["ErrorCode"] = rec.ErrorCode
    return d


def _out_values(rec: GateOutValues) -> dict:
    d = {
        "PlotOutId": rec.PlotOutId,
        "BookingId": rec.BookingId,
        "ContainerId": rec.ContainerId,
        "SealNo": rec.SealNo,
        "Transporter": rec.Transporter,
        "VehicleNo": rec.VehicleNo,
        "PlotOutDate": rec.PlotOutDate,
        "PlotOutTime": rec.PlotOutTime,
        "Remarks": rec.Remarks,
        "CreatedBy": 1,
        "PlotOutStatus": "P",
        "PlotId": rec.PlotId,
        "ContType": rec.ContType,
        "ContainerStatusId": rec.ContainerStatusId,
    }
    if rec.ErrorCode:
        d["ErrorCode"] = rec.ErrorCode
    return d


def write_outputs(out_dir: Path, in_records: list[GateInValues],
                  out_records: list[GateOutValues]) -> dict[str, int]:
    out_dir = Path(out_dir)

    gate_in = [{"values": _in_values(r)} for r in in_records]
    gate_out = [{"values": _out_values(r)} for r in out_records]

    errors = []
    for r in in_records:
        if r.ErrorCode and r.ErrorCode != ErrorCode.DUPLICATE_RECORD.value:
            v = _in_values(r)
            v["GateType"] = "IN"
            errors.append({"values": v})
    for r in out_records:
        if r.ErrorCode and r.ErrorCode != ErrorCode.DUPLICATE_RECORD.value:
            v = _out_values(r)
            v["GateType"] = "OUT"
            errors.append({"values": v})

    _dump(out_dir / "gate_in.json", gate_in)
    _dump(out_dir / "gate_out.json", gate_out)
    _dump(out_dir / "gate_errors.json", errors)

    return {"in": len(gate_in), "out": len(gate_out), "errors": len(errors)}
