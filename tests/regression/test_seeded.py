"""The committed planted-error drawings (A5a) and their answer keys. Needs data/raw and data/eval/seeded."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pymupdf
import pytest

from drawing_intelligence.eval.answer_key import AnswerKey, load_answer_keys
from drawing_intelligence.eval.seed import CASES, seed_all
from drawing_intelligence.extraction import extract_pdf
from drawing_intelligence.review.rulebook import load_rulebook
from drawing_intelligence.schemas.review import EvidenceRef
from drawing_intelligence.settings import get_settings

pytestmark = pytest.mark.regression

_S = get_settings()
SEEDED = _S.data_path / "eval" / "seeded"
HAVE = SEEDED.is_dir() and _S.raw_dir.is_dir()
KEYS = load_answer_keys(SEEDED) if HAVE else []
needs_data = pytest.mark.skipif(not HAVE, reason="no seeded cases in data/eval/seeded")


def _words(pdf: Path) -> list[tuple[str, pymupdf.Rect]]:
    """Words as the drawing is viewed (visual coordinates, as in case.json and the extraction)."""
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        return [(w[4], pymupdf.Rect(w[:4]) * page.rotation_matrix) for w in page.get_text("words")]


def _key_rect(word: tuple[str, pymupdf.Rect]) -> tuple[str, int, int]:
    return word[0], round(word[1].x0), round(word[1].y0)


@needs_data
def test_every_case_is_built_and_has_a_key():
    by_name = {k.case: k for k in KEYS}
    assert sorted(by_name) == sorted(c.name for c in CASES)
    for case in CASES:
        key = by_name[case.name]
        assert (key.kind, key.base, key.pdf, key.planted) == (
            case.kind,
            case.base,
            f"{case.name}.pdf",
            case.summary,
        )
        assert (SEEDED / case.name / key.pdf).is_file()
    assert sum(k.kind == "planted" for k in KEYS) >= 15


@needs_data
def test_committed_drawings_are_what_the_seed_script_builds(tmp_path):
    for r in seed_all(_S.raw_dir, tmp_path):
        built, committed = tmp_path / r.case, SEEDED / r.case
        assert json.loads((built / "case.json").read_text("utf-8")) == json.loads(
            (committed / "case.json").read_text("utf-8")
        ), r.case
        assert [_key_rect(w) for w in _words(built / r.pdf)] == [
            _key_rect(w) for w in _words(committed / r.pdf)
        ]
        with pymupdf.open(built / r.pdf) as a, pymupdf.open(committed / r.pdf) as b:
            assert len(a[0].get_drawings()) == len(b[0].get_drawings()), r.case


@needs_data
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_each_case_changes_only_its_planted_text(case):
    record = json.loads((SEEDED / case.name / "case.json").read_text("utf-8"))
    original_words = _words(_S.raw_dir / f"{case.base}.pdf")
    original = Counter(_key_rect(w) for w in original_words)
    seeded = Counter(_key_rect(w) for w in _words(SEEDED / case.name / record["pdf"]))
    lost, gained = original - seeded, seeded - original
    if case.kind == "clean":
        assert not lost and not gained
        return
    assert lost, "nothing was changed"
    edited = [pymupdf.Rect(e["bbox"]) for e in record["edits"]]
    for text, rect in original_words:  # every word that went was one of the edited texts
        if lost[_key_rect((text, rect))]:
            centre = ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
            assert any(e.contains(centre) for e in edited), f"{text!r} lost outside the edits"
    new_words = Counter(w for e in record["edits"] if e["to"] for w in e["to"].split())
    assert not Counter(t for t, *_ in gained.elements()) - new_words, "words added that no edit wrote"


@needs_data
def test_keys_follow_the_rulebook():
    rules = {r.id: r for r in load_rulebook().rules}
    for key in KEYS:
        for f in key.expected + key.pre_existing:
            rule = rules[f.rule_id]
            assert (f.category, f.severity) == (rule.category, rule.severity), f"{key.case} {f.rule_id}"
            assert f.result == ("warning" if rule.check_type == "llm" else "fail"), f"{key.case} {f.rule_id}"
            assert set(f.also_acceptable) <= set(rules), f"{key.case} {f.also_acceptable}"
        for trap in key.must_not_flag:
            assert set(trap.rule_ids) <= set(rules), f"{key.case} {trap.rule_ids}"


def _evidence(key: AnswerKey) -> list[EvidenceRef]:
    found = [e for f in key.expected + key.pre_existing for e in f.evidence]
    return found + [e for trap in key.must_not_flag for e in trap.evidence]


@needs_data
@pytest.mark.parametrize("key", KEYS, ids=lambda k: k.case)
def test_key_evidence_points_at_the_seeded_drawing(key):
    pdf = SEEDED / key.case / key.pdf
    dims = {d.id: d for d in extract_pdf(pdf).pages[0].dimensions}
    words = _words(pdf)
    with pymupdf.open(pdf) as doc:
        sheet = doc[0].rect  # as viewed
    for e in _evidence(key):
        assert e.bbox is not None, e
        box = pymupdf.Rect(e.bbox)
        inside = [
            w for w, r in words if pymupdf.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1).contains(r)
        ]
        if e.kind == "dimension":
            assert e.ref in dims and dims[e.ref].text == e.quote, (
                f"{e.ref} is {dims.get(e.ref)}, key says {e.quote}"
            )
            assert dims[e.ref].bbox == pytest.approx(e.bbox, abs=0.2)
        elif e.quote is not None:  # title-block values and notes: the words printed there
            assert " ".join(inside) == e.quote
        elif e.kind == "title_block":  # a field the case emptied
            assert not inside, f"{e.ref} should be empty, has {inside}"
        else:  # a region where something was removed
            assert box in sheet
