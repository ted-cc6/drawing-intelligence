import json
from typing import Any

import pytest

from drawing_intelligence.extraction import ImagingConfig, extract_pdf
from drawing_intelligence.graph import run_workflow
from drawing_intelligence.llm import LLMClient, RawCompletion, load_registry
from drawing_intelligence.storage import ResponseCache, Telemetry
from drawing_intelligence.understanding import build_parts, understand_page

SMALL = ImagingConfig(dpi=72, grid_rows=1, grid_cols=2)


def knowledge_from_request(kwargs: dict[str, Any], drop: int = 0) -> dict[str, Any]:
    """What a perfect model would answer: every extracted dimension echoed back unchanged."""
    last = kwargs["messages"][0]["content"][-1]["text"]
    page = json.loads(last.split("\n", 1)[1])
    dims = page["dimensions"][drop:]
    return {
        "drawing": dict.fromkeys(
            [
                "number", "title", "revision", "material", "surface_treatment", "heat_treatment", "scale",
                "sheet_size", "units", "general_tolerance_standard", "drawn_date", "checked_date",
                "approved_date", "weight",
            ]
        ),
        "views": [{"id": "view1", "name": "FRONT VIEW", "scale": None}],
        "dimensions": [
            {
                "id": d["id"], "text": d["text"], "value": None, "unit": "mm", "tolerance": None,
                "type": "linear", "is_reference": d["is_reference"], "view_id": "view1", "feature_id": None,
                "source": "pdf_text", "bbox": d["bbox"],
            }
            for d in dims
        ],
        "features": [], "symbols": [], "notes": [], "general_tolerances": [], "revisions": [],
        "uncertain": [],
    }  # fmt: skip


class FakeModel:
    """Answers like a model would; optionally returns garbage first to exercise the retry."""

    def __init__(self, garbage_first: bool = False, drop: int = 0):
        self.garbage_first, self.drop, self.calls = garbage_first, drop, []

    def __call__(self, kwargs, api_key, base_url, timeout) -> RawCompletion:
        self.calls.append(kwargs)
        if self.garbage_first and len(self.calls) == 1:
            return RawCompletion('{"drawing": "oops"}', 1000, 10)
        return RawCompletion(json.dumps(knowledge_from_request(kwargs, self.drop)), 30_000, 5_000)


def _client(settings, tmp_path, fake):
    return LLMClient(
        load_registry(), settings, Telemetry(tmp_path / "t.db"), ResponseCache(tmp_path / "c"), "s", fake
    )


def test_message_has_prompt_images_and_exact_text(make_pdf, tmp_path):
    out = tmp_path / "ex"
    page = extract_pdf(make_pdf(), out, imaging=SMALL).pages[0]
    parts = build_parts(page, out)
    kinds = [type(p).__name__ for p in parts]
    assert kinds[0] == "TextPart" and kinds.count("ImagePart") == 4  # full + 2 tiles + title block
    assert parts[-1].text.startswith("EXTRACTED TEXT (JSON):")  # type: ignore[union-attr]
    assert "matched_lines" not in parts[-1].text  # type: ignore[union-attr]


def test_message_leaves_out_what_stage_1_derives_by_code(make_pdf, tmp_path):
    # The prompt stays the one ADR 0009 chose the model on: raw text yes, code-derived fields no.
    out = tmp_path / "ex"
    page = extract_pdf(make_pdf(), out, imaging=SMALL).pages[0]
    text = json.loads(build_parts(page, out)[-1].text.split("\n", 1)[1])  # type: ignore[union-attr]
    for key in ("title_block_fields", "title_block_layout", "general_tolerances", "revision_rows"):
        assert key not in text
    assert all("limits" not in d for d in text["dimensions"])
    assert all("chain_ids" not in c and "overall_id" not in c for c in text["chain_checks"])
    assert text["title_block_text"] and text["dimensions"]  # the raw text is all still there


def test_understand_page_valid(make_pdf, settings, tmp_path):
    out = tmp_path / "ex"
    page = extract_pdf(make_pdf(), out, imaging=SMALL).pages[0]
    res = understand_page(_client(settings, tmp_path, FakeModel()), page, out, model="qwen3-vl-plus")
    assert res.valid and res.attempts == 1 and not res.problems
    assert res.cost_usd > 0 and res.model == "qwen3-vl-plus" and res.thinking == "off"


def test_understand_page_retries_once_on_invalid_json(make_pdf, settings, tmp_path):
    out = tmp_path / "ex"
    page = extract_pdf(make_pdf(), out, imaging=SMALL).pages[0]
    fake = FakeModel(garbage_first=True)
    res = understand_page(_client(settings, tmp_path, fake), page, out)
    assert res.valid and res.attempts == 2 and len(fake.calls) == 2
    assert "previous reply was not valid" in fake.calls[1]["messages"][0]["content"][0]["text"]


def test_missing_dimensions_are_reported(make_pdf, settings, tmp_path):
    out = tmp_path / "ex"
    page = extract_pdf(make_pdf(), out, imaging=SMALL).pages[0]
    res = understand_page(_client(settings, tmp_path, FakeModel(drop=1)), page, out)
    assert res.valid and res.problems == [f"D1 ({page.dimensions[0].text}) missing"]


def test_workflow_end_to_end_is_ephemeral(make_pdf, settings):
    fake = FakeModel()
    res = run_workflow(make_pdf(pages=2), settings, imaging=SMALL, completion_fn=fake)
    assert [r.page_number for r in res.understanding] == [1, 2] and all(r.valid for r in res.understanding)
    assert len(fake.calls) == 2  # one call per page
    assert not (settings.sessions_dir / res.session_id).exists()  # client data gone
    tel = Telemetry(settings.telemetry_db)
    assert len(tel.calls(res.session_id)) == 2


def test_extract_only_needs_no_keys(make_pdf, settings):
    settings.openai_api_key = settings.qwen_api_key = None
    res = run_workflow(make_pdf(), settings, understand=False, imaging=SMALL)
    assert res.extraction.pages[0].dimensions and not res.understanding


def test_export_keeps_an_explicit_copy(make_pdf, settings, tmp_path):
    res = run_workflow(
        make_pdf(), settings, imaging=SMALL, completion_fn=FakeModel(), export_dir=tmp_path / "x"
    )
    assert res.exported_to is not None
    names = {p.name for p in res.exported_to.iterdir()}
    assert {
        "extraction.json",
        "page_1_extraction.png",
        "page_1_knowledge.png",
        "page_1_understanding.json",
    } <= names


def test_keep_mode_reuses_the_cache(make_pdf, settings):
    settings.retention = "keep"
    pdf, fake = make_pdf(), FakeModel()
    run_workflow(pdf, settings, imaging=SMALL, completion_fn=fake)
    second = run_workflow(pdf, settings, imaging=SMALL, completion_fn=fake)
    assert len(fake.calls) == 1 and second.understanding[0].cached


def test_unknown_model_fails_fast(make_pdf, settings):
    with pytest.raises(ValueError, match="unknown model"):
        run_workflow(make_pdf(), settings, imaging=SMALL, model="gpt-0", completion_fn=FakeModel())


# --- review stage (ADR 0010) ------------------------------------------------------------------------------


def test_review_runs_through_to_a_verified_result(make_pdf, settings, tmp_path):
    from drawing_intelligence.review import load_rulebook

    pdf = make_pdf(overall="405")  # the chain 135 + 130 + (135) adds up to 400
    res = run_workflow(
        pdf, settings, imaging=SMALL, completion_fn=FakeModel(), review=True, export_dir=tmp_path / "x"
    )
    assert res.review is not None
    statuses = {s.rule_id: s.status for s in res.review.rule_statuses}
    assert len(statuses) == len(load_rulebook().rules)  # every rule has exactly one status
    assert statuses["CN-001"] == "fail" and statuses["CN-004"] == "fail"
    assert res.review.reviewers_run == ["checks"]
    assert set(res.review.reviewers_skipped) == {"drawing_practice", "manufacturability", "design_intent"}
    assert res.exported_to is not None and (res.exported_to / "review_result.json").exists()
    assert not (settings.sessions_dir / res.session_id).exists()  # still ephemeral


def test_review_without_understanding_needs_no_model(make_pdf, settings):
    settings.openai_api_key = settings.qwen_api_key = None
    res = run_workflow(make_pdf(), settings, understand=False, review=True, imaging=SMALL)
    assert res.review is not None and not res.understanding
    assert {s.rule_id: s.status for s in res.review.rule_statuses}["CN-001"] == "pass"


def test_a_crashing_reviewer_does_not_lose_the_review(make_pdf, settings, monkeypatch):
    from drawing_intelligence.graph import workflow

    def boom(ctx):
        raise RuntimeError("checks crashed")

    monkeypatch.setitem(workflow.REVIEWER_FNS, "checks", boom)
    res = run_workflow(make_pdf(), settings, understand=False, review=True, imaging=SMALL)
    assert res.review is not None and "checks" in res.review.reviewers_skipped
    assert {s.status for s in res.review.rule_statuses} == {"not_checked"}
    assert "checks crashed" in res.review.extra["reviewer_errors"]["checks"]
