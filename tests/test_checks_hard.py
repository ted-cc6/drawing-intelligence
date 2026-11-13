"""The 2026-11-13 batch: the 18 rules better kept off the AI reviewers. Stage 1's graphics reader on a drawn
sheet, then one passing and one failing case per check (lighter bar, see the backlog)."""

from __future__ import annotations

from typing import Literal

import pymupdf

from drawing_intelligence.extraction import extract_pdf
from drawing_intelligence.schemas import (
    ArrowheadItem,
    CircleItem,
    DimensionGraphics,
    FieldRevisionMark,
    MatchedLine,
    PageGraphics,
    SymbolItem,
    TextLine,
)
from tests.test_checks import dim, fields, page, run
from tests.test_checks_easy import notes
from tests.test_checks_easy import notes as _notes

# --- stage 1: the graphics reader -------------------------------------------------------------------------


def _arrow(pg: pymupdf.Page, tip: tuple[float, float], direction: int) -> None:
    """A filled arrowhead 6.9 pt long, 2.3 pt wide, pointing along x (+1 right, -1 left)."""
    x, y = tip
    base = x - 6.9 * direction
    shape = pg.new_shape()
    shape.draw_polyline([(x, y), (base, y - 1.15), (base, y + 1.15), (x, y)])
    shape.finish(color=(0, 0, 0), fill=(0, 0, 0), closePath=True)
    shape.commit()


def test_graphics_reader(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=1191, height=842)
    # 40 on a dimension line with two arrowheads, 100 pt (35.3 mm) tip to tip
    pg.draw_line((200, 400), (300, 400))
    _arrow(pg, (200, 400), -1)
    _arrow(pg, (300, 400), 1)
    pg.insert_text((243, 397), "40", fontsize=9)
    # 25 on its own, nothing near it
    pg.insert_text((600, 300), "25", fontsize=9)
    # 60 on a dimension line, with a hatching line running right through it
    pg.draw_line((400, 500), (500, 500))
    _arrow(pg, (400, 500), -1)
    _arrow(pg, (500, 500), 1)
    pg.insert_text((443, 497), "60", fontsize=9)
    pg.draw_line((430, 510), (470, 480))
    path = tmp_path / "g.pdf"
    doc.save(path)
    p = extract_pdf(path).pages[0]
    assert p.graphics is not None
    assert p.graphics.arrowhead_styles == {"filled": 4}
    by_text = {d.text: g for d in p.dimensions for g in p.graphics.dimensions if g.dimension_id == d.id}
    forty = by_text["40"]
    assert forty.line is not None and forty.line_arrowheads == 2 and forty.span_pts == 100.0
    assert forty.direction == (1.0, 0.0) and not forty.crossed_by
    assert by_text["25"].line is None
    assert by_text["60"].crossed_by


# --- page builders ----------------------------------------------------------------------------------------


def graphics(*dims: DimensionGraphics, **kw) -> PageGraphics:
    return PageGraphics(dimensions=list(dims), **kw)


def g(i: int, **kw) -> DimensionGraphics:
    base = {"dimension_id": f"D{i}", "direction": (1.0, 0.0)}
    return DimensionGraphics(**{**base, **kw})


LINE = (100.0, 112.0, 200.0, 112.0)  # a horizontal dimension line under a value at (100, 100)


def on_line(i: int, **kw) -> DimensionGraphics:
    return g(i, line=LINE, arrowheads=2, line_arrowheads=2, span_pts=100.0, **kw)


def arrows(*styles: Literal["filled", "closed", "open"]) -> list[ArrowheadItem]:
    return [
        ArrowheadItem(tip=(100.0 + 10 * k, 50.0), axis=(1.0, 0.0), length=6.9, style=s)
        for k, s in enumerate(styles)
    ]


# --- CN-003, ISO-023 ----------------------------------------------------------------------------------------


def test_unattached_dimension():
    ok = page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1)))
    assert run("unattached_dimension", ok)[1].status == "pass"
    alone = page(dimensions=[dim(1, "40")], graphics=graphics(g(1)))
    assert run("unattached_dimension", alone)[1].status == "fail"
    cell = page(dimensions=[dim(1, "40")], graphics=graphics(g(1, in_table=True)))
    assert run("unattached_dimension", cell)[1].status == "not_applicable"  # a table cell is not a value
    ordinate = page(dimensions=[dim(1, "40")], graphics=graphics(g(1, ordinate=True)))
    assert run("unattached_dimension", ordinate)[1].status == "pass"
    # extracted before schema 2.3
    assert run("unattached_dimension", page(dimensions=[dim(1, "40")]))[1].status == "not_checked"


def test_dimension_line_terminations():
    params = {"terminations": ["arrowhead", "oblique_stroke", "origin_indication"]}
    ok = page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1)))
    assert run("dimension_line_terminations", ok, **params)[1].status == "pass"
    bare = page(
        dimensions=[dim(1, "40")],
        matched_lines=[MatchedLine(dimension_id="D1", line=LINE, orientation="horizontal")],
        graphics=graphics(g(1)),
    )
    findings, status = run("dimension_line_terminations", bare, **params)
    assert status.status == "fail" and "arrowhead" in findings[0].comment


# --- ISO-025 -----------------------------------------------------------------------------------------------


def test_single_arrowhead_style():
    params = {"styles": ["open", "closed", "closed_filled"], "small_space_substitutes": ["oblique_stroke"]}
    one = page(graphics=PageGraphics(arrowheads=arrows("filled", "filled"), arrowhead_styles={"filled": 2}))
    assert run("single_arrowhead_style", one, **params)[1].status == "pass"
    mixed = page(
        graphics=PageGraphics(
            arrowheads=arrows("filled", "filled", "open"), arrowhead_styles={"filled": 2, "open": 1}
        )
    )
    findings, status = run("single_arrowhead_style", mixed, **params)
    assert status.status == "fail" and "2 filled, 1 open" in findings[0].comment


# --- ISO-027, WST-050 ---------------------------------------------------------------------------------------


def test_radius_single_arrowhead():
    one = page(
        dimensions=[dim(1, "R 6")], graphics=graphics(g(1, line=LINE, arrowheads=1, line_arrowheads=1))
    )
    assert run("radius_single_arrowhead", one, arrowheads=1)[1].status == "pass"
    two = page(dimensions=[dim(1, "R 6")], graphics=graphics(on_line(1)))
    assert run("radius_single_arrowhead", two, arrowheads=1)[1].status == "fail"
    assert (
        run(
            "radius_single_arrowhead",
            page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1))),
            arrowheads=1,
        )[1].status
        == "not_applicable"
    )


def test_full_circle_by_diameter():
    arc = page(dimensions=[dim(1, "R 6")], graphics=graphics(g(1, line=LINE, line_arrowheads=1)))
    assert run("full_circle_by_diameter", arc)[1].status == "pass"
    circle = page(
        dimensions=[dim(1, "R 6")], graphics=graphics(g(1, line=LINE, line_arrowheads=1, tip_on_circle=True))
    )
    findings, status = run("full_circle_by_diameter", circle)
    assert status.status == "fail" and "Ø12" in (findings[0].recommended_correction or "")


# --- ISO-029, ISO-030, ISO-031 ------------------------------------------------------------------------------


def test_dimension_text_not_crossed():
    ok = page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1)))
    assert run("dimension_text_not_crossed", ok)[1].status == "pass"
    crossed = page(
        dimensions=[dim(1, "40")], graphics=graphics(on_line(1, crossed_by=[(90.0, 110.0, 120.0, 95.0)]))
    )
    findings, status = run("dimension_text_not_crossed", crossed)
    assert status.status == "fail" and findings[0].evidence[1].kind == "region"


VERTICAL = (150.0, 100.0, 150.0, 200.0)


def test_dimension_value_method_consistent():
    params = {"methods": ["method_1_aligned", "method_2_unidirectional"]}

    def vert(i: int, direction: tuple[float, float]) -> DimensionGraphics:
        return g(i, direction=direction, line=VERTICAL, line_arrowheads=2, span_pts=100.0)

    aligned = page(
        dimensions=[dim(1, "40"), dim(2, "50", y=300)],
        graphics=graphics(vert(1, (0.0, -1.0)), vert(2, (0.0, -1.0))),
    )
    assert run("dimension_value_method_consistent", aligned, **params)[1].status == "pass"
    mixed = page(
        dimensions=[dim(1, "40"), dim(2, "50", y=300), dim(3, "60", y=500)],
        graphics=graphics(vert(1, (0.0, -1.0)), vert(2, (0.0, -1.0)), vert(3, (1.0, 0.0))),
    )
    findings, status = run("dimension_value_method_consistent", mixed, **params)
    assert status.status == "fail" and [e.quote for e in findings[0].evidence] == ["60"]


def test_dimension_text_readable_direction():
    params = {"read_from": ["bottom", "right"], "value_method": ["method_1"]}
    up = page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1, direction=(0.0, -1.0))))
    assert run("dimension_text_readable_direction", up, **params)[1].status == "pass"
    down = page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1, direction=(0.0, 1.0))))
    findings, status = run("dimension_text_readable_direction", down, **params)
    assert status.status == "fail" and "from the left" in findings[0].comment
    angle = page(dimensions=[dim(1, "30°")], graphics=graphics(on_line(1, direction=(0.0, 1.0))))
    assert run("dimension_text_readable_direction", angle, **params)[1].status == "warning"


# --- DSM-023 ------------------------------------------------------------------------------------------------


def test_dimension_matches_scale_or_underlined():
    from drawing_intelligence.review.checks._geometry import MM_PTS

    def drawn(i: int, value: float, length_mm: float, **kw) -> DimensionGraphics:
        span = round(length_mm * MM_PTS, 1)
        y = 100.0 * i + 12  # the value (from `dim`) sits between the two tips
        return g(
            i, line=LINE, line_arrowheads=2, span_pts=span, arrow_tips=[(95.0, y), (95.0 + span, y)], **kw
        )

    dims = [dim(i, str(v), y=100.0 * i) for i, v in enumerate((10, 20, 30, 40), 1)]
    to_scale = [drawn(i, v, v) for i, v in enumerate((10, 20, 30, 40), 1)]
    assert (
        run(
            "dimension_matches_scale_or_underlined",
            page(dimensions=dims, graphics=graphics(*to_scale)),
            not_to_scale_marker="underline",
        )[1].status
        == "pass"
    )
    off = [*to_scale[:3], drawn(4, 40, 30)]  # 40 drawn 30 mm long
    findings, status = run(
        "dimension_matches_scale_or_underlined",
        page(dimensions=dims, graphics=graphics(*off)),
        not_to_scale_marker="underline",
    )
    assert status.status == "fail" and findings[0].evidence[0].quote == "40"
    marked = [*to_scale[:3], drawn(4, 40, 30, underlined=True)]
    assert (
        run(
            "dimension_matches_scale_or_underlined",
            page(dimensions=dims, graphics=graphics(*marked)),
            not_to_scale_marker="underline",
        )[1].status
        == "pass"
    )


# --- DTT-002, MX-011 ----------------------------------------------------------------------------------------


def frame(characteristic: str) -> SymbolItem:
    return SymbolItem(
        id="S1", type="gdt", text=f"{characteristic} 0.1 | A", characteristic=characteristic, tolerance="0.1",
        datums=["A"], bbox=(400.0, 400.0, 450.0, 410.0), provenance="pdf_text",
    )  # fmt: skip


def test_basic_dimension_untoleranced():
    boxed = page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1, boxed=True)))
    assert run("basic_dimension_untoleranced", boxed)[1].status == "pass"
    toleranced = page(dimensions=[dim(1, "40±0.1")], graphics=graphics(on_line(1, boxed=True)))
    assert run("basic_dimension_untoleranced", toleranced)[1].status == "fail"
    assert (
        run("basic_dimension_untoleranced", page(dimensions=[dim(1, "40")], graphics=graphics(on_line(1))))[
            1
        ].status
        == "not_applicable"
    )


def test_basic_dims_for_position():
    with_basic = page(
        dimensions=[dim(1, "40")], symbols=[frame("position")], graphics=graphics(on_line(1, boxed=True))
    )
    assert run("basic_dims_for_position", with_basic)[1].status == "pass"
    without = page(dimensions=[dim(1, "40")], symbols=[frame("position")], graphics=graphics(on_line(1)))
    assert run("basic_dims_for_position", without)[1].status == "fail"
    assert (
        run("basic_dims_for_position", page(symbols=[frame("flatness")], graphics=graphics()))[1].status
        == "not_applicable"
    )


# --- MD-013, MD-020 -----------------------------------------------------------------------------------------


def datum(x: float, y: float) -> SymbolItem:
    return SymbolItem(
        id="S2", type="datum", text="datum A", datums=["A"], bbox=(x, y, x + 8, y + 10), provenance="vector"
    )


def test_datum_feature_size_toleranced():
    # the flag's triangle sits on the continuation of the 40's dimension line, just past its right end
    foot = graphics(on_line(1), datum_triangles=[(203.0, 109.0, 209.0, 115.0)])
    loose = page(dimensions=[dim(1, "⌀40")], symbols=[datum(202.0, 125.0)], graphics=foot)
    findings, status = run("datum_feature_size_toleranced", loose)
    assert status.status == "fail" and "feature of size" in findings[0].comment
    fitted = page(dimensions=[dim(1, "⌀40 h7")], symbols=[datum(202.0, 125.0)], graphics=foot)
    assert run("datum_feature_size_toleranced", fitted)[1].status == "pass"
    # a flag on a face, its triangle nowhere near a dimension line
    face = graphics(on_line(1), datum_triangles=[(503.0, 300.0, 509.0, 306.0)])
    assert (
        run(
            "datum_feature_size_toleranced",
            page(dimensions=[dim(1, "⌀40")], symbols=[datum(502.0, 310.0)], graphics=face),
        )[1].status
        == "not_applicable"
    )


def test_pattern_datum_defined():
    call = TextLine(text="4X ⌀9 THRU", bbox=(300.0, 300.0, 360.0, 310.0))
    loose = page(body_text=[call], symbols=[datum(365.0, 300.0)], graphics=graphics())
    assert run("pattern_datum_defined", loose)[1].status == "fail"
    pos = frame("position").model_copy(update={"bbox": (300.0, 315.0, 360.0, 325.0)})
    defined = page(body_text=[call], symbols=[datum(365.0, 300.0), pos], graphics=graphics())
    assert run("pattern_datum_defined", defined)[1].status == "pass"
    chamfer = page(
        body_text=[TextLine(text="1X 45°", bbox=(300.0, 300.0, 340.0, 310.0))],
        symbols=[datum(345.0, 300.0)],
        graphics=graphics(),
    )
    assert run("pattern_datum_defined", chamfer)[1].status == "not_applicable"


# --- NASA-100, NASA-006 -------------------------------------------------------------------------------------


def mark(label: str, x: float = 400.0, y: float = 400.0) -> FieldRevisionMark:
    return FieldRevisionMark(label=label, bbox=(x, y, x + 15, y + 13))


def revs(*numbers: str) -> list[TextLine]:
    return [
        TextLine(text=n, bbox=(1100.0, 700.0 - 15 * i, 1105.0, 709.0 - 15 * i)) for i, n in enumerate(numbers)
    ]


def test_revision_markers_match():
    ok = page(
        revision_numbers=revs("1", "2"), graphics=graphics(revision_marks=[mark("1"), mark("02", x=600)])
    )
    assert run("revision_markers_match", ok)[1].status == "pass"
    unknown = page(
        revision_numbers=revs("1"), graphics=graphics(revision_marks=[mark("1"), mark("3", x=600)])
    )
    findings, status = run("revision_markers_match", unknown)
    assert status.status == "fail" and "Δ3" in findings[0].comment
    unmarked = page(revision_numbers=revs("1", "2"), graphics=graphics(revision_marks=[mark("1")]))
    findings, status = run("revision_markers_match", unmarked)
    assert status.status == "warning" and "Revision 2" in findings[0].comment
    assert run("revision_markers_match", page(graphics=graphics()))[1].status == "not_applicable"


def test_where_indicated_has_marker():
    params = {"trigger_phrases": ["WHERE INDICATED", "INDICATED AREA"]}
    text = "INDUCTION HARDENED TO BE DONE FOR INDICATED AREA"
    bare = notes(text, graphics=graphics())
    assert run("where_indicated_has_marker", bare, **params)[1].status == "fail"
    led = notes(text, graphics=graphics(leadered_text=[(300.0, 300.0, 400.0, 308.0)]))
    assert run("where_indicated_has_marker", led, **params)[1].status == "pass"
    assert (
        run("where_indicated_has_marker", notes("DEBURR ALL EDGES", graphics=graphics()), **params)[1].status
        == "not_applicable"
    )


# --- MX-026, MF-011, MC-004 ---------------------------------------------------------------------------------


def test_intermittent_weld_complete():
    sized = notes("STITCH WELD 50-150 BOTH SIDES")
    assert run("intermittent_weld_complete", sized)[1].status == "pass"
    bare = notes("STITCH WELD BOTH SIDES")
    assert run("intermittent_weld_complete", bare)[1].status == "fail"
    tabled = notes("3) FOR STITCH WELDING, APPLY 25 MM WELD ON END OF WELD", "(WELD-PITCH)")
    assert run("intermittent_weld_complete", tabled)[1].status == "pass"


def test_material_approved():
    def notes(*texts: str):
        return _notes(
            *texts, title_block_fields=fields(material="#")
        )  # the '#' sends the reader to the notes

    params = {
        "table": "material_heat_treatment",
        "classes_table": "materials",
        "governed_classes": ["carbon_steel", "alloy_steel", "tool_steel"],
    }
    assert run("material_approved", notes("# MATERIAL : EN9"), **params)[1].status == "pass"
    findings, status = run("material_approved", notes("# MATERIAL : EN31"), **params)
    assert status.status == "fail" and "DES-11" in findings[0].comment
    assert run("material_approved", notes("# MATERIAL : M.S"), **params)[1].status == "not_applicable"
    assert run("material_approved", notes("# MATERIAL : SAE4140"), **params)[1].status == "warning"


def test_tap_drill_depth():
    params = {"min_extra_pitches": 3, "report_missing": False}
    assert run("tap_drill_depth", notes("M8 x 15 DEEP, DRILL Ø6.8 x 20 DEEP"), **params)[1].status == "pass"
    findings, status = run("tap_drill_depth", notes("M8 x 15 DEEP, DRILL Ø6.8 x 16 DEEP"), **params)
    assert status.status == "fail" and "18.75" in findings[0].comment
    assert run("tap_drill_depth", notes("M8 x 15 DEEP"), **params)[1].status == "not_checked"
    missing = run("tap_drill_depth", notes("M8 x 15 DEEP"), min_extra_pitches=3, report_missing=True)
    assert missing[1].status == "fail"


def test_values_that_are_not_dimensions():
    """Revision numbers, finish-mark Ra values, balloons and stacked-limit fragments are left out."""
    rev = page(
        dimensions=[dim(1, "1", x=402.0, y=403.0)],
        graphics=graphics(g(1), revision_marks=[mark("1")]),
    )
    assert run("unattached_dimension", rev)[1].status == "not_applicable"
    balloon = page(
        dimensions=[dim(1, "2", x=100.0, y=100.0)],
        graphics=graphics(g(1), circles=[CircleItem(centre=(105.0, 104.0), radius=12.0)]),
    )
    assert run("unattached_dimension", balloon)[1].status == "not_applicable"
    fragment = page(
        dimensions=[dim(1, "0", x=100.0, y=90.0), dim(2, "45.5 -0.1", x=100.0, y=99.0)],
        graphics=graphics(g(1), on_line(2)),
    )
    assert run("unattached_dimension", fragment)[1].status == "pass"
