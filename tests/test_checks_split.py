"""The 2026-11-13 batch of the last 11 rules: the tagger (AI finds the feature) and the code checks on its
tags, the candidates the AI reviewers judge, and the rules that became code (MD-002, DM-002, MP-012).
One passing and one failing case each."""

from __future__ import annotations

import json

from drawing_intelligence.llm import LLMClient, RawCompletion, load_registry
from drawing_intelligence.review import load_rulebook
from drawing_intelligence.review.checks import registered
from drawing_intelligence.review.llm_reviewer import candidates_for, run_llm_reviewer
from drawing_intelligence.review.runner import run_rule
from drawing_intelligence.schemas import (
    DimensionGraphics,
    DimensionTag,
    DrawingKnowledge,
    PageExtraction,
    PageGraphics,
    SymbolItem,
    TextItem,
)
from drawing_intelligence.storage import ResponseCache, Telemetry
from drawing_intelligence.understanding.tagging import tag_page
from tests.test_checks import ctx, dim, page, rule
from tests.test_checks_hard import g

UNDERCUT = {"table": "is1369_thread_runout_undercut", "g1_minus_d_mm": 0.5}


def tag(i: int, text: str, role: str, of: str | None = None) -> DimensionTag:
    return DimensionTag(dimension_id=f"D{i}", quote=text, role=role, of=of)  # type: ignore[arg-type]


def status(check: str, p: PageExtraction, tags: list[DimensionTag] | None = None, **params):
    """(findings, status) of `check` on page `p`, with the tagger's `tags` when given."""
    c = ctx(p)
    if tags is not None:
        c = type(c)(**{**c.__dict__, "tags": {1: tags}})
    return run_rule(c, rule(check, **params), registered()[check])


def tagged(check: str, dims: list[TextItem], tags: list[DimensionTag], **params):
    return status(check, page(dimensions=dims), tags, **params)


def knowledge(dimensions: list[dict] | None = None) -> DrawingKnowledge:
    fields = DrawingKnowledge.model_fields["drawing"].annotation.model_fields  # type: ignore[union-attr]
    return DrawingKnowledge.model_validate(
        {
            "drawing": dict.fromkeys(fields),
            "views": [],
            "dimensions": dimensions or [],
            "features": [],
            "symbols": [],
            "notes": [],
            "general_tolerances": [],
            "revisions": [],
            "uncertain": [],
        }
    )


def datum_flag(x: float, y: float) -> SymbolItem:
    return SymbolItem(
        id="S1", type="datum", text="datum A", datums=["A"], bbox=(x, y, x + 8, y + 10), provenance="vector"
    )


# --- the tagger ---------------------------------------------------------------------------------------------


class TagModel:
    def __init__(self, tags):
        self.tags, self.calls = tags, []

    def __call__(self, kwargs, api_key, base_url, timeout) -> RawCompletion:
        self.calls.append(kwargs)
        return RawCompletion(json.dumps({"tags": self.tags}), 9_000, 80)


def test_tagger_keeps_tags_that_quote_the_drawing(settings, tmp_path):
    d1 = {
        "id": "D1",
        "text": "6",
        "value": 6,
        "unit": "mm",
        "tolerance": None,
        "type": "linear",
        "is_reference": False,
        "view_id": None,
        "feature_id": None,
        "source": "pdf_text",
        "bbox": None,
    }
    fake = TagModel(
        [
            {"dimension_id": "D1", "quote": "6", "role": "keyway_width", "of": "Ø20"},
            {"dimension_id": "D1", "quote": "8", "role": "keyway_width", "of": "Ø20"},  # misquote
            {"dimension_id": "D9", "quote": "6", "role": "keyway_width", "of": None},  # no such dimension
        ]
    )
    client = LLMClient(
        load_registry(), settings, Telemetry(tmp_path / "t.db"), ResponseCache(tmp_path / "c"), "s", fake
    )
    res = tag_page(client, page(), tmp_path, knowledge([d1]))
    assert [t.quote for t in res.tags] == ["6"] and res.dropped == 2 and len(fake.calls) == 1


# --- WST-206, MC-007, MC-008, WST-242 -----------------------------------------------------------------------


def test_fit_letter_case_matches_feature():
    hole = "⌀20 H7"
    assert (
        tagged("fit_letter_case_matches_feature", [dim(1, hole)], [tag(1, hole, "internal_fit")])[1].status
        == "pass"
    )
    shaft = "⌀20 h7"
    findings, st = tagged("fit_letter_case_matches_feature", [dim(1, shaft)], [tag(1, shaft, "internal_fit")])
    assert st.status == "fail" and "H7" in (findings[0].recommended_correction or "")
    untagged = status("fit_letter_case_matches_feature", page(dimensions=[dim(1, shaft)]))  # no tagger run
    assert untagged[1].status == "not_checked"


def test_keyway_standard():
    shaft = dim(2, "⌀30 h7")
    ok = tagged(
        "keyway_standard", [dim(1, "8 P9"), shaft], [tag(1, "8 P9", "keyway_width", "D2")], table="keyways"
    )
    assert ok[1].status == "pass"  # a 22-30 mm shaft takes an 8 mm key
    findings, st = tagged(
        "keyway_standard", [dim(1, "6 P9"), shaft], [tag(1, "6 P9", "keyway_width", "D2")], table="keyways"
    )
    assert st.status == "fail" and "gives 8" in findings[0].comment
    # the keyway's d - t1 (16.5) is not a diameter: the keyway is not judged against it
    depth = tagged(
        "keyway_standard", [dim(1, "6")], [tag(1, "6", "keyway_width", "16.5-0.1")], table="keyways"
    )
    assert depth[1].status == "not_checked"
    bottom = [dim(1, "16.5 -0.1"), dim(2, "⌀20 g6")]
    tags = [tag(1, "16.5 -0.1", "keyway_bottom_shaft", "D2")]
    assert tagged("keyway_standard", bottom, tags, table="keyways")[1].status == "pass"


def test_circlip_groove_waits_for_the_standard():
    groove = [tag(1, "⌀19", "circlip_groove_diameter", "⌀20")]
    res = tagged("circlip_groove_standard", [dim(1, "⌀19")], groove, table="circlip_grooves")
    assert res[1].status == "not_checked" and "PARI" in (res[1].note or "")
    none = tagged("circlip_groove_standard", [dim(1, "⌀19")], [], table="circlip_grooves")
    assert none[1].status == "not_applicable"


def test_thread_undercut_matches():
    ok_tags = [tag(1, "3", "undercut_width", "M10"), tag(2, "R 1", "undercut_radius", "M10")]
    assert (
        tagged("thread_undercut_matches", [dim(1, "3"), dim(2, "R 1")], ok_tags, **UNDERCUT)[1].status
        == "pass"
    )
    narrow = tagged(
        "thread_undercut_matches", [dim(1, "1.5")], [tag(1, "1.5", "undercut_width", "M10")], **UNDERCUT
    )
    assert narrow[1].status == "fail" and "less than" in narrow[0][0].comment
    shallow = tagged(
        "thread_undercut_matches", [dim(1, "⌀9")], [tag(1, "⌀9", "undercut_diameter", "M10")], **UNDERCUT
    )
    assert shallow[1].status == "fail" and "larger than g" in shallow[0][0].comment
    fine = [tag(1, "1.5", "undercut_width", "M10 x 1")]
    assert tagged("thread_undercut_matches", [dim(1, "1.5")], fine, **UNDERCUT)[1].status == "not_checked"


def test_undercut_guards():
    tapped = [tag(1, "1.5", "undercut_width", "M10 x 20 DEEP")]
    # a blind tapped hole has no undercut drawn
    assert tagged("thread_undercut_matches", [dim(1, "1.5")], tapped, **UNDERCUT)[1].status == "not_checked"
    odd = [tag(1, "⌀34.5", "undercut_diameter", "M5")]
    # 34.5 cannot be an M5's undercut diameter
    assert tagged("thread_undercut_matches", [dim(1, "⌀34.5")], odd, **UNDERCUT)[1].status == "not_checked"


# --- MP-012, MD-002, DM-002 (code) --------------------------------------------------------------------------


def test_ordinate_origin():
    def ordinate_page(texts: list[str], flag: bool) -> PageExtraction:
        dims = [dim(i, t, x=100.0 + 60 * i) for i, t in enumerate(texts, 1)]
        gr = PageGraphics(dimensions=[g(i, ordinate=True) for i in range(1, len(texts) + 1)])
        return page(dimensions=dims, graphics=gr, symbols=[datum_flag(150.0, 120.0)] if flag else [])

    assert status("ordinate_origin", ordinate_page(["0", "25", "50", "80"], flag=True))[1].status == "pass"
    findings, st = status("ordinate_origin", ordinate_page(["10", "25", "50", "80"], flag=True))
    assert st.status == "fail" and "not marked 0" in findings[0].comment
    assert (
        "datum" in status("ordinate_origin", ordinate_page(["0", "25", "50", "80"], flag=False))[0][0].comment
    )


def test_datums_needed():
    tight = [dim(1, "20±0.02"), dim(2, "⌀6 H7 (+0.012/0)", y=200)]
    findings, st = status("datums_needed", page(dimensions=tight), tight_tolerance_mm=0.02)
    assert st.status == "fail" and [e.quote for e in findings[0].evidence] == ["20±0.02"]
    flagged = page(dimensions=tight, symbols=[datum_flag(10.0, 10.0)])
    assert status("datums_needed", flagged, tight_tolerance_mm=0.02)[1].status == "pass"
    fit_only = page(dimensions=[dim(1, "⌀6 H7 (+0.012/0)"), dim(2, "40±0.1", y=200)])
    # a fit alone is a size tolerance and needs no datum
    assert status("datums_needed", fit_only, tight_tolerance_mm=0.02)[1].status == "not_applicable"


def test_duplicate_dimension():
    def line(i: int, y: float, x0: float, x1: float) -> DimensionGraphics:
        return g(i, line=(x0, y, x1, y), line_arrowheads=2, span_pts=x1 - x0, arrow_tips=[(x0, y), (x1, y)])

    dims = [dim(1, "40", y=100), dim(2, "40", y=200)]
    twice = page(
        dimensions=dims, graphics=PageGraphics(dimensions=[line(1, 112, 100, 213), line(2, 212, 100, 213)])
    )
    findings, st = status("duplicate_dimension", twice)
    assert st.status == "fail" and len(findings[0].evidence) == 2
    apart = page(
        dimensions=dims, graphics=PageGraphics(dimensions=[line(1, 112, 100, 213), line(2, 212, 300, 413)])
    )
    assert status("duplicate_dimension", apart)[1].status == "pass"  # equal values on two features


# --- candidates for the AI reviewers ------------------------------------------------------------------------


def test_candidates_and_rules_left_out(settings, tmp_path):
    from tests.test_llm_reviewer import ReviewModel, client

    book = load_rulebook()
    mx = book.get("MX-006")
    assert candidates_for(ctx(page(dimensions=[dim(1, "24")])), mx) == []
    pattern = ctx(page(dimensions=[dim(1, "4X ⌀9 THRU")]))
    assert candidates_for(pattern, mx) == [{"page": 1, "dimension_id": "D1", "text": "4X ⌀9 THRU"}]
    base = ctx(page(dimensions=[dim(1, "13")]))
    plain = type(base)(**{**base.__dict__, "rulebook": book, "knowledge": {1: knowledge()}})
    fake = ReviewModel([])
    out = run_llm_reviewer(plain, "drawing_practice", client(settings, tmp_path, fake))
    assert {s.rule_id: s.status for s in out.rule_statuses}["MX-006"] == "not_checked"  # waits for geometry
    assert len(fake.calls) == 1  # the reviewer's other rules are still judged
    assert "MX-006" not in json.dumps(fake.calls[0], ensure_ascii=False)


def test_angle_stated():
    from tests.test_checks_easy import notes

    findings, st = status("angle_stated", notes("CHAMFER ALL TAPPED HOLES"))
    assert st.status == "fail" and "without its angle" in findings[0].comment
    assert status("angle_stated", notes("CHAMFER 1 X 45° ALL TAPPED HOLES"))[1].status == "pass"
    assert (
        status("angle_stated", notes("CHAMFER & DIMENSION ADDED"))[1].status == "not_applicable"
    )  # a change note
