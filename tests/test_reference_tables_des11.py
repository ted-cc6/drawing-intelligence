"""DES-11 source anchors and independent structural invariants, like test_reference_tables.py.

Expected numeric cells below were read from the supplied PDF, not calculated from the YAML under test.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from drawing_intelligence.review.reference import load_reference
from drawing_intelligence.review.reference_des11 import (
    PROCESSES,
    Des11Stock,
    MaterialHeatTreatment,
)

# Process order: toughening, flame, induction, case, nitriding, through.
# Each numeric tuple is (low HRC, high HRC, low depth mm or None, high depth mm or None).
EXPECTED = {
    "EN9": [(24,32,None,None), (45,55,.6,2), (45,55,.6,2), None, (45,55,.02,.025), (40,45,None,None)],
    "C45": [(24,32,None,None), (45,55,.6,2), (45,55,.6,2), None, None, (40,45,None,None)],
    "EN24": [(24,32,None,None), (45,55,.6,2), (45,55,.6,2), None, None, (50,55,None,None)],
    "SAE8620": [None, None, None, (56,60,.6,2), None, None],
    "20MnCr5": [None, None, None, (56,60,.6,2), None, None],
    "EN19": [None, (50,55,.6,2), (50,55,.6,2), None, (50,55,.02,.025), None],
    "EN41B": [None, None, None, None, (50,55,.02,.025), None],
    "D2": [None, None, None, None, None, (58,62,None,None)],
    "SS304": [None, None, None, None, None, None],
    "EN42": [None, None, None, None, None, None],
    "FG260": [None, None, None, None, None, None],
    "FG300": [None, None, None, None, None, None],
    "OHNS": [None, None, None, None, None, (58,62,None,None)],
}  # fmt: skip

ROUND = [
    10,
    16,
    25,
    30,
    32,
    36,
    40,
    42,
    45,
    50,
    52,
    56,
    60,
    65,
    70,
    75,
    80,
    85,
    90,
    95,
    100,
    105,
    110,
    115,
    120,
    125,
    130,
    135,
    140,
]
SQUARE = [40, 50, 55, 63, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 140]
PLATE = [
    5,
    6,
    10,
    12,
    16,
    20,
    22,
    25,
    28,
    30,
    32,
    36,
    40,
    45,
    50,
    56,
    63,
    70,
    75,
    80,
    90,
    100,
    110,
    120,
    130,
    140,
]
BUFFER = {
    "EN9": [25, 36, 45, 56, 75, 80, 100],
    "EN24": [20, 30, 40, 50, 60, 80],
    "SAE8620": None,
    "20MnCr5": [25, 36, 56, 75, 100],
    "C45": None,
    "EN19": [36, 45, 56, 75, 100],
}


@pytest.fixture(scope="module")
def heat() -> MaterialHeatTreatment:
    return load_reference()["material_heat_treatment"]


@pytest.fixture(scope="module")
def stock() -> Des11Stock:
    return load_reference()["raw_material_sizes_des11"]


def test_des11_identity_and_page_citations(heat, stock):
    source_path = Path(heat.source.repository_path)
    assert source_path.name == "PARI Standard High Carbon  Alloy Steel Material Selection PRD-GD-DES-11.pdf"
    actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
    expected = "282c05fcfdf5a4481e2778a13458029a6f3e3c2d4da53532fd195e80a4f54157"
    assert actual == heat.source.sha256 == stock.source.sha256 == expected
    assert heat.source.document_id == "PRD/GD/DES/11"
    assert heat.source.version == heat.source.revision == 1
    assert heat.source.effective_date.isoformat() == "2016-03-09"
    assert heat.source.pdf_pages == [1] and stock.source.pdf_pages == [2]


def test_page1_has_complete_matrix_including_nil(heat):
    assert [m.key for m in heat.materials] == list(EXPECTED)
    assert [m.row for m in heat.materials] == list(range(1, 14))
    cells = [c for m in heat.materials for c in m.treatments.values()]
    assert len(cells) == 78
    assert sum(c.status == "tabulated" for c in cells) == 21
    assert sum(c.status == "nil" for c in cells) == 57


@pytest.mark.parametrize(
    "grade,process,expected",
    [
        (grade, process, values[i])
        for grade, values in EXPECTED.items()
        for i, process in enumerate(PROCESSES)
    ],
)
def test_every_treatment_cell_against_source(heat, grade, process, expected):
    cell = heat.by_key(grade).treatments[process]
    if expected is None:
        assert cell.status == "nil" and cell.printed == "NIL"
        assert cell.hardness is None and cell.depth_mm is None
        return
    assert cell.status == "tabulated"
    assert (cell.hardness.low, cell.hardness.high) == expected[:2]
    assert cell.hardness.unit == "HRC"
    if expected[2] is None:
        assert cell.depth_mm is None
    else:
        assert cell.depth_mm.unit == "mm"
        assert (cell.depth_mm.low, cell.depth_mm.high) == expected[2:]
    assert cell.area_marking_required == (process in {"flame", "induction", "case"})


@pytest.mark.parametrize("grade", ["EN9", "EN19", "EN41B"])
def test_microns_are_preserved_and_correctly_converted(heat, grade):
    cell = heat.by_key(grade).treatments["nitriding"]
    assert cell.depth_as_printed.unit == "microns"
    assert (cell.depth_as_printed.low, cell.depth_as_printed.high) == (20, 25)
    assert (cell.depth_mm.low, cell.depth_mm.high) == (0.020, 0.025)


def test_plus_minus_cells_and_core_hardness_are_not_confused(heat):
    assert "58 ± 2 HRC" in heat.by_key("SAE8620").treatments["case"].printed
    assert "60 ±2 HRC" in heat.by_key("D2").treatments["through"].printed
    assert "10 to 14 HRC" in heat.by_key("C45").additional_information
    tough = heat.by_key("C45").treatments["toughening"].hardness
    assert (tough.low, tough.high) == (24, 32)


@pytest.mark.parametrize(
    "grade,low,high",
    [
        ("EN9", 60, 75),
        ("C45", 60, 75),
        ("EN24", 75, 130),
        ("20MnCr5", 62, 74),
        ("EN19", 70, 110),
        ("EN41B", 80, 100),
    ],
)
def test_mechanical_property_ranges_and_stress_relation(heat, grade, low, high):
    material = heat.by_key(grade)
    assert (material.uts.low, material.uts.high) == (low, high)
    assert (material.allowable_stress.low, material.allowable_stress.high) == (low / 2, high / 2)
    assert material.uts.unit == material.allowable_stress.unit == "Kg/mm² as printed"


def test_blank_properties_and_dash_cells_remain_distinct_from_nil(heat):
    for grade in {"SAE8620", "D2", "SS304", "EN42", "FG260", "FG300", "OHNS"}:
        material = heat.by_key(grade)
        assert material.uts is None and material.uts_as_printed is None
        assert material.allowable_stress is None and material.allowable_stress_as_printed is None
    assert heat.by_key("FG260").pari_std_as_printed == "--"
    assert heat.by_key("FG300").pari_std_as_printed == "--"
    assert heat.by_key("EN41B").raw_material_note == "--"
    assert heat.by_key("SAE8620").treatments["through"].status == "nil"


def test_form_ambiguity_is_retained_instead_of_first_match_wins(heat):
    assert {m.key for m in heat.candidates("C45")} == {"EN9", "C45"}
    assert {m.key for m in heat.candidates("C55")} == {"EN9", "C45"}
    assert [m.key for m in heat.candidates("C45", "round")] == ["EN9"]
    assert [m.key for m in heat.candidates("C45", "plate_block")] == ["C45"]
    assert {m.key for m in heat.candidates("20MnCr5")} == {"SAE8620", "20MnCr5"}
    assert heat.candidates("unknown") == []


@pytest.mark.parametrize("diameter,expected", [(1, "EN9"), (32, "EN9"), (32.0001, "EN24"), (100, "EN24")])
def test_round_size_boundary_from_rows_1_and_3(heat, diameter, expected):
    assert heat.preferred_round_grade(diameter) == expected


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_selection_diameters_rejected(heat, bad):
    with pytest.raises(ValueError):
        heat.preferred_round_grade(bad)


def test_policies_keep_mandatory_and_recommended_wording_separate(heat):
    assert set(heat.general_notes) == {"i", "ii", "iii"}
    assert "apart from below table" in heat.general_notes["iii"]
    assert "special requirements" in heat.general_notes["iii"]
    strengths = {p.requirement: p.strength for p in heat.policies}
    assert strengths == {
        "nitriding_after_finish_machining": "instruction",
        "prefer_toughening_before_nitriding": "preference",
        "avoid_chrome_after_nitriding": "avoid_recommendation",
    }
    assert all(set(p.material_keys) == {"EN9", "EN19", "EN41B"} for p in heat.policies)
    shared_rows = list(range(8, 14))
    assert all(m.raw_note_shared_rows == shared_rows for m in heat.materials if m.row >= 8)


@pytest.mark.parametrize("grade", BUFFER)
def test_all_page2_sizes_against_source(stock, grade):
    row = next(m for m in stock.materials if m.material == grade)
    if grade == "C45":
        assert row.sizes_mm == {"plate_thickness": PLATE}
        assert row.plate_sheet_dimensions_mm == [2500, 6000]
        assert row.unavailable_forms_as_printed == []
    else:
        assert row.sizes_mm == {"black_round": ROUND, "black_square": SQUARE}
        assert row.unavailable_forms_as_printed == ["Plate", "Flat"]
    assert row.buffer_round_mm == BUFFER[grade]


def test_page2_structure_and_source_inconsistency_preserved(stock, heat):
    assert len(stock.materials) == 6
    assert sum(len(m.sizes_mm) for m in stock.materials) == 11
    assert sum(len(s) for m in stock.materials for s in m.sizes_mm.values()) == 251
    en24 = next(m for m in stock.materials if m.material == "EN24")
    assert 20 in en24.buffer_round_mm and 20 not in en24.sizes_mm["black_round"]
    assert stock.source_anomalies[0].material == "EN24" and stock.source_anomalies[0].sizes_mm == [20]
    # Availability is not filtered by the preferred-use cutoff. These are different source columns.
    en9 = next(m for m in stock.materials if m.material == "EN9")
    assert max(en9.sizes_mm["black_round"]) == 140
    assert heat.by_key("EN9").selection.diameter_mm == 32


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_row",
        "missing_nil_cell",
        "nil_with_numbers",
        "wrong_depth_units",
        "wrong_micron_conversion",
        "reversed_range",
        "missing_exception_note",
    ],
)
def test_corrupt_transcriptions_fail_validation(heat, mutation):
    data = deepcopy(heat.model_dump())
    if mutation == "missing_row":
        data["materials"].pop()
    elif mutation == "missing_nil_cell":
        del data["materials"][0]["treatments"]["case"]
    elif mutation == "nil_with_numbers":
        data["materials"][0]["treatments"]["case"]["hardness"] = {"low": 1, "high": 2, "unit": "HRC"}
    elif mutation == "wrong_depth_units":
        data["materials"][0]["treatments"]["nitriding"]["depth_mm"]["unit"] = "HRC"
    elif mutation == "wrong_micron_conversion":
        data["materials"][0]["treatments"]["nitriding"]["depth_mm"]["high"] = 25
    elif mutation == "reversed_range":
        data["materials"][0]["treatments"]["toughening"]["hardness"]["low"] = 99
    else:
        del data["general_notes"]["iii"]
    with pytest.raises(ValidationError):
        MaterialHeatTreatment.model_validate(data)


def test_unrecorded_source_anomaly_fails_validation(stock):
    data = stock.model_dump()
    data["source_anomalies"] = []
    with pytest.raises(ValidationError):
        Des11Stock.model_validate(data)
