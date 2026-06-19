from depot.errors import ErrorCode
from depot.extract.gate_in import extract_gate_in
from depot.extract.gate_out import extract_gate_out
from depot.models import ExtractedTable, RawRow
from depot.regions.detector import detect_region


def _table(header, rows):
    return ExtractedTable(sheet="S", title="t", header=header,
                          rows=[RawRow(source_row=i, cells=r) for i, r in enumerate(rows)])


def test_gate_in_first_date_time_and_skip_no_container():
    reg = detect_region("GATE IN")
    t = _table(["Container", "Date", "Time", "Remark"], [
        ["TCNU1234567", "2026-06-18", "09:30", "ok"],
        ["no container here", "x", "y", "z"],
    ])
    recs = extract_gate_in(t, reg)
    assert len(recs) == 1
    assert recs[0].container_no == "TCNU1234567"
    assert recs[0].date == "2026-06-18"
    assert recs[0].remark == "ok"


def test_gate_out_booking_and_no_booking_error():
    reg = detect_region("GATE IN")  # india
    t = _table(["Container", "Booking", "Seal", "Date", "Time"], [
        ["TCNU1234567", "ABC/DEF/123456", "S1", "2026-06-18", "14:30"],
        ["MEDU7654321", "123456", "S2", "2026-06-18", "15:00"],
    ])
    recs = extract_gate_out(t, reg)
    assert recs[0].booking_id == "ABC/DEF/123456"
    assert recs[0].error_code == ""
    # weak booking rejected by india -> NO_BOOKING_ID
    assert recs[1].error_code == ErrorCode.NO_BOOKING_ID.value


def test_gate_out_last_date_time():
    reg = detect_region("GATE IN")
    t = _table(["Container", "Date1", "Date2", "Time1", "Time2"], [
        ["TCNU1234567 2026-06-17 2026-06-18 09:00 14:30"],
    ])
    recs = extract_gate_out(t, reg)
    assert recs[0].plot_out_date == "2026-06-18"
    assert recs[0].plot_out_time == "14:30"
