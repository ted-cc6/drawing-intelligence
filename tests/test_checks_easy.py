"""The 2026-11-12 batch of easy checks: one passing and one failing case each (lighter bar, see backlog)."""

from __future__ import annotations

from drawing_intelligence.schemas import ChainCheck, PageExtraction, TextItem, TextLine
from tests.test_checks import dim, fields, page, run

PLAN = {"notes": ["UNSP. RADII", "UNSP. CHF", "Gen Tol"]}


def line(text: str, x: float = 300.0, y: float = 300.0) -> TextLine:
    return TextLine(text=text, bbox=(x, y, x + 100, y + 8))


def note(text: str, y: float = 300.0) -> TextItem:
    return TextItem(text=text, bbox=(300.0, y, 400.0, y + 8))


def notes(*texts: str, **kw):
    """A page whose body carries `texts`, one line each (stage 1 gives them as notes and body lines)."""
    items = [note(t, 300.0 + 12 * i) for i, t in enumerate(texts)]
    return page(notes=items, body_text=[line(t, y=300.0 + 12 * i) for i, t in enumerate(texts)], **kw)


# --- heat treatment and plating (DES-11, DES-12) -----------------------------------------------------------


def test_heat_treatment_allowed():
    ok = notes("1) TO BE TOUGHENED UPTO 28-32 HRC.", "# MATERIAL : EN9")
    assert run("heat_treatment_allowed", ok, table="material_heat_treatment")[1].status == "pass"
    nil = notes("1) TO BE CASE HARDENED UPTO 56~60 HRC.", "# MATERIAL : EN9")  # EN9: case is NIL
    findings, status = run("heat_treatment_allowed", nil, table="material_heat_treatment")
    assert status.status == "fail" and "NIL" in findings[0].comment
    induction = notes("INDUCTION HARDENED TO BE DONE FOR INDICATED AREA", "# MATERIAL : 20MnCr5")
    assert (
        "Induction" in run("heat_treatment_allowed", induction, table="material_heat_treatment")[0][0].comment
    )
    unknown = notes("1) TO BE TOUGHENED UPTO 28-32 HRC.", "# MATERIAL : M.S.")
    assert run("heat_treatment_allowed", unknown, table="material_heat_treatment")[1].status == "not_checked"


def test_hardness_in_range():
    ok = notes("1) TO BE TOUGHENED UPTO 28-32 HRC.", "# MATERIAL : EN9")
    assert run("hardness_in_range", ok, table="material_heat_treatment")[1].status == "pass"
    low = notes("TO BE CASE HARDENED UPTO 40~45 HRC.", "2) CASE DEPTH 0.8~1.2mm.", "MATERIAL :- 20MnCr5")
    findings, status = run("hardness_in_range", low, table="material_heat_treatment")
    assert status.status == "fail" and "40-45 HRC" in findings[0].comment
    plus_minus = notes("1)TO BE CASE HARDENED TO 58u2 HRc.", "# MATERIAL: 20MnCr5")  # 58±2 = 56-60: in range
    assert run("hardness_in_range", plus_minus, table="material_heat_treatment")[1].status == "pass"
    bare = notes("1) TO BE HARDENED UPTO 32-35 HRC.", "# MATERIAL : EN 24")  # no process named: every column
    findings, _ = run("hardness_in_range", bare, table="material_heat_treatment")
    assert "no process named" in findings[0].comment and "toughening" in findings[0].comment


def test_treatment_combination():
    nitrided = notes("PROCESS- GAS NITROCARBURISING WITH OXIDATION")
    assert run("treatment_combination", nitrided, table="material_heat_treatment")[1].status == "pass"
    both = notes("PROCESS- GAS NITROCARBURISING WITH OXIDATION", "# FINISH:- HARD CHROME PLATING 0.025 mm")
    assert run("treatment_combination", both, table="material_heat_treatment")[1].status == "fail"
    assert run("treatment_combination", page(), table="material_heat_treatment")[1].status == "not_applicable"


def test_surface_treatment_approved():
    ok = page(title_block_fields=fields(surface_treatment="I.Z.B.P. (TRIVALENT)"))
    assert run("surface_treatment_approved", ok, table="plating_processes")[1].status == "pass"
    odd = page(title_block_fields=fields(surface_treatment="CADMIUM PLATING"))
    assert run("surface_treatment_approved", odd, table="plating_processes")[1].status == "fail"
    na = page(title_block_fields=fields(surface_treatment="N.A"))
    assert run("surface_treatment_approved", na, table="plating_processes")[1].status == "not_applicable"
    paint = page(title_block_fields=fields(surface_treatment="PAINTING"))
    assert (
        run("surface_treatment_approved", paint, table="plating_processes", not_plating=["paint"])[1].status
        == "not_applicable"
    )


def test_treatment_prerequisites():
    params = {"table": "plating_processes", "prerequisites": "plating_prerequisites"}
    ok = notes("# FINISH:- HARD CHROME PLATING", "1) TO BE CASE HARDENED UPTO 56~60 HRC.")
    assert run("treatment_prerequisites", ok, **params)[1].status == "pass"
    soft = notes("# FINISH:- HARD CHROME PLATING", "1) TO BE TOUGHENED UPTO 28-32 HRC.")
    findings, status = run("treatment_prerequisites", soft, **params)
    assert status.status == "fail" and "hardened base" in findings[0].comment
    flash = notes("4) $ FLASH HARD CHROME PLATING 15 TO 20 MICRONS,")  # flash chrome: no prerequisites
    assert run("treatment_prerequisites", flash, **params)[1].status == "not_applicable"


def test_plating_edge_radius():
    procs = ["hard chrome", "flash chrome", "QPQ"]
    plated = notes("# FINISH:- HARD CHROME PLATING")
    assert run("plating_edge_radius", plated, processes=procs)[1].status == "pass"
    plated.other_numeric.append(TextItem(text="0.5x 45°", bbox=(200.0, 200.0, 230.0, 208.0)))
    assert run("plating_edge_radius", plated, processes=procs)[1].status == "fail"  # warning via the rulebook
    assert run("plating_edge_radius", page(), processes=procs)[1].status == "not_applicable"


def test_masking_note():
    params = {"table": "plating_processes", "processes": ["hard_chrome", "flash_chrome"]}
    unmasked = notes("4) $ FLASH HARD CHROME PLATING 15 TO 20 MICRONS,", "M6 x 14 DEEP")
    assert run("masking_note", unmasked, **params)[1].status == "fail"
    masked = notes("4) $ FLASH HARD CHROME PLATING", "M6 x 14 DEEP", "5) MASK ALL THREADS DURING PLATING")
    assert run("masking_note", masked, **params)[1].status == "pass"
    izbp = notes("# FINISH : IZBP", "M6 x 14 DEEP")  # thin finish: not judged
    assert run("masking_note", izbp, **params)[1].status == "not_applicable"


# --- consistency -----------------------------------------------------------------------------------------


def closed(reference: bool) -> PageExtraction:
    return page(
        dimensions=[dim(1, "28.5"), dim(2, "(16.5)" if reference else "16.5±0.1"), dim(3, "45")],
        chain_checks=[
            ChainCheck(
                chain_texts=["28.5", "16.5"],
                chain_ids=["D1", "D2"],
                chain_sum=45,
                overall_text="45",
                overall_id="D3",
                overall_value=45,
                match=True,
                diff=0,
            )
        ],
    )


def test_closed_chain():
    assert run("closed_chain", closed(reference=True))[1].status == "pass"
    findings, status = run("closed_chain", closed(reference=False))
    assert status.status == "fail" and {e.ref for e in findings[0].evidence} == {"D1", "D2", "D3"}


def test_template_notes_present():
    ok = page(
        tolerance_table_text=[line("UNSP.RADII"), line("UNSP.CHF.")],
        title_block_text=[line("Gen Tol.: IS 2102")],
    )
    assert run("template_notes_present", ok, **PLAN)[1].status == "pass"
    bare = page(title_block_text=[line("Gen Tol.: IS 2102")])
    findings, status = run("template_notes_present", bare, **PLAN)
    assert status.status == "fail" and "UNSP. RADII" in findings[0].comment


def bordered(*items: TextItem):
    """An A3 sheet with zone markers in the margin: columns at y 20 / 822, rows at x 20 / 1171."""
    markers = [line(str(i), x=200.0 * i, y=16.0) for i in (1, 2, 3)] + [
        line(str(i), x=200.0 * i, y=818.0) for i in (1, 2, 3)
    ]
    markers += [TextLine(text=c, bbox=(16.0, y, 24.0, y + 8)) for c, y in (("A", 200.0), ("B", 400.0))]
    markers += [TextLine(text=c, bbox=(1167.0, y, 1175.0, y + 8)) for c, y in (("A", 200.0), ("B", 400.0))]
    return page(body_text=markers, notes=list(items))


def test_content_inside_border():
    inside = TextItem(text="WEAR DETAILS : N.A.", bbox=(102.0, 799.0, 200.0, 808.0))  # near the frame, inside
    assert run("content_inside_border", bordered(inside))[1].status == "pass"
    out = TextItem(text="3) DEBURR", bbox=(300.0, 815.0, 380.0, 826.0))  # reaches the bottom zone markers
    findings, status = run("content_inside_border", bordered(out))
    assert status.status == "fail" and "bottom margin" in findings[0].comment
    assert (
        run("content_inside_border", page(notes=[out]))[1].status == "not_checked"
    )  # no markers to place it


def test_rotated_view_labelled():
    label = "ROTATED <angle> CW|CCW"
    ok = page(view_labels=[note("SECTION A-A ROTATED 90° CW")])
    assert run("rotated_view_labelled", ok, label_pattern=label)[1].status == "pass"
    bad = page(view_labels=[note("VIEW B ROTATED")])
    findings, status = run("rotated_view_labelled", bad, label_pattern=label)
    assert status.status == "fail" and "angle or direction" in findings[0].comment
    assert run("rotated_view_labelled", page(), label_pattern=label)[1].status == "not_applicable"


def test_hardness_scales_agree():
    params = {"table": "hardness_conversion_steel"}
    ok = notes("HARDNESS 58-62 HRC (653-746 HV)")
    assert run("hardness_scales_agree", ok, **params)[1].status == "pass"
    bad = notes("HARDNESS 58-62 HRC (300-350 HV)")
    assert run("hardness_scales_agree", bad, **params)[1].status == "fail"
    assert (
        run("hardness_scales_agree", notes("HARDNESS 850 TO 1000 HV."), **params)[1].status
        == "not_applicable"
    )


# --- material --------------------------------------------------------------------------------------------


def test_us_india_equivalent():
    params = {"table": "us_india_materials"}
    shown = page(title_block_fields=fields(material="SAE1018 CRS (Mild Steel 1018)"))
    assert run("us_india_equivalent", shown, **params)[1].status == "pass"
    alone = page(title_block_fields=fields(material="SAE1018 CRS"))
    findings, status = run("us_india_equivalent", alone, **params)
    assert status.status == "fail" and "Mild Steel 1018" in findings[0].comment
    assert run("us_india_equivalent", page(), **params)[1].status == "not_applicable"  # M.S.


# --- manufacturability -----------------------------------------------------------------------------------


def test_depth_to_diameter():
    ok = notes("Ø 6.40 mm x 18.00 mm DEEP", "M6 x 12.00 mm DEEP", "M50 x 1.5 x 30 DEEP")
    assert run("depth_to_diameter", ok, max_ratio=10)[1].status == "pass"
    deep = notes("Ø 3.00 mm x 45.00 mm DEEP")
    findings, status = run("depth_to_diameter", deep, max_ratio=10)
    assert status.status == "fail" and "15.0 × D" in findings[0].comment
    gun = notes("Ø 3.00 mm x 45.00 mm DEEP", "GUN DRILL")
    assert run("depth_to_diameter", gun, max_ratio=10)[1].status == "pass"


def test_taper_ratio_standard():
    params = {"table": "is3458_standard_tapers"}
    assert run("taper_ratio_standard", notes("TAPER 1:20"), **params)[1].status == "pass"
    assert run("taper_ratio_standard", notes("TAPER 1:25"), **params)[1].status == "fail"
    assert run("taper_ratio_standard", notes("SCALE 1:2"), **params)[1].status == "not_applicable"


def test_taper_pin_hole_callout():
    params = {"taper": "1:50", "nominal_d_mm": [6, 8], "table": "is6688_taper_pins"}
    assert run("taper_pin_hole_callout", notes("HOLE FOR TAPER PIN Ø6 1:50"), **params)[1].status == "pass"
    findings, status = run("taper_pin_hole_callout", notes("HOLE FOR TAPER PIN Ø7"), **params)
    assert status.status == "fail" and "1:50" in findings[0].comment and "7 mm" in findings[0].comment


def test_centre_hole_designation_complete():
    params = {"types": ["A", "B"], "d1_mm": [1, 4], "type_B_max_d1_mm": 6.3, "table": "is2473_centre_holes"}
    ok = notes("Centre Hole A×4 IS: 2473")
    assert run("centre_hole_designation_complete", ok, **params)[1].status == "pass"
    for bad, word in (("CENTRE HOLE B×10 IS 2473", "type B"), ("CENTER HOLE", "type and pilot")):
        findings, status = run("centre_hole_designation_complete", notes(bad), **params)
        assert status.status == "fail" and word in findings[0].comment


def test_self_holding_taper_matches_table():
    params = {"table": "is1715_self_holding_tapers"}
    assert (
        run("self_holding_taper_matches_table", notes("MORSE TAPER NO. 3, M12"), **params)[1].status == "pass"
    )
    for bad in ("MORSE TAPER 3 M10", "MORSE TAPER 7"):
        assert run("self_holding_taper_matches_table", notes(bad), **params)[1].status == "fail"
