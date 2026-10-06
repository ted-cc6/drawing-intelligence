import pytest

from drawing_intelligence.extraction.classify import classify


@pytest.mark.parametrize(
    "text",
    [
        "35",
        "(35)",
        "10±0.1",
        "⌀15",
        "R5",
        "2-⌀15",
        "45°",
        "4 x 90°",
        "H7",
        "⌀20 H7",
        "11 (-0.2/-0.1)",
        "-0.1",
    ],
)
def test_dimensions(text):
    assert classify(text) == "dimension_value"


@pytest.mark.parametrize("text", ["SECTION A-A", "DETAIL B", "SCALE 1:2", "TYP", "TYP.", "02 NOS"])
def test_view_labels(text):
    assert classify(text) == "view_label"


@pytest.mark.parametrize("text", ["2. DO NOT SCALE DRAWING", "HARDEN AND TEMPER", "SCALE"])
def test_notes_are_not_view_labels(text):
    # notebook v2 fix: a note that merely contains "SCALE" is not a view label
    assert classify(text) == "note"


@pytest.mark.parametrize(
    ("text", "expected"), [("", "empty"), ("  ", "empty"), ("A-3", "other_numeric"), ("-", "text_other")]
)
def test_other(text, expected):
    assert classify(text) == expected
