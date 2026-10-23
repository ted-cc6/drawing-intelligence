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
