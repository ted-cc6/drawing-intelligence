import json

import pytest

from drawing_intelligence.extraction import EXTRACTION_FILE, ImagingConfig, extract_pdf, load_template
from drawing_intelligence.extraction.geometry import nominal_value
from drawing_intelligence.extraction.imaging import tile_boxes
from drawing_intelligence.schemas import Extraction
from tests.conftest import A2


def _texts(items):
    return [i.text for i in items]


def test_sample_sheet(make_pdf):
    ex = extract_pdf(make_pdf())
    assert ex.n_pages == 1 and not ex.warnings
    p = ex.pages[0]
    dims = _texts(p.dimensions)
    assert {"135", "130", "(135)", "400", "11 (-0.1/-0.2)"} <= set(dims)
    assert [d.id for d in p.dimensions] == [f"D{i}" for i in range(1, len(dims) + 1)]
    assert next(d for d in p.dimensions if d.text == "(135)").is_reference
    assert _texts(p.view_labels) == ["SECTION A-A"]
    assert _texts(p.notes) == ["2. DO NOT SCALE DRAWING"]
    assert "P24TEST000001" in _texts(p.title_block_text)
    assert "6 UP TO 30" in _texts(p.tolerance_table_text)
    # template regions keep title-block text out of the dimensions
    assert not any("P24TEST" in t for t in dims)


def test_chain_sum_consistent(make_pdf):
    (check,) = extract_pdf(make_pdf()).pages[0].chain_checks
    assert check.chain_texts == ["135", "130", "(135)"]
    assert check.chain_sum == 400 and check.match


def test_chain_sum_mismatch_uses_absolute_tolerance(make_pdf):
    # 400.1 vs a chain of 400: the old 2 % rule passed this, the strict 0.05 mm rule must not
    (check,) = extract_pdf(make_pdf(overall="400.1")).pages[0].chain_checks
    assert not check.match and check.diff == pytest.approx(0.1)


def test_matched_lines_point_at_dimension_ids(make_pdf):
    p = extract_pdf(make_pdf()).pages[0]
    ids = {d.id for d in p.dimensions}
    assert p.matched_lines and all(m.dimension_id in ids for m in p.matched_lines)
    assert p.scale_pts_per_mm is not None


def test_every_page_is_extracted(make_pdf):
    ex = extract_pdf(make_pdf(pages=2))
    assert [p.page_number for p in ex.pages] == [1, 2]
    assert all(p.dimensions for p in ex.pages)


def test_bigger_sheet_same_template(make_pdf):
    # regions are anchored to the sheet edges, so an A2 sheet still finds its title block
    p = extract_pdf(make_pdf(size=A2)).pages[0]
    assert "P24TEST000001" in _texts(p.title_block_text)
    assert any("differs from the template" in w for w in p.warnings)


def test_writes_images_and_json(make_pdf, tmp_path):
    out = tmp_path / "out"
    ex = extract_pdf(make_pdf(), out_dir=out, imaging=ImagingConfig(dpi=72, grid_rows=1, grid_cols=2))
    img = ex.pages[0].images
    assert img is not None and len(img.tiles) == 2 and img.title_block
    for f in [img.full, img.title_block, *(t.file for t in img.tiles)]:
        assert (out / f).exists()
    saved = Extraction.model_validate(json.loads((out / EXTRACTION_FILE).read_text(encoding="utf-8")))
    assert saved == ex


def test_tiles_overlap_and_cover_the_page():
    boxes = [b for _, b in tile_boxes(300, 200, ImagingConfig(grid_rows=2, grid_cols=3, overlap=0.1))]
    assert boxes[0][:2] == (0, 0) and boxes[-1][2:] == (300, 200)
    assert boxes[1][0] < boxes[0][2]  # neighbours overlap


@pytest.mark.parametrize(
    ("text", "value"),
    [("40±0.1", 40.0), ("(35)", 35.0), ("R5", 5.0), ("⌀12,5", 12.5), ("4 x 90°", None), ("H7", None)],
)
def test_nominal_value(text, value):
    assert nominal_value(text) == value


def test_template_coordinates():
    t = load_template()
    tb = t.regions_for(1191, 842)["title_block"]
    assert tb == (1191 - 508, 842 - 197, 1191, 842)
