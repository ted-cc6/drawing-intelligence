"""The LLM reviewers with a fake model: schema, message, answers as warnings, and what verify keeps."""

from __future__ import annotations

import json

import pytest

from drawing_intelligence.extraction import extract_pdf, load_template
from drawing_intelligence.graph import run_workflow
from drawing_intelligence.llm import LLMClient, RawCompletion, load_registry
from drawing_intelligence.review import load_rulebook
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.llm_reviewer import SILENT, build_message, output_schema, run_llm_reviewer
from drawing_intelligence.review.reviewers import reviewer_for
from drawing_intelligence.schemas import DrawingKnowledge
from drawing_intelligence.storage import ResponseCache, Telemetry
from tests.test_eval_and_cli import _knowledge
from tests.test_workflow import SMALL, FakeModel

BOOK = load_rulebook()


class ReviewModel:
    """Answers every reviewer call with the given items."""

    def __init__(self, items):
        self.items, self.calls = items, []

    def __call__(self, kwargs, api_key, base_url, timeout) -> RawCompletion:
        self.calls.append(kwargs)
        return RawCompletion(json.dumps({"findings": self.items}), 8_000, 300)


@pytest.fixture
def ctx(make_pdf):
    page = extract_pdf(make_pdf()).pages[0]
    k = DrawingKnowledge.model_validate(_knowledge(page))
    ex = extract_pdf(make_pdf())
    return ReviewContext(extraction=ex, rulebook=BOOK, template=load_template(), knowledge={1: k})


def client(settings, tmp_path, fake) -> LLMClient:
    return LLMClient(
        load_registry(), settings, Telemetry(tmp_path / "t.db"), ResponseCache(tmp_path / "c"), "s", fake
    )


def dim_item(ctx: ReviewContext, rule_id: str = "MC-001", quote: str | None = None) -> dict:
    d = ctx.pages[0].dimensions[0]
    cite = {"kind": "dimension", "ref": d.id, "page": 1, "quote": quote or d.text}
    return {
        "rule_id": rule_id,
        "evidence": [cite],
        "comment": "too sharp",
        "recommended_correction": "use R 1",
    }


def test_schema_only_allows_the_reviewers_rules():
    schema = output_schema(["MC-001", "MC-003"])
    ok = {"findings": [{"rule_id": "MC-001", "evidence": [], "comment": "c", "recommended_correction": "r"}]}
    schema.model_validate(ok)
    with pytest.raises(ValueError):
        schema.model_validate({"findings": [{**ok["findings"][0], "rule_id": "TB-001"}]})


def test_message_holds_the_rules_and_the_drawing_without_symbols_or_bboxes(ctx):
    rules = [r for r in BOOK.rules if r.check_type == "llm" and reviewer_for(r) == "manufacturability"]
    text = build_message(ctx, rules)
    drawing = json.loads(text.split("DRAWING:\n", 1)[1])
    assert all(r.id in text for r in rules)
    assert "symbols" not in drawing[0] and all("bbox" not in d for d in drawing[0]["dimensions"])


def test_answers_become_warnings_and_silence_is_not_a_pass(ctx, settings, tmp_path):
    fake = ReviewModel([dim_item(ctx)])
    out = run_llm_reviewer(ctx, "manufacturability", client(settings, tmp_path, fake))
    assert len(fake.calls) == 1
    (f,) = out.findings
    assert (f.rule_id, f.result, f.source, f.severity) == (
        "MC-001",
        "warning",
        "llm",
        BOOK.get("MC-001").severity,
    )
    assert f.evidence[0].bbox is not None  # filled in from stage 1
    statuses = {s.rule_id: s for s in out.rule_statuses}
    assert statuses["MC-001"].status == "warning"
    assert {s.status for r, s in statuses.items() if r != "MC-001"} == {"not_checked"}
    assert statuses["MC-003"].note == SILENT


def test_items_a_verifier_could_not_check_are_dropped(ctx, settings, tmp_path):
    no_evidence = {**dim_item(ctx), "evidence": []}
    other_rule = dim_item(ctx, rule_id="TB-001")  # not this reviewer's rule
    out = run_llm_reviewer(
        ctx, "manufacturability", client(settings, tmp_path, ReviewModel([no_evidence, other_rule]))
    )
    assert out.findings == []


def test_no_call_without_understanding(ctx, settings, tmp_path):
    fake = ReviewModel([])
    empty = ReviewContext(**{**ctx.__dict__, "knowledge": {1: None}})
    out = run_llm_reviewer(empty, "design_intent", client(settings, tmp_path, fake))
    assert fake.calls == [] and {s.status for s in out.rule_statuses} == {"not_checked"}


def test_in_the_workflow_a_misquote_is_dropped_by_verify(make_pdf, settings):
    pdf = make_pdf()
    first = extract_pdf(pdf).pages[0].dimensions[0]
    cite = {"kind": "dimension", "ref": first.id, "page": 1, "quote": first.text}
    good = {"rule_id": "MC-001", "evidence": [cite], "comment": "c", "recommended_correction": "r"}
    bad = {**good, "rule_id": "MC-003", "evidence": [{**good["evidence"][0], "quote": "999"}]}
    res = run_workflow(
        pdf, settings, imaging=SMALL, review=True, completion_fn=FakeModel(review_findings=[good, bad])
    )
    assert res.review is not None
    kept = {f.rule_id for f in res.review.findings if f.source == "llm"}
    assert kept == {"MC-001"}
    assert {(r.finding.rule_id, r.reason) for r in res.rejected} >= {("MC-003", "quote_mismatch")}
    assert {s.rule_id: s.status for s in res.review.rule_statuses}["MC-003"] == "not_checked"


def test_llm_review_can_be_turned_off(make_pdf, settings):
    fake = FakeModel()
    res = run_workflow(make_pdf(), settings, imaging=SMALL, review=True, llm_review=False, completion_fn=fake)
    assert res.review is not None and res.review.reviewers_run == ["checks"]
    assert len(fake.calls) == 1  # understanding only
