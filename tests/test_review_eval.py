"""`di eval review` scoring: matching findings to answer keys, labels, recall and precision (fake reviews)."""

from __future__ import annotations

from drawing_intelligence.eval.answer_key import AnswerKey, ExpectedFinding, Kind, NotAFinding
from drawing_intelligence.eval.review_eval import label, same_evidence, score_case, summarize
from drawing_intelligence.review.rulebook import Rule, RuleSource, new_finding
from drawing_intelligence.schemas import EvidenceRef, ReviewResult
from drawing_intelligence.schemas.review import EvidenceKind


def ev(kind: EvidenceKind = "dimension", ref="D6", bbox=None, quote="17") -> EvidenceRef:
    return EvidenceRef(
        kind=kind, ref=ref if kind != "text" else None, page=1, bbox=bbox, quote=quote, provenance="pdf_text"
    )


def rule(rid: str) -> Rule:
    return Rule(
        id=rid, category="consistency", requirement=rid, severity="major", check_type="code", check="x",
        source=RuleSource(document="t", section="1"),
    )  # fmt: skip


def finding(rid: str, *evidence: EvidenceRef, reviewer: str = "checks"):
    return new_finding(rule(rid), reviewer=reviewer, evidence=list(evidence) or [ev()], comment="c")


def expected(rid: str, *evidence: EvidenceRef, also: list[str] | None = None) -> ExpectedFinding:
    return ExpectedFinding(
        rule_id=rid, category="consistency", severity="major", result="fail",
        evidence=list(evidence) or [ev()], description="d", also_acceptable=also or [],
    )  # fmt: skip


def key(kind: Kind = "planted", exp=(), pre=(), must_not=()) -> AnswerKey:
    return AnswerKey(
        case=f"X_{kind}", kind=kind, base="b", pdf="x.pdf", planted="p",
        expected=list(exp), pre_existing=list(pre), must_not_flag=list(must_not),
    )  # fmt: skip


def review(*findings) -> ReviewResult:
    return ReviewResult(source_file="x.pdf", rulebook_version="v", findings=list(findings))


def test_same_evidence_by_key_or_by_bbox_for_text():
    assert same_evidence([ev(), ev(ref="D9")], [ev()])
    assert not same_evidence([ev(ref="D9")], [ev()])
    a = ev("text", bbox=[10, 10, 20, 20], quote='3.94"')
    b = ev("text", bbox=[15, 15, 30, 30], quote='3.94"')
    c = ev("text", bbox=[40, 40, 50, 50], quote='3.94"')
    assert same_evidence([a], [b]) and not same_evidence([a], [c])


def test_labels():
    k = key(
        exp=[expected("CN-001", also=["CN-004"])],
        pre=[expected("TB-016", ev("title_block", ref="checked_date"))],
    )
    assert label(finding("CN-001"), k) == "caught"
    assert label(finding("CN-004"), k) == "caught"  # an acceptable rule on the key's evidence catches it too
    # caused by the planted error, but not citing its evidence:
    assert label(finding("CN-004", ev(ref="D9")), k) == "acceptable"
    assert label(finding("CN-001", ev(ref="D9")), k) == "false_alarm"  # right rule, wrong place
    assert label(finding("TB-016", ev("title_block", ref="checked_date")), k) == "pre_existing"
    assert label(finding("TB-099"), k) == "false_alarm"


def test_score_and_summary():
    built = {"CN-001", "TB-016"}
    planted = key(exp=[expected("CN-001")])
    unbuilt = key(exp=[expected("MC-001")])
    near = key(
        kind="near_miss", must_not=[NotAFinding(rule_ids=["TL-003"], evidence=[ev()], description="d")]
    )
    scores = [
        score_case(planted, review(finding("CN-001")), built),
        score_case(unbuilt, review(), built),
        score_case(near, review(finding("TL-003")), built),
    ]
    s = summarize(scores)
    assert (s.caught, s.planted, s.caught_covered, s.covered) == (1, 2, 1, 1)
    assert s.recall == 0.5 and s.recall_covered == 1.0
    assert (s.correct, s.findings) == (1, 2)
    assert [(case, f.rule_id) for case, f in s.false_alarms_on_quiet] == [("X_near_miss", "TL-003")]
    assert s.by_reviewer == {"checks": (1, 2)}


def test_llm_warnings_on_quiet_drawings_are_measured_apart_from_the_code_gate():
    llm_rule = rule("MC-001").model_copy(update={"check_type": "llm", "check": None})
    llm = new_finding(llm_rule, reviewer="manufacturability", evidence=[ev()], comment="c")
    code = finding("CN-001")
    s = summarize([score_case(key(kind="clean"), review(llm, code), set())])
    assert [f.rule_id for _, f in s.false_alarms_on_quiet] == ["CN-001"]
    assert [f.rule_id for _, f in s.llm_alarms_on_quiet] == ["MC-001"]


def test_llm_rules_count_as_covered_only_when_their_reviewer_can_judge_them():
    from drawing_intelligence.eval.review_eval import built_rule_ids
    from drawing_intelligence.settings import get_settings

    rules = get_settings().config_path / "rules"
    code_only, with_llm = built_rule_ids(rules), built_rule_ids(rules, llm=True)
    assert "TL-002" not in code_only and "TL-002" in with_llm
    assert "MX-001" not in with_llm  # needs feature locations stage 1 does not read yet
    assert "CN-001" in code_only and "CN-001" in with_llm
