from depot.detect.boundaries import find_boundary
from depot.detect.headers import detect_headers, is_plain_text
from depot.detect.titles import attach_titles
from depot.models import LogicalCell
from depot.workbook.grid import build_logical_rows


class FakeView:
    def __init__(self, title, cells, merged=None):
        self.title = title
        self._cells = cells  # {(r,c): value}
        self.max_row = max((r for r, _ in cells), default=0)
        self.max_col = max((c for _, c in cells), default=0)
        self._merged = merged or []

    def cell(self, r, c):
        return self._cells.get((r, c))

    def merged_ranges(self):
        return self._merged


def test_formula_cells_excluded_from_headers():
    cell = LogicalCell(row=1, end_row=1, start_col=1, end_col=1, value="=SUM(A1)")
    assert not is_plain_text(cell)
    assert is_plain_text(LogicalCell(row=1, end_row=1, start_col=1, end_col=1, value="Name"))


def test_merged_cell_flattening():
    view = FakeView("S", {(1, 1): "Merged", (1, 3): "C"}, merged=[(1, 1, 1, 2)])
    rows = build_logical_rows(view)
    first = rows[0]
    assert first[0].start_col == 1 and first[0].end_col == 2
    assert first[0].is_horizontal_merge is True
    assert first[1].start_col == 3


def test_header_and_boundary():
    cells = {
        (1, 1): "Container", (1, 2): "Date", (1, 3): "Remark",
        (2, 1): "TCNU1234567", (2, 2): "2026-06-18", (2, 3): "ok",
        (3, 1): "MEDU7654321", (3, 2): "2026-06-18", (3, 3): "fine",
    }
    view = FakeView("GATE IN", cells)
    rows = build_logical_rows(view)
    headers = detect_headers("GATE IN", rows)
    assert len(headers) == 1
    assert headers[0].row == 1
    region = find_boundary(headers[0], rows)
    assert region.data_start_row == 2
    assert region.data_end_row == 3


def test_title_attached_above_header():
    cells = {
        (1, 1): "Daily Report",
        (2, 1): "Container", (2, 2): "Date", (2, 3): "Remark",
        (3, 1): "TCNU1234567", (3, 2): "2026-06-18", (3, 3): "ok",
    }
    view = FakeView("S", cells)
    rows = build_logical_rows(view)
    headers = attach_titles(detect_headers("S", rows), rows)
    assert headers[0].title == "Daily Report"
