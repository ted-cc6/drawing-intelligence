"""Stage 4 verify: each rejection reason, duplicate merging, and one status per rule (ADR 0010)."""

from __future__ import annotations

import pytest

from drawing_intelligence.review.rulebook import Rule, Rulebook, RuleSource, new_finding
from drawing_intelligence.review.verify import verify
from drawing_intelligence.schemas import (
    EvidenceRef,
    Extraction,
    PageExtraction,
    ReviewerOutput,
    RuleStatus,
    TextItem,
    TextLine,
    TitleBlockField,
)


def rule(rid: str, check_type: str = "code") -> Rule:
    return Rule(
        id=rid,
        category="consistency",
        requirement=f"requirement {rid}",
        severity="major",
        check_type=check_type,  # type: ignore[arg-type]
        check=None if check_type == "llm" else "some_check",
        source=RuleSource(document="t", section="1"),
    )


BOOK = Rulebook(version="v1", rules=[rule("CN-001"), rule("CN-002"), rule("TB-001"), rule("DP-001", "llm")])
EXTRACTION = Extraction(
    source_file="t.pdf",
    template="wipro_pari",
    n_pages=1,
    pages=[
        PageExtraction(
            page_number=1,
            page_size_pts=(1191.0, 842.0),
            rotation=0,
            dimensions=[TextItem(id="D1", text="35", bbox=(100, 100, 110, 108))],
            body_text=[TextLine(text='OVERALL 3.94"', bbox=(300, 500, 340, 510))],
            title_block_layout="standard",
            title_block_fields={"material": TitleBlockField(value="M.S.", bbox=(900, 780, 920, 790))},
        )
    ],
)


def ev(kind: str = "dimension", **kw) -> EvidenceRef:
    base = {"kind": kind, "page": 1, "provenance": "pdf_text"}
    if kind == "dimension":
        base |= {"ref": "D1", "quote": "35"}
    return EvidenceRef(**{**base, **kw})


def finding(rid: str = "CN-001", *evidence: EvidenceRef, reviewer: str = "checks"):
    r = BOOK.get(rid) if rid in {x.id for x in BOOK.rules} else rule(rid)
    return new_finding(r, reviewer=reviewer, evidence=list(evidence) or [ev()], comment="c")


def out(
    *findings, reviewer: str = "checks", statuses: list[RuleStatus] | None = None, error: str | None = None
):
    return ReviewerOutput(
        reviewer=reviewer, findings=list(findings), rule_statuses=statuses or [], error=error
    )


def test_a_finding_that_resolves_is_kept():
    result, rejected = verify([out(finding())], EXTRACTION, BOOK)
    assert len(result.findings) == 1 and rejected == []
    assert {s.rule_id: s.status for s in result.rule_statuses}["CN-001"] == "fail"


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (finding("XX-999"), "unknown_rule"),
        (finding("CN-001", ev(ref="D9")), "unknown_ref"),
        (finding("CN-001", ev(page=2)), "unknown_page"),
        (finding("CN-001", ev(bbox=[1100, 800, 1300, 900])), "bbox_off_sheet"),
        (finding("CN-001", ev(quote="36")), "quote_mismatch"),
        (finding("CN-001", ev("title_block", ref="materal")), "unknown_title_block_field"),
        (finding("CN-001", ev("title_block", ref="material", quote="EN8")), "quote_mismatch"),
        (finding("CN-001", ev("text", quote='3.95"')), "quote_mismatch"),
        (finding("CN-001", ev("note", ref="N1")), "unknown_ref"),  # notes need the understanding step
    ],
)
def test_each_unresolved_citation_is_dropped_with_its_reason(bad, reason):
    result, rejected = verify([out(bad)], EXTRACTION, BOOK)
    assert result.findings == [] and [r.reason for r in rejected] == [reason]
    assert result.extra["rejected"] == 1


def test_quoted_text_may_be_part_of_a_line():
    result, rejected = verify([out(finding("CN-001", ev("text", quote='3.94"')))], EXTRACTION, BOOK)
    assert len(result.findings) == 1 and rejected == []


def test_duplicates_are_merged_whatever_order_reviewers_finish_in():
    a, b = out(finding(), reviewer="drawing_practice"), out(finding(), reviewer="checks")
    r1, _ = verify([a, b], EXTRACTION, BOOK)
    r2, _ = verify([b, a], EXTRACTION, BOOK)
    assert r1 == r2 and len(r1.findings) == 1
    assert r1.findings[0].reviewer == "checks" and "also raised by drawing_practice" in r1.findings[0].comment


def test_every_rule_gets_exactly_one_status():
    statuses = [
        RuleStatus(rule_id="CN-001", status="pass"),
        RuleStatus(rule_id="CN-002", status="not_applicable", note="no chain"),
        RuleStatus(rule_id="TB-001", status="fail", finding_ids=[finding("TB-001", ev()).id]),
    ]
    bad_tb = finding("TB-001", ev(quote="99"))  # its only finding gets rejected
    result, _ = verify([out(bad_tb, statuses=statuses)], EXTRACTION, BOOK, skipped=["drawing_practice"])
    got = {s.rule_id: (s.status, s.note) for s in result.rule_statuses}
    assert got["CN-001"] == ("pass", None)
    assert got["CN-002"] == ("not_applicable", "no chain")
    assert got["TB-001"] == ("not_checked", "its findings were rejected")  # a rejected fail is never a pass
    assert got["DP-001"] == ("not_checked", "its reviewer did not run")
    assert result.reviewers_skipped == ["drawing_practice"]


def test_a_crashed_reviewer_is_skipped_and_its_rules_not_checked():
    result, _ = verify([out(reviewer="checks", error="boom")], EXTRACTION, BOOK)
    assert result.reviewers_run == [] and result.reviewers_skipped == ["checks"]
    assert {s.status for s in result.rule_statuses} == {"not_checked"}
    assert result.extra["reviewer_errors"] == {"checks": "boom"}


def test_stage_1_symbols_can_be_cited():
    from drawing_intelligence.schemas import SymbolItem

    sym = SymbolItem(
        id="S1", type="datum", text="datum A", datums=["A"], bbox=(300, 300, 312, 312), provenance="vector"
    )
    ex = EXTRACTION.model_copy(update={"pages": [EXTRACTION.pages[0].model_copy(update={"symbols": [sym]})]})
    ok = finding("CN-001", ev("symbol", ref="S1", quote="datum A", provenance="vector"))
    bad = finding("CN-002", ev("symbol", ref="S1", quote="datum B", provenance="pdf_text"))
    result, rejected = verify([out(ok, bad)], ex, BOOK)
    assert [f.rule_id for f in result.findings] == ["CN-001"] and [r.reason for r in rejected] == [
        "quote_mismatch"
    ]
