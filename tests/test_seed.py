"""The planted-error seed script and answer-key format (A5a), on synthetic sheets: no client data needed."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from drawing_intelligence import cli
from drawing_intelligence.eval.answer_key import KEY_FILE, AnswerKey, load_answer_keys
from drawing_intelligence.eval.seed import CAM, Case, Edit, apply_edits, seed_case
from drawing_intelligence.extraction import extract_pdf
from drawing_intelligence.extraction.template import load_template
from tests.conftest import draw_sample_sheet

REMAPS = load_template().glyph_remap


def _words(page: pymupdf.Page) -> list[tuple[str, pymupdf.Rect]]:
    """Words as the drawing is viewed (visual coordinates)."""
    return [(w[4], pymupdf.Rect(w[:4]) * page.rotation_matrix) for w in page.get_text("words")]


def _where(page: pymupdf.Page, word: str) -> pymupdf.Rect:
    (rect,) = [r for w, r in _words(page) if w == word]
    return rect


def _edited(pdf: Path, *edits: Edit, erase=()) -> tuple[pymupdf.Page, list]:
    page = pymupdf.open(pdf)[0]
    return page, apply_edits(page, edits, REMAPS, erase)


def test_replacement_takes_the_old_values_place_and_breaks_the_chain(make_pdf, tmp_path):
    pdf = make_pdf()
    before = _where(pymupdf.open(pdf)[0], "400")
    doc = pymupdf.open(pdf)
    page = doc[0]
    applied = apply_edits(page, (Edit("400", "405"),), REMAPS)
    after = _where(page, "405")
    assert after.y1 == pytest.approx(before.y1, abs=0.1)  # same baseline and centre
    assert (after.x0 + after.x1) / 2 == pytest.approx((before.x0 + before.x1) / 2, abs=0.3)
    assert "400" not in [w for w, _ in _words(page)]
    assert applied[0].find == "400" and applied[0].to == "405" and applied[0].font == "Helvetica"
    out = tmp_path / "seeded.pdf"
    doc.save(out)
    (chain,) = extract_pdf(out).pages[0].chain_checks
    assert chain.overall_text == "405" and not chain.match  # 135 + 130 + (135) = 400


def test_removal_takes_only_that_text_and_keeps_the_line_art(make_pdf):
    pdf = make_pdf()
    original = pymupdf.open(pdf)[0]
    words, paths = sorted(w for w, _ in _words(original)), len(original.get_drawings())
    page, applied = _edited(pdf, Edit("130"))
    words.remove("130")
    assert sorted(w for w, _ in _words(page)) == words
    assert len(page.get_drawings()) == paths
    assert applied[0].to is None


def test_repeated_text_needs_a_locator(make_pdf):
    pdf = make_pdf()
    with pytest.raises(ValueError, match="found 2 times"):
        _edited(pdf, Edit("135", "136"))
    page, _ = _edited(pdf, Edit("135", "136", at=(380, 275)))  # the reference dimension, on the right
    assert _where(page, "135").x0 < 320 < _where(page, "136").x0


def test_missing_text_is_an_error(make_pdf):
    with pytest.raises(ValueError, match="not found"):
        _edited(make_pdf(), Edit("999", "998"))


@pytest.mark.parametrize("align", ["start", "end", "centre"])
def test_replacement_keeps_its_start_end_or_centre(make_pdf, align):
    pdf = make_pdf()
    old = _where(pymupdf.open(pdf)[0], "400")
    page, _ = _edited(pdf, Edit("400", "4000", align=align))
    new = _where(page, "4000")
    kept = {"start": (new.x0, old.x0), "end": (new.x1, old.x1), "centre": (new.x0 + new.x1, old.x0 + old.x1)}
    assert kept[align][0] == pytest.approx(kept[align][1], abs=0.3)


def test_span_changes_one_piece_of_a_line():
    page = pymupdf.open().new_page(width=1191, height=842)
    page.insert_text((100, 100), "01/10/2025", fontsize=8)
    page.insert_text((142, 100), "01/10/2025", fontsize=8.5)  # another size: one line, two pieces
    apply_edits(page, (Edit("01/10/2025 01/10/2025", "25/09/2025", span=0),), REMAPS)
    assert [w for w, _ in sorted(_words(page), key=lambda w: w[1].x0)] == ["25/09/2025", "01/10/2025"]


def test_a_label_beside_a_vertical_value_survives():
    """The section letter printed in a vertical dimension's descender space must not go with the value."""
    page = pymupdf.open().new_page(width=1191, height=842)
    page.insert_text((200, 300), "28.5", fontsize=9.6, rotate=90)
    value = _where(page, "28.5")
    page.insert_text((value.x1 - 1.0, 285), "B", fontsize=9.6)  # overlaps the value's box by 1 pt
    apply_edits(page, (Edit("28.5", "28.500"),), REMAPS)
    assert sorted(w for w, _ in _words(page)) == ["28.500", "B"]


def test_an_edit_that_would_take_a_neighbour_is_refused():
    page = pymupdf.open().new_page(width=1191, height=842)
    page.insert_text((100, 100), "70", fontsize=10)
    page.insert_text((108, 110), "XY", fontsize=10, rotate=90)  # its Y crosses the 70's glyphs
    with pytest.raises(ValueError, match="also remove"):
        apply_edits(page, (Edit("70", "71"),), REMAPS)


def test_erase_removes_line_art_wholly_inside_the_box_only():
    page = pymupdf.open().new_page(width=1191, height=842)
    page.insert_text((600, 650), "NOTE", fontsize=10)
    page.draw_rect(pymupdf.Rect(590, 630, 660, 660))  # a frame inside the box
    page.draw_line((500, 645), (760, 645))  # a line running through it
    apply_edits(page, (), REMAPS, erase=((580, 620, 670, 670),))
    drawings = page.get_drawings()
    assert len(drawings) == 1 and drawings[0]["rect"].width == pytest.approx(260)
    assert [w for w, _ in _words(page)] == ["NOTE"]


def test_edits_on_a_rotated_page_land_where_the_drawing_shows_them():
    """The samples are stored with /Rotate 90; edits work in the content's own coordinates and restore it."""
    page = pymupdf.open().new_page(width=842, height=1191)
    draw_sample_sheet(page)
    page.set_rotation(90)
    before = _where(page, "400")
    (applied,) = apply_edits(page, (Edit("400", "405"),), REMAPS)
    assert page.rotation == 90
    after = _where(page, "405")
    assert (after.x0 + after.x1, after.y0 + after.y1) == pytest.approx(
        (before.x0 + before.x1, before.y0 + before.y1), abs=0.6
    )
    assert applied.bbox == pytest.approx([round(v, 1) for v in before], abs=0.6)


def test_seed_case_is_repeatable(make_pdf, tmp_path):
    raw = make_pdf("S.pdf").parent
    case = Case("T01_overall", "S", "planted", (Edit("400", "405"),), "overall 400 -> 405")
    a = seed_case(case, raw, tmp_path / "a", REMAPS)
    seed_case(case, raw, tmp_path / "b", REMAPS)
    for name in (a.pdf, "case.json"):
        assert (tmp_path / "a" / case.name / name).read_bytes() == (
            tmp_path / "b" / case.name / name
        ).read_bytes()
    record = (tmp_path / "a" / case.name / "case.json").read_bytes()
    assert b"\r\n" not in record
    assert json.loads(record)["edits"][0]["to"] == "405"


def test_di_eval_seed_builds_cases_and_rejects_unknown_names(settings, monkeypatch, make_pdf):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    settings.raw_dir.mkdir(parents=True)
    make_pdf("x.pdf").replace(settings.raw_dir / f"{CAM}.pdf")
    runner = CliRunner()
    r = runner.invoke(cli.app, ["eval", "seed", "--only", "C01_clean_cam_plate"])
    assert r.exit_code == 0, r.output
    assert (
        settings.data_path / "eval" / "seeded" / "C01_clean_cam_plate" / "C01_clean_cam_plate.pdf"
    ).is_file()
    r = runner.invoke(cli.app, ["eval", "seed", "--only", "P99_no_such_case"])
    assert r.exit_code != 0 and "no such case" in r.output


def _evidence() -> list[dict]:
    return [{"kind": "dimension", "ref": "D1", "page": 1, "quote": "105", "provenance": "pdf_text"}]


def _finding() -> dict:
    return {
        "rule_id": "CN-001",
        "category": "consistency",
        "severity": "critical",
        "result": "fail",
        "evidence": _evidence(),
        "description": "the chain no longer adds up",
    }


def _key(kind: str, **parts) -> dict:
    return {"case": "X", "kind": kind, "base": "S", "pdf": "X.pdf", "planted": "-", **parts}


@pytest.mark.parametrize(
    "key",
    [
        _key("planted", expected=[_finding()]),
        _key(
            "near_miss", must_not_flag=[{"rule_ids": ["TL-003"], "evidence": _evidence(), "description": "-"}]
        ),
        _key("clean", pre_existing=[_finding()]),
    ],
)
def test_answer_key_accepts_each_kind(key):
    AnswerKey.model_validate(key)


@pytest.mark.parametrize(
    "key",
    [
        _key("planted"),  # a planted case must expect its error
        _key("clean", expected=[_finding()]),  # only planted cases expect findings
        _key("near_miss"),  # a near-miss names the rules that must stay quiet
        _key("planted", expected=[{**_finding(), "evidence": []}]),  # a finding points at something
        _key("planted", expected=[{**_finding(), "severity": "high"}]),  # the rulebook's severities only
    ],
)
def test_answer_key_rejects_inconsistent_keys(key):
    with pytest.raises(ValidationError):
        AnswerKey.model_validate(key)


def test_load_answer_keys_reads_every_case_folder_in_order(tmp_path):
    for name in ("B", "A"):
        (tmp_path / name).mkdir()
        key = _key("clean", case=name)
        (tmp_path / name / KEY_FILE).write_text(json.dumps(key), encoding="utf-8")
    (tmp_path / "no_key").mkdir()
    assert [k.case for k in load_answer_keys(tmp_path)] == ["A", "B"]
