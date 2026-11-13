"""The 2026-11-12 batch of medium checks: one passing and one failing case each (lighter bar, see backlog)."""

from __future__ import annotations

from drawing_intelligence.schemas import SymbolItem, TextItem, TextLine
from tests.test_checks import dim, fields, page, run
from tests.test_checks_easy import line, notes


def test_part_class_stated():
    params = {"classes": ["T+S", "A", "B", "C"]}
    assert (
        run("part_class_stated", page(title_block_fields=fields(part_class="B")), **params)[1].status
        == "pass"
    )
    findings, status = run("part_class_stated", page(title_block_fields=fields(part_class=None)), **params)
    assert status.status == "fail" and "empty" in findings[0].comment
    assert (
        run("part_class_stated", page(title_block_fields=fields(part_class="X")), **params)[1].status
        == "fail"
    )


def test_weld_class_for_part_class():
    table = {"T+S": "B", "A": "C", "B": "C", "C": "D"}
    ok = notes("WELD CLASS              : B IF APPLICABLE", title_block_fields=fields(part_class="B"))
    assert run("weld_class_for_part_class", ok, table=table)[1].status == "pass"
    loose = notes(
        '8) WELD CLASS - "D"', "2) WELDING SHOULD BE NEAT", title_block_fields=fields(part_class="A")
    )
    findings, status = run("weld_class_for_part_class", loose, table=table)
    assert status.status == "fail" and "looser" in findings[0].comment
    none = notes("2) WELDING SHOULD BE NEAT AND CLEAN.")
    assert "no weld quality level" in run("weld_class_for_part_class", none, table=table)[0][0].comment
    path = notes("\\\\srv\\PRV58 - Battery Tray Welding\\x.dft")  # a file path is not welding
    assert run("weld_class_for_part_class", path, table=table)[1].status == "not_applicable"


def test_material_for_size():
    params = {"table": "material_heat_treatment"}
    ok = notes("1) # USE STD. ф20g6 En-8(D) BRIGHT BAR.")
    assert run("material_for_size", ok, **params)[1].status == "pass"
    big = notes("1)#USE STD. DIA.35g6 En-8(D) BRIGHT BAR.")
    findings, status = run("material_for_size", big, **params)
    assert status.status == "fail" and "EN24" in findings[0].comment


def test_stock_size_available():
    params = {"table": "raw_material_sizes", "allowance_mm": 2}
    assert (
        run("stock_size_available", notes("1) # USE STD. Ø20g6 En-8(D) BRIGHT BAR."), **params)[1].status
        == "pass"
    )
    findings, status = run(
        "stock_size_available", notes("1)#USE STD. DIA.35g6 En-8(D) BRIGHT BAR."), **params
    )
    assert status.status == "fail" and "nearest" in findings[0].comment


def test_thread_engagement():
    params = {"min_factor": {"aluminium": 1.5, "steel": 1.0}}
    steel = notes("M6 x 12.00 mm DEEP", "# MATERIAL : EN9")
    assert run("thread_engagement", steel, **params)[1].status == "pass"
    alu = notes("M6 x 6 DEEP", title_block_fields=fields(material="Aluminum, 6061-T6"))
    findings, status = run("thread_engagement", alu, **params)
    assert status.status == "fail" and "aluminium" in findings[0].comment
    unknown = notes("M6 x 6 DEEP", title_block_fields=fields(material="#"))
    assert run("thread_engagement", unknown, **params)[1].status == "not_checked"


def test_section_labels_match():
    labelled = page(view_labels=[TextItem(text="SECTION A-A", bbox=(300.0, 500.0, 360.0, 510.0))])
    assert run("section_labels_match", labelled)[1].status == "fail"
    labelled.body_text.extend([line("A", x=200.0, y=200.0), line("A", x=500.0, y=200.0)])
    assert run("section_labels_match", labelled)[1].status == "pass"
    odd = page(view_labels=[TextItem(text="SECTION A-B", bbox=(300.0, 500.0, 360.0, 510.0))])
    assert "differ" in run("section_labels_match", odd)[0][0].comment


def hole_table(*rows: tuple[str, ...]):
    lines = [line("HOLE TABLE", x=300.0, y=100.0)]
    lines += [
        line(t, x=x, y=120.0) for t, x in (("X", 200.0), ("Y", 250.0), ("Size", 330.0), ("REMARK", 450.0))
    ]
    for i, row in enumerate(rows):
        lines += [line(t, x=x, y=140.0 + 20 * i) for t, x in zip(row, (200.0, 250.0, 300.0), strict=False)]
    return page(body_text=lines)


def test_hole_table_complete():
    ok = hole_table(("0.00", "0.00", "Ø 20.00 mm THRU'"), ("-2.12", "94.05", "M8 x 12 DEEP"))
    assert run("hole_table_complete", ok)[1].status == "pass"
    bad = hole_table(("0.00", "0.00", "Ø 20.00 mm"), ("-2.12", "94.05", "M8 x 12 DEEP"))
    findings, status = run("hole_table_complete", bad)
    assert status.status == "fail" and "depth or THRU" in findings[0].comment
    assert run("hole_table_complete", page())[1].status == "not_applicable"


def test_hole_depth_stated():
    assert run("hole_depth_stated", notes("Ø 6.6 DRILL THRU'"))[1].status == "pass"
    assert run("hole_depth_stated", notes("Ø 6.6 DRILL"))[1].status == "fail"
    revision = notes("2-M6 TAP & DIA.6.6 ADDED.")  # a revision description, not a call-out
    assert run("hole_depth_stated", revision)[1].status == "not_applicable"
    wrapped = page(body_text=[line("C'BORE Ø 10.00 mm - 10.00 mm", y=300.0), line("DEEP", y=310.0)])
    assert run("hole_depth_stated", wrapped)[1].status == "pass"


def flag(x: float, y: float) -> SymbolItem:
    return SymbolItem(
        id="S1", type="datum", text="datum A", datums=["A"], bbox=(x, y, x + 8, y + 12), provenance="vector"
    )


def test_thread_datum_qualifier():
    thread = TextLine(text="$ M65 X 2", bbox=(300.0, 300.0, 340.0, 310.0))
    on = page(body_text=[thread], symbols=[flag(345.0, 300.0)])
    assert run("thread_datum_qualifier", on)[1].status == "fail"
    qualified = page(
        body_text=[thread, TextLine(text="MD", bbox=(355.0, 300.0, 365.0, 310.0))],
        symbols=[flag(345.0, 300.0)],
    )
    assert run("thread_datum_qualifier", qualified)[1].status == "pass"
    # the flag is on the Ø4 dimension, nearer than the thread
    beside = page(
        dimensions=[dim(1, "⌀4 -0.05", x=346.0, y=315.0)], body_text=[thread], symbols=[flag(345.0, 300.0)]
    )
    assert run("thread_datum_qualifier", beside)[1].status == "not_applicable"


def frame(characteristic: str, tolerance: str, x: float = 345.0) -> SymbolItem:
    return SymbolItem(
        id="S1",
        type="gdt",
        text=f"{characteristic} {tolerance} | A",
        characteristic=characteristic,
        tolerance=tolerance,
        datums=["A"],
        bbox=(x, 300.0, x + 40, 310.0),
        provenance="vector",
    )


def test_projected_zone_on_threads():
    features = ["tapped_hole"]
    thread = TextLine(text="M8 x 16 DEEP", bbox=(300.0, 300.0, 340.0, 310.0))
    bare = page(body_text=[thread], symbols=[frame("position", "⌀0.1")])
    assert run("projected_zone_on_threads", bare, features=features)[1].status == "fail"
    projected = page(body_text=[thread], symbols=[frame("position", "⌀0.1 Ⓟ 12")])
    assert run("projected_zone_on_threads", projected, features=features)[1].status == "pass"


def test_material_modifier_on_feature_of_size():
    assert (
        run("material_modifier_on_feature_of_size", page(symbols=[frame("position", "⌀0.1 Ⓜ")]))[1].status
        == "pass"
    )
    flat = page(symbols=[frame("flatness", "0.05 Ⓜ")])
    findings, status = run("material_modifier_on_feature_of_size", flat)
    assert status.status == "fail" and "flatness" in findings[0].comment
    assert run("material_modifier_on_feature_of_size", page())[1].status == "not_applicable"


def test_mass_within_envelope():
    params = {"table": "material_specific_weight", "margin": 50}
    dims = [dim(1, "100"), dim(2, "50"), dim(3, "20")]  # 100 × 50 × 20 mm of steel: 0.785 kg
    ok = page(dimensions=dims, title_block_fields=fields(weight="0.75 kg"))
    assert run("mass_within_envelope", ok, **params)[1].status == "pass"
    grams = page(dimensions=dims, title_block_fields=fields(weight="750 kg"))  # grams written as kg
    assert run("mass_within_envelope", grams, **params)[1].status == "fail"
