from datetime import date, datetime

from depot.normalize import fields
from depot.regions.detector import detect_region


def test_normalize_container():
    assert fields.normalize_container("tcnu 123 4567") == "TCNU1234567"


def test_normalize_date_variants():
    assert fields.normalize_date(datetime(2026, 6, 18)) == "2026-06-18"
    assert fields.normalize_date(date(2026, 6, 18)) == "2026-06-18"
    assert fields.normalize_date("18/06/2026") == "2026-06-18"
    assert fields.normalize_date("18 Jun 2026") == "2026-06-18"


def test_normalize_time():
    assert fields.normalize_time(datetime(2026, 6, 18, 9, 30)) == "09:30:00.000"
    reg = detect_region("GATE IN")
    assert fields.normalize_time("9:30 AM", reg) == "09:30:00.000"
    assert fields.normalize_time("14:30", reg) == "14:30:00.000"


def test_normalize_empty():
    assert fields.normalize_empty(None) == ""
    assert fields.normalize_empty("  x ") == "x"
