from depot.models import Direction
from depot.regions.detector import detect_region
from depot.regions.loader import get_region_profiles


def test_profiles_loaded():
    assert set(get_region_profiles()) == {"india", "china"}


def test_detect_region_by_cjk():
    assert detect_region("GATE IN").name == "india"
    assert detect_region("进场").name == "china"


def test_container_uppercased():
    ind = detect_region("GATE IN")
    assert ind.find_container("x tcnu1234567 y") == "TCNU1234567"


def test_india_rejects_weak_booking_china_accepts():
    ind = detect_region("GATE IN")
    chn = detect_region("进场")
    assert ind.find_booking("123456") is None
    assert ind.find_booking("ABC/DEF/123456") == "ABC/DEF/123456"
    assert chn.find_booking("123456") == "123456"


def test_direction():
    ind = detect_region("GATE IN")
    assert ind.detect_direction("GATE IN") == Direction.IN
    assert ind.detect_direction("GATE OUT") == Direction.OUT
    assert ind.detect_direction("GATE IN GATE OUT") == Direction.UNRESOLVED
