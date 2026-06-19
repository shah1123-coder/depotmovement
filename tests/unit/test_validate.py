import depot.db.lookups as lookups
import depot.validate.booking as booking
from depot.db.batcher import LookupCache
from depot.errors import ErrorCode
from depot.models import GateInRecord, GateOutRecord
from depot.validate.gate_in import validate_gate_in
from depot.validate.gate_out import validate_gate_out


def _cache():
    c = LookupCache()
    c.container_ids = {"TCNU1234567": 11}
    c.container_info = {"TCNU1234567": {"status_id": 2, "plot_id": 5, "plot_name": "P"}}
    c.container_types = {"TCNU1234567": "20GP"}
    c.booking_ids = {"ABC/DEF/123456": 99}
    c.booked_qty = {99: 5}
    c.plotted_counts = {99: 0}
    return c


def test_gate_in_no_container(monkeypatch):
    monkeypatch.setattr(lookups, "check_in_duplicate", lambda *a: False)
    recs = [GateInRecord(container_no="ZZZU0000000", date="2026-06-18")]
    out = validate_gate_in(recs, _cache(), plot_id=5)
    assert out[0].ErrorCode == ErrorCode.NO_CONTAINER_ID.value


def test_gate_in_duplicate_priority(monkeypatch):
    monkeypatch.setattr(lookups, "check_in_duplicate", lambda *a: True)
    recs = [GateInRecord(container_no="TCNU1234567", date="2026-06-18")]
    out = validate_gate_in(recs, _cache(), plot_id=5)
    assert out[0].ErrorCode == ErrorCode.DUPLICATE_RECORD.value


def test_gate_in_invalid_status(monkeypatch):
    monkeypatch.setattr(lookups, "check_in_duplicate", lambda *a: False)
    c = _cache()
    c.container_info["TCNU1234567"]["status_id"] = 3  # not in {2,7}
    recs = [GateInRecord(container_no="TCNU1234567", date="2026-06-18")]
    out = validate_gate_in(recs, c, plot_id=5)
    assert out[0].ErrorCode == ErrorCode.INVALID_CONTAINER_STATUS_ID.value


def test_gate_in_clean(monkeypatch):
    monkeypatch.setattr(lookups, "check_in_duplicate", lambda *a: False)
    recs = [GateInRecord(container_no="TCNU1234567", date="2026-06-18")]
    out = validate_gate_in(recs, _cache(), plot_id=5)
    assert out[0].ErrorCode is None
    assert out[0].ContainerId == 11


def test_gate_out_preserves_no_booking(monkeypatch):
    monkeypatch.setattr(lookups, "check_out_duplicate", lambda *a: False)
    monkeypatch.setattr(booking, "ecp_exceeds", lambda *a: False)
    recs = [GateOutRecord(container_id="TCNU1234567", booking_id="",
                          plot_out_date="2026-06-18", error_code=ErrorCode.NO_BOOKING_ID.value)]
    out = validate_gate_out(recs, _cache(), plot_id=5)
    assert out[0].ErrorCode == ErrorCode.NO_BOOKING_ID.value


def test_gate_out_invalid_ecp(monkeypatch):
    monkeypatch.setattr(lookups, "check_out_duplicate", lambda *a: False)
    monkeypatch.setattr(booking, "ecp_exceeds", lambda *a: True)
    recs = [GateOutRecord(container_id="TCNU1234567", booking_id="ABC/DEF/123456",
                          plot_out_date="2026-06-18")]
    out = validate_gate_out(recs, _cache(), plot_id=5)
    assert out[0].ErrorCode == ErrorCode.INVALID_ECP_COUNT.value


def test_gate_out_clean(monkeypatch):
    monkeypatch.setattr(lookups, "check_out_duplicate", lambda *a: False)
    monkeypatch.setattr(booking, "ecp_exceeds", lambda *a: False)
    recs = [GateOutRecord(container_id="TCNU1234567", booking_id="ABC/DEF/123456",
                          plot_out_date="2026-06-18", plot_out_time="14:30")]
    out = validate_gate_out(recs, _cache(), plot_id=5)
    assert out[0].ErrorCode is None
    assert out[0].BookingId == 99
    assert out[0].ContType == "20GP"
