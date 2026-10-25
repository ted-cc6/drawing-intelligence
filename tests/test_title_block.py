"""Stage 1 title-block fields, read by position from the template's cells (synthetic sheets)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from drawing_intelligence.extraction import extract_pdf, load_template
from drawing_intelligence.extraction.template import resolve_rect

A3 = (1191, 842)


def draw_title_block(
    page: pymupdf.Page,
    values: dict[str, str],
    *,
    anchors: bool = True,
    extra_text: list[tuple[str, tuple[float, float]]] | None = None,
) -> None:
    """Template labels at their anchors, and each value inside its cell, like a real PARI sheet."""
    t = load_template()
    w, h = page.rect.width, page.rect.height
    if anchors:
        for text, x, y in t.anchors_for(w, h):
            page.insert_text((x, y + 7), text, fontsize=6)
    cells = t.field_cells(w, h)
    for field, value in values.items():
        x0, y0, _, y1 = cells[field]
        page.insert_text((x0 + 2, (y0 + y1) / 2 + 2.5), value, fontsize=6)
    for text, pos in extra_text or []:
        page.insert_text(pos, text, fontsize=8)


@pytest.fixture
def sheet(tmp_path: Path):
    def _make(values: dict[str, str], size: tuple[int, int] = A3, **kwargs) -> Path:
        doc = pymupdf.open()
        draw_title_block(doc.new_page(width=size[0], height=size[1]), values, **kwargs)
        path = tmp_path / "tb.pdf"
        doc.save(path)
        doc.close()
        return path

    return _make


VALUES = {
    "number": "P24TEST000001",
    "material": "M.S.",
    "surface_treatment": "I.Z.B.P. (TRIVALENT)",
    "revision": "00",
    "scale": "1 : 1",
    "drawn_date": "01/10/2025",
    "checked_date": "02/10/2025",
    "approved_date": "03/10/2025",
    "general_tolerance_standard": "Gen Tol.: IS 2102",
}


def test_fields_are_read_from_their_cells(sheet):
    page = extract_pdf(sheet(VALUES)).pages[0]
    assert page.title_block_layout == "standard"
    got = {k: v.value for k, v in page.title_block_fields.items()}
    for field, value in VALUES.items():
        expected = "IS 2102" if field == "general_tolerance_standard" else value  # printed prefix stripped
        assert got[field] == expected, field


def test_neighbouring_cells_stay_apart(sheet):
    # The checked and approved dates sit side by side; the PDF may join them into one line, never one field.
    page = extract_pdf(sheet(VALUES)).pages[0]
    assert page.title_block_fields["checked_date"].value == "02/10/2025"
    assert page.title_block_fields["approved_date"].value == "03/10/2025"


def test_empty_cell_is_none_with_the_cells_bbox(sheet):
    values = {k: v for k, v in VALUES.items() if k != "material"}
    page = extract_pdf(sheet(values)).pages[0]
    field = page.title_block_fields["material"]
    assert field.value is None
    cell = resolve_rect(load_template().title_block_fields["material"], *A3)
    assert field.bbox == pytest.approx(cell, abs=0.1)


def test_cells_follow_the_sheet_edges_on_a_bigger_sheet(sheet):
    page = extract_pdf(sheet(VALUES, size=(1684, 1191))).pages[0]
    assert page.title_block_fields["number"].value == "P24TEST000001"


def test_variant_title_block_reads_no_fields(sheet):
    page = extract_pdf(sheet(VALUES, anchors=False)).pages[0]
    assert page.title_block_layout == "variant"
    assert page.title_block_fields == {}
    assert any("variant title block" in w for w in page.warnings)


def test_units_come_from_the_unit_statement(sheet):
    page = extract_pdf(sheet(VALUES, extra_text=[("ALL DIMENSIONS ARE IN mm", (100, 700))])).pages[0]
    assert page.title_block_fields["units"].value == "mm"


def test_revision_table_rows_and_numbers(sheet):
    w, h = A3
    rows = [
        (".", (w - 540, h - 200)),
        ("1", (w - 545, h - 196)),
        ("MATERIAL CHANGE", (w - 500, h - 196)),
        ("2", (w - 545, h - 205)),
    ]
    page = extract_pdf(sheet(VALUES, extra_text=rows)).pages[0]
    assert sorted(r.text for r in page.revision_numbers) == ["1", "2"]
    assert "." not in [r.text for r in page.revision_rows]  # placeholder dots are not rows
    assert "MATERIAL CHANGE" in [r.text for r in page.revision_rows]


def test_chain_checks_carry_dimension_ids(make_pdf):
    page = extract_pdf(make_pdf()).pages[0]
    chain = page.chain_checks[0]
    ids = {d.text: d.id for d in page.dimensions}
    assert chain.overall_id == ids["400"]
    assert len(chain.chain_ids) == len(chain.chain_texts) == 3


# --- general tolerance table and stacked limits (stage 1) -------------------------------------------------


def test_general_tolerance_table_rows_by_section(tmp_path: Path):
    doc = pymupdf.open()
    page = doc.new_page(width=A3[0], height=A3[1])
    x = A3[0] - 110
    for text, y, dx in [
        ("UNSPECIFIED TOL.(M/C)", 500, 0),
        ("FOR LINEAR IN mm.", 508, 0),
        ("6 UP TO 30", 520, 0),
        ("±0.2", 520, 60),
        ("30 UP TO 120", 532, 0),
        ("±0.3", 532, 60),
        ("OVER 2000", 544, 0),
        ("±2", 544, 60),
    ]:
        page.insert_text((x + dx, y), text, fontsize=5)
    path = tmp_path / "tol.pdf"
    doc.save(path)
    rows = extract_pdf(path).pages[0].general_tolerances
    assert [(r.process, r.kind, r.over, r.up_to, r.value_mm) for r in rows] == [
        ("machining", "linear", 6.0, 30.0, 0.2),
        ("machining", "linear", 30.0, 120.0, 0.3),
        ("machining", "linear", 2000.0, None, 2.0),
    ]


def _stacked(tmp_path: Path, rotate: int, upper: str, lower: str, lower_first: bool = False):
    """A nominal 11 with its limits printed in place; `lower_first` writes the lower one first into the PDF.

    `rotate` 0: horizontal, the upper limit on top. 90: reading upwards, the nominal below and the upper limit
    in the left column (the text's "up").
    """
    doc = pymupdf.open()
    page = doc.new_page(width=A3[0], height=A3[1])
    if rotate == 0:
        page.insert_text((500, 500), "11", fontsize=10)
        slots = [(upper, (516, 494)), (lower, (516, 502))]
    else:
        page.insert_text((500, 500), "11", fontsize=10, rotate=90)
        slots = [(upper, (494, 484)), (lower, (502, 484))]
    for text, pos in reversed(slots) if lower_first else slots:
        page.insert_text(pos, text, fontsize=6, rotate=rotate)
    path = tmp_path / f"stacked_{rotate}_{lower_first}.pdf"
    doc.save(path)
    return [d for d in extract_pdf(path).pages[0].dimensions if d.limits]


@pytest.mark.parametrize("rotate", [0, 90])
@pytest.mark.parametrize("lower_first", [False, True])
def test_stacked_limits_are_ordered_by_position_not_pdf_order(tmp_path: Path, rotate: int, lower_first: bool):
    (dim,) = _stacked(tmp_path, rotate, "-0.1", "-0.2", lower_first)
    assert dim.limits == ("-0.1", "-0.2")


def test_another_dimensions_value_is_not_a_limit(tmp_path: Path):
    dims = _stacked(tmp_path, 0, "+0.2", "16.5")  # 16.5 is a size, not a limit
    assert dims == []


def test_a_marked_cell_takes_its_value_from_the_notes(sheet):
    values = {**VALUES, "material": "#", "surface_treatment": "#"}
    notes = [
        ("# MATERIAL: EN8", (100, 650)),
        ("# FINISH: I.Z.B.P. (TRIVALENT)", (100, 662)),
        ("# MATÉRIEL : EN8", (100, 674)),  # the French copy is not read
    ]
    fields = extract_pdf(sheet(values, extra_text=notes)).pages[0].title_block_fields
    assert (fields["material"].value, fields["material"].source) == ("EN8", "notes")
    assert fields["surface_treatment"].value == "I.Z.B.P. (TRIVALENT)"
    assert fields["number"].source == "cell"


def test_a_marked_cell_with_no_note_stays_as_printed(sheet):
    fields = extract_pdf(sheet({**VALUES, "material": "#"})).pages[0].title_block_fields
    assert (fields["material"].value, fields["material"].source) == ("#", "cell")
