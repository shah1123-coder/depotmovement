import json
from pathlib import Path

import depot.db.lookups as lookups
import depot.validate.booking as booking
from depot.db.batcher import LookupCache
from depot.output import json_writer
from depot.pipeline import extract_workbook
from depot.validate.gate_in import validate_gate_in
from depot.validate.gate_out import validate_gate_out

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import build_fixtures  # noqa: E402


def _stub_cache():
    c = LookupCache()
    c.container_ids = {"TCNU1234567": 11, "MEDU7654321": 22}
    c.container_info = {
        "TCNU1234567": {"status_id": 2, "plot_id": 5, "plot_name": "P"},
        "MEDU7654321": {"status_id": 7, "plot_id": 6, "plot_name": "Q"},
    }
    c.container_types = {"TCNU1234567": "20GP", "MEDU7654321": "40HC"}
    c.booking_ids = {"ABC/DEF/123456": 99}
    c.booked_qty = {99: 5}
    c.plotted_counts = {99: 0}
    return c


def test_full_pipeline_in_and_out(tmp_path, monkeypatch):
    monkeypatch.setattr(lookups, "check_in_duplicate", lambda *a: False)
    monkeypatch.setattr(lookups, "check_out_duplicate", lambda *a: False)
    monkeypatch.setattr(booking, "ecp_exceeds", lambda *a: False)

    in_file = build_fixtures.india_gate_in()
    out_file = build_fixtures.india_gate_out()

    ex_in = extract_workbook(str(in_file), message_id="m1")
    ex_out = extract_workbook(str(out_file), message_id="m2")

    assert ex_in.region == "india"
    assert len(ex_in.in_records) == 2
    assert len(ex_out.out_records) == 1

    cache = _stub_cache()
    final_in = validate_gate_in(ex_in.in_records, cache, plot_id=5)
    final_out = validate_gate_out(ex_out.out_records, cache, plot_id=5)

    counts = json_writer.write_outputs(tmp_path, final_in, final_out)
    assert counts["in"] == 2
    assert counts["out"] == 1

    gate_in = json.loads((tmp_path / "gate_in.json").read_text(encoding="utf-8"))
    assert gate_in[0]["values"]["ContainerId"] == 11
    assert gate_in[0]["values"]["PlotInStatus"] == "P"

    gate_out = json.loads((tmp_path / "gate_out.json").read_text(encoding="utf-8"))
    assert gate_out[0]["values"]["BookingId"] == 99
    assert gate_out[0]["values"]["ContType"] == "20GP"

    errors = json.loads((tmp_path / "gate_errors.json").read_text(encoding="utf-8"))
    assert errors == []
