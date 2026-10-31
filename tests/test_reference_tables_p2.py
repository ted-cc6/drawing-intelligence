"""P2 table structure, published anchors and fidelity to the source workbooks. No LLM calls."""

from __future__ import annotations

import hashlib
import re
import warnings
from itertools import pairwise
from pathlib import Path

import pytest
from openpyxl import load_workbook

from drawing_intelligence.review.reference import TABLE_MODELS, load_reference
from drawing_intelligence.review.rulebook import load_rulebook

SOURCE_DIR = Path("data/client_set/WP Specific Guidelines")


@pytest.fixture(scope="module")
def refs():
    return load_reference()


def test_uploaded_example_test_is_unchanged():
    assert hashlib.sha256(Path("tests/test_reference_tables.py").read_bytes()).hexdigest() == (
        "84fde903790cd3514c06b57c60e259c8a17b5ce15e22f946a9059b5a1054a22a"
    )


def test_every_new_table_is_typed_and_points_to_exact_source_bytes(refs):
    old_tables = {
        "materials",
        "plating_processes",
        "is919_fits",
        "is2102_general_tolerances",
        "iso_metric_threads",
    }
    for name, table in refs.items():
        assert name in TABLE_MODELS and isinstance(table, TABLE_MODELS[name])
        if name in old_tables - {"plating_processes"}:
            continue
        metadata = table.model_dump()["source"]
        source = SOURCE_DIR / metadata["document"]
        assert source.is_file(), source
        assert hashlib.sha256(source.read_bytes()).hexdigest() == metadata["sha256"]
        assert metadata["section"].strip()


def test_des12_all_process_prerequisites_and_constraints_are_transcribed(refs):
    processes = refs["plating_processes"].processes
    assert len(processes) == 10
    assert {p.source_row for p in processes} == set(range(1, 11))
    assert all(p.prerequisites_as_printed and p.process_constraints_as_printed for p in processes)
    by_id = {p.id: p for p in processes}

    def plain(text):
        return re.sub(r"\s+", " ", text).upper()

    assert "MIN 45 HRC" in plain(by_id["hard_chrome"].prerequisites_as_printed)
    assert "MORE THAN 55 HRC" in plain(by_id["balzer"].prerequisites_as_printed)
    assert "TWICE AND THRICE" in plain(by_id["balzer"].process_constraints_as_printed)
    assert "TWICE AND THRICE" not in plain(by_id["zafc"].process_constraints_as_printed)
    assert "EN-24" in plain(by_id["balzer"].remarks_as_printed)
    qpq = plain(by_id["qpq"].process_constraints_as_printed)
    assert "NOT RECOMMENDED" in qpq and "30 TO 50 HRC" in qpq
    structured = next(r for r in refs["plating_prerequisites"].rows if r.process == "qpq")
    assert structured.not_recommended_heat == ["case"] and structured.forbidden_heat == []


def test_des12_specific_pattern_precedes_general_pattern(refs):
    processes = refs["plating_processes"]
    assert processes.identify("HARD ANODIZING").id == "hard_anodizing"
    assert processes.identify("SILVER ANODIZING").id == "silver_anodizing"
    assert processes.identify("AN UNKNOWN FINISH") is None


def test_all_14_equivalent_rows_match_original_cells(refs):
    table = refs["us_india_materials"]
    sheet = load_workbook(SOURCE_DIR / table.source.document, read_only=True, data_only=True)["Sheet1"]
    assert len(table.rows) == 14
    for row, source_row in zip(table.rows, range(5, 19), strict=True):
        assert row.us == str(sheet[f"G{source_row}"].value).strip()
        assert row.india == str(sheet[f"H{source_row}"].value).strip()
        assert row.cell == f"Sheet1!G{source_row}:H{source_row}"
    # A36 has conditional alternatives; recording a workbook row is not approval to substitute blindly.
    assert not next(r for r in table.rows if r.us == "A36").automatic


def test_stock_numeric_subset_matches_source_cells(refs):
    table = refs["raw_material_sizes"]
    workbook = load_workbook(SOURCE_DIR / table.source.document, read_only=True, data_only=True)
    assert len(table.rows) == 22
    for row in table.rows:
        sheet_name, cell_range = row.cell.split("!")
        first, last = cell_range.split(":")
        assert first.startswith("B") and last.startswith("C")
        row_number = int(re.sub(r"\D", "", first))
        sheet = workbook[sheet_name]
        printed_material = str(sheet.cell(row=row_number, column=2).value).strip()
        expected_material = re.sub(r"\s+(?:Round|Plate)$", "", printed_material, flags=re.I)
        expected_sizes = sorted(
            set(
                float(v)
                for v in re.findall(r"\d+(?:\.\d+)?", str(sheet.cell(row=row_number, column=3).value))
            )
        )
        assert row.material == expected_material
        assert row.sizes_mm == expected_sizes


def test_full_stock_catalogue_preserves_all_cells_and_merged_ranges(refs):
    table = refs["raw_material_catalogue"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        workbook = load_workbook(SOURCE_DIR / table.source.document, data_only=False)
    assert len(table.sheets) == 16
    assert sum(len(sheet.cells) for sheet in table.sheets) == 768
    assert [sheet.name for sheet in table.sheets] == workbook.sheetnames
    for sheet in table.sheets:
        expected = {c.coordinate: c.value for row in workbook[sheet.name] for c in row if c.value is not None}
        assert {c.address: c.value for c in sheet.cells} == expected
        assert set(sheet.merged_ranges) == {str(v) for v in workbook[sheet.name].merged_cells.ranges}
    assert table.graphical_shapes_transcribed is False


def test_full_hardness_columns_and_blank_cells(refs):
    table = refs["hardness_conversion_steel"]
    assert len(table.rows) == 34
    by_hv = {r.hv: r for r in table.rows}
    assert by_hv[700].hrc == 60.1 and by_hv[700].hb_carbide_ball == 656
    assert by_hv[550].hb_steel_ball == 505 and by_hv[550].hb_carbide_ball == 517
    assert by_hv[235].hrb == 99.9 and by_hv[235].hrc is None
    assert by_hv[210].tensile_kgf_mm2 == 72
    assert by_hv[940].hrc == 68 and by_hv[940].tensile_kgf_mm2 is None
    assert by_hv[105].hrb == 56.4
    for column in ("hv", "hrc", "hrb", "hb_steel_ball", "hb_carbide_ball", "tensile_kgf_mm2"):
        values = [v for r in table.rows if (v := getattr(r, column)) is not None]
        assert all(a < b for a, b in pairwise(values)), column


def test_specific_weights_preserve_ranges_and_element_vs_alloy(refs):
    values = refs["material_specific_weight"].values
    assert len(values) == 18
    assert values["steel"] == [7.85] and values["grey cast iron"] == [7.2]
    assert values["aluminium"] == [2.7] and values["al alloy"] == [2.8]
    assert values["babbitt metal"] == [7.5, 10.1]
    assert values["copper"] == [8.9]


def test_morse_columns_and_angle_convention_retained(refs):
    table = refs["is1715_self_holding_tapers"]
    assert len(table.rows) == 10 and len({r.designation for r in table.rows}) == 10
    by_name = {r.designation: r for r in table.rows}
    assert by_name["Morse 3"].gauge_d_mm == 23.825 and by_name["Morse 3"].thread == "M12"
    assert by_name["Morse 3"].alpha_dms_as_printed == [1, 26, 16]
    assert by_name["Metric 4"].alpha_dms_as_printed == [1, 25, 26]
    assert by_name["Metric 6"].alpha_dms_as_printed == [1, 25, 56]
    assert by_name["Morse 0"].thread is None


def test_taper_and_centre_hole_lists_match_the_rulebook(refs):
    book = load_rulebook()
    taper = refs["is3458_standard_tapers"].values["denominators"]
    assert taper == [float(r.split(":")[1]) for r in book.get("WST-239").params["ratios"]]
    pins = refs["is6688_taper_pins"].values
    assert pins["nominal_d_mm"] == book.get("WST-229").params["nominal_d_mm"]
    assert pins["taper_denominator"] == [50]
    centres = refs["is2473_centre_holes"].values
    assert centres["A"] == book.get("WST-249").params["d1_mm"]
    assert centres["B"] == centres["A"][:5] and max(centres["B"]) == 6.3


def test_undercut_widths_angles_and_blank_diameters(refs):
    table = refs["is1369_thread_runout_undercut"]
    assert len(table.rows) == 15
    diameters = [d for r in table.rows for d in r.diameters_mm]
    assert len(diameters) == len(set(diameters))
    m2 = next(r for r in table.rows if 2 in r.diameters_mm)
    assert m2.external_width_mm_by_min_angle_deg == {15: None, 22.5: 1, 30: None}
    assert m2.external_g_subtract_mm is None and m2.internal_g1_add_mm is None
    m10 = next(r for r in table.rows if 10 in r.diameters_mm)
    assert m10.external_width_mm_by_min_angle_deg == {15: 3, 22.5: None, 30: 2}
    assert m10.external_radius_mm == 1 and m10.external_g_subtract_mm == 2.1
    assert m10.internal_width_mm_by_min_angle_deg == {20: 5, 25: 3}
    assert m10.internal_radius_mm == 1 and m10.internal_g1_add_mm == 0.5
    for row in table.rows:
        if row.internal_g1_add_mm is not None:
            assert row.internal_g1_add_mm == 0.5
        if row.external_g_subtract_mm is not None:
            assert row.external_g_subtract_mm < min(row.diameters_mm)


def test_keyways_have_source_nominals_without_invented_tolerances(refs):
    table = refs["keyways"]
    assert table.tolerances_transcribed is False
    taper, woodruff = table.taper_keys_is2292, table.woodruff_keys_is2294
    assert len(taper) == 12 and len(woodruff) == 11
    assert taper[0].lower_inclusive and not any(r.lower_inclusive for r in taper[1:])
    assert all(a.shaft_up_to_mm == b.shaft_over_mm for a, b in pairwise(taper))
    assert all(r.shaft_depth_mm + r.hub_depth_mm < r.height_mm for r in taper)
    assert (taper[6].width_mm, taper[6].height_mm) == (10, 8)
    assert (woodruff[-1].key_length_mm, woodruff[-1].key_diameter_mm) == (18.57, 19)


def test_woodruff_depth_sum_matches_the_source_table(refs):
    # In every row of THIS printed table, t + t1 = h + 0.2 mm. This is a source-internal
    # consistency check, not a general clearance/tolerance rule for all Woodruff standards.
    woodruff = refs["keyways"].woodruff_keys_is2294
    for row in woodruff:
        assert row.shaft_depth_mm + row.hub_depth_mm == pytest.approx(row.height_mm + 0.2), row
    source_row = next(r for r in woodruff if r.shaft_over_mm == 8 and r.width_mm == 2.5)
    assert source_row.shaft_depth_mm == 2.9


def test_weld_mapping_is_already_cited_in_rule_params():
    rule = load_rulebook().get("WF-007")
    assert rule.params["table"] == {"T+S": "B", "A": "C", "B": "C", "C": "D"}
    assert "Welding" in rule.source.document and "ISO 5817" in rule.source.section


def test_reference_change_affects_actual_rulebook_version(tmp_path):
    rules = tmp_path / "rules"
    reference = tmp_path / "reference"
    rules.mkdir()
    reference.mkdir()
    (rules / "material.yaml").write_bytes(Path("config/rules/material.yaml").read_bytes())
    table = reference / "test.yaml"
    table.write_text("source_value: 1\n")
    before = load_rulebook(rules).version
    table.write_text("source_value: 2\n")
    assert load_rulebook(rules).version != before
