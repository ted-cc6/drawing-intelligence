"""A2: the review contracts (Finding, RuleStatus, ReviewResult) and the rulebook loader."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from typer.testing import CliRunner

from drawing_intelligence import cli
from drawing_intelligence.review import Rule, RulebookError, load_rulebook, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, FindingFeedback, ReviewResult, RuleStatus

runner = CliRunner()

RULE_YAML = """\
rules:
  - id: TB-001
    category: title_block
    requirement: The title block states the material.
    severity: major
    check_type: lookup
    check: title_block_field
    params: {field: material, placeholder_ok: ["#"]}
    source: {document: Check List.docx, section: Title block requirements}
  - id: MF-001
    category: manufacturability
    requirement: Hole depth is machinable for its diameter.
    severity: minor
    check_type: llm
    applies_to: {part_family: [round]}
    source: {document: WP Specific Guidelines, section: Machining}
"""


def dim(ref: str = "D3", provenance: str = "pdf_text", page: int = 1) -> EvidenceRef:
    return EvidenceRef(kind="dimension", ref=ref, page=page, provenance=provenance)  # type: ignore[arg-type]


def rule(**over) -> Rule:
    base = {
        "id": "CN-001",
        "category": "consistency",
        "requirement": "Chain dimensions add up to the overall dimension.",
        "severity": "major",
        "check_type": "code",
        "check": "chain_sum",
        "source": {"document": "Check List.docx", "section": "Common rejection conditions"},
    }
    return Rule.model_validate(base | over)


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rules"
    d.mkdir()
    (d / "title_block.yaml").write_text(RULE_YAML, encoding="utf-8")
    return d


# --- EvidenceRef ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "dimension", "page": 1, "provenance": "pdf_text"},  # no ref
        {"kind": "text", "page": 1, "provenance": "pdf_text"},  # no quote
        {"kind": "region", "page": 1, "provenance": "vector"},  # no bbox
        {"kind": "region", "page": 1, "bbox": [1, 2, 3], "provenance": "vector"},  # bad bbox
        {"kind": "note", "ref": "N1", "page": 0, "provenance": "pdf_text"},  # pages start at 1
    ],
)
def test_evidence_must_point_at_something(kwargs):
    with pytest.raises(ValidationError):
        EvidenceRef.model_validate(kwargs)


# --- Finding trust rules ---------------------------------------------------------------------------------


def test_finding_from_rule_takes_severity_category_and_source_from_the_rule():
    f = new_finding(rule(), reviewer="consistency", evidence=[dim()], comment="10 + 20 != 35")
    assert (f.result, f.severity, f.category, f.source, f.rule_id) == (
        "fail",
        "major",
        "consistency",
        "code",
        "CN-001",
    )
    assert f.id.startswith("F-")


def test_llm_finding_cannot_fail():
    with pytest.raises(ValidationError, match="only be a warning"):
        Finding(
            rule_id="MF-001",
            category="manufacturability",
            requirement="r",
            result="fail",
            severity="minor",
            evidence=[dim()],
            comment="c",
            reviewer="manufacturability",
            source="llm",
        )
    llm_rule = rule(id="MF-001", category="manufacturability", check_type="llm", check=None)
    assert new_finding(llm_rule, reviewer="m", evidence=[dim()], comment="c").result == "warning"


def test_a_rule_marked_result_warning_only_warns():
    soft = rule(result="warning")
    assert not soft.can_fail
    assert new_finding(soft, reviewer="r", evidence=[dim()], comment="c").result == "warning"
    # even a check that asks for a fail gets a warning, and severity still comes from the rule
    forced = new_finding(soft, reviewer="r", evidence=[dim()], comment="c", result="fail")
    assert forced.result == "warning" and forced.severity == soft.severity
    assert new_finding(rule(), reviewer="r", evidence=[dim()], comment="c").result == "fail"


def test_fail_cannot_rest_on_vision_alone_but_a_warning_can():
    with pytest.raises(ValidationError, match="vision-only"):
        new_finding(rule(), reviewer="r", evidence=[dim("V1", "vision")], comment="c")
    w = new_finding(rule(), reviewer="r", evidence=[dim("V1", "vision")], comment="c", result="warning")
    assert w.result == "warning"
    mixed = new_finding(rule(), reviewer="r", evidence=[dim("D1"), dim("S2", "vector")], comment="c")
    assert mixed.result == "fail"


def test_finding_without_a_rule_is_an_info_warning():
    f = new_finding(
        None,
        reviewer="design_intent",
        evidence=[dim()],
        comment="c",
        category="design_intent",
        requirement="Fit looks loose for a locating pin",
    )
    assert (f.result, f.severity, f.source, f.rule_id) == ("warning", "info", "llm", None)
    with pytest.raises(ValidationError, match="without a rule"):
        Finding(
            rule_id=None,
            category="design_intent",
            requirement="r",
            result="warning",
            severity="critical",  # a model may not set severity
            evidence=[dim()],
            comment="c",
            reviewer="d",
            source="llm",
        )
    with pytest.raises(ValueError, match="category and a requirement"):
        new_finding(None, reviewer="d", evidence=[dim()], comment="c")


def test_finding_id_is_stable_across_wording_order_and_bbox():
    a = new_finding(rule(), reviewer="r", evidence=[dim("D1"), dim("D2")], comment="first wording")
    b = new_finding(
        rule(),
        reviewer="r",
        evidence=[
            dim("D2"),
            EvidenceRef(kind="dimension", ref="D1", page=1, bbox=[0, 0, 5, 5], provenance="pdf_text"),
        ],
        comment="second wording",
    )
    c = new_finding(rule(), reviewer="r", evidence=[dim("D1"), dim("D3")], comment="first wording")
    assert a.id == b.id
    assert a.id != c.id


def test_finding_round_trips_and_rejects_a_wrong_id():
    f = new_finding(rule(), reviewer="r", evidence=[dim()], comment="c")
    again = Finding.model_validate_json(f.model_dump_json())
    assert again == f
    with pytest.raises(ValidationError, match="does not match"):
        Finding.model_validate(f.model_dump() | {"id": "F-0000000000"})


# --- RuleStatus and ReviewResult -----------------------------------------------------------------------


def test_rule_status_findings_match_the_status():
    RuleStatus(rule_id="TB-001", status="pass")
    RuleStatus(rule_id="TB-001", status="fail", finding_ids=["F-1"])
    with pytest.raises(ValidationError):
        RuleStatus(rule_id="TB-001", status="fail")
    with pytest.raises(ValidationError):
        RuleStatus(rule_id="TB-001", status="pass", finding_ids=["F-1"])


def test_review_result_is_consistent():
    f = new_finding(rule(), reviewer="r", evidence=[dim()], comment="c")
    ok = ReviewResult(
        source_file="x.pdf",
        rulebook_version="abc",
        findings=[f],
        rule_statuses=[RuleStatus(rule_id="CN-001", status="fail", finding_ids=[f.id])],
    )
    assert ReviewResult.model_validate_json(ok.model_dump_json()) == ok
    with pytest.raises(ValidationError, match="duplicate findings"):
        ReviewResult(source_file="x.pdf", rulebook_version="abc", findings=[f, f])
    with pytest.raises(ValidationError, match="unknown findings"):
        ReviewResult(
            source_file="x.pdf",
            rulebook_version="abc",
            rule_statuses=[RuleStatus(rule_id="CN-001", status="fail", finding_ids=["F-nope"])],
        )
    with pytest.raises(ValidationError, match="more than one status"):
        ReviewResult(
            source_file="x.pdf",
            rulebook_version="abc",
            rule_statuses=[RuleStatus(rule_id="TB-001", status="pass")] * 2,
        )


def test_by_severity_puts_fails_and_critical_first():
    minor = new_finding(rule(id="CN-002", severity="minor"), reviewer="r", evidence=[dim()], comment="c")
    critical = new_finding(
        rule(id="CN-003", severity="critical"), reviewer="r", evidence=[dim()], comment="c"
    )
    warning = new_finding(
        rule(id="CN-004", severity="critical"), reviewer="r", evidence=[dim()], comment="c", result="warning"
    )
    res = ReviewResult(source_file="x.pdf", rulebook_version="v", findings=[warning, minor, critical])
    assert [f.rule_id for f in res.by_severity()] == ["CN-003", "CN-002", "CN-004"]


def test_feedback_records_a_decision():
    fb = FindingFeedback(finding_id="F-1", decision="reject", role="checker", comment="drawn to standard")
    assert fb.at.tzinfo is not None
    with pytest.raises(ValidationError):
        FindingFeedback(finding_id="F-1", decision="maybe")  # type: ignore[arg-type]


# --- Rule and rulebook loader ----------------------------------------------------------------------------


def test_rule_validation():
    with pytest.raises(ValidationError, match="name its check"):
        rule(check=None)
    with pytest.raises(ValidationError):
        rule(id="tb1")  # id format
    with pytest.raises(ValidationError):
        rule(severity="blocker")
    assert not rule(check_type="llm", check=None).can_fail


def test_load_rulebook(rules_dir):
    book = load_rulebook(rules_dir)
    assert [r.id for r in book.rules] == ["TB-001", "MF-001"]
    assert book.get("MF-001").applies_to.part_family == ["round"]
    assert [r.id for r in book.applicable("prismatic", "machining")] == ["TB-001"]
    assert len(book.applicable()) == 2  # unknown family/type: every rule applies
    with pytest.raises(KeyError):
        book.get("XX-999")


def test_missing_or_empty_folder_is_an_empty_rulebook(tmp_path):
    assert load_rulebook(tmp_path / "nope").rules == []
    assert load_rulebook(tmp_path).rules == []


def test_rulebook_version_tracks_content_not_line_endings(rules_dir, tmp_path):
    v1 = load_rulebook(rules_dir).version
    other = tmp_path / "crlf"
    other.mkdir()
    (other / "title_block.yaml").write_bytes(RULE_YAML.replace("\n", "\r\n").encode("utf-8"))
    assert load_rulebook(other).version == v1
    (rules_dir / "title_block.yaml").write_text(RULE_YAML.replace("major", "minor"), encoding="utf-8")
    assert load_rulebook(rules_dir).version != v1


def test_loader_reports_every_problem_at_once(rules_dir):
    (rules_dir / "bad.yaml").write_text(
        """\
rules:
  - id: TB-001
    category: title_block
    requirement: duplicate of the first file
    severity: major
    check_type: llm
    source: {document: d, section: s}
  - id: GD-001
    category: geometry
    requirement: unknown category
    severity: high
    check_type: code
    source: {document: d, section: s}
  - id: CN-001
    category: consistency
    requirement: a code rule without its check function
    severity: major
    check_type: code
    source: {document: d, section: s}
""",
        encoding="utf-8",
    )
    (rules_dir / "broken.yaml").write_text("rules: [unclosed", encoding="utf-8")
    (rules_dir / "shape.yaml").write_text("just: a mapping", encoding="utf-8")
    with pytest.raises(RulebookError) as e:
        load_rulebook(rules_dir)
    text = "\n".join(e.value.problems)
    assert "duplicate id" in text
    assert "category" in text and "severity" in text and "name its check" in text
    assert "not valid YAML" in text
    assert "top-level `rules:` list" in text


class FieldParams(BaseModel):
    field: str
    placeholder_ok: list[str] = []


def test_loader_checks_params_of_built_checks_and_lists_the_rest(rules_dir):
    book = load_rulebook(rules_dir, checks={"title_block_field": FieldParams})
    assert len(book.rules) == 2 and book.not_built({"title_block_field": FieldParams}) == []
    # A check with no function yet is not an error: its rule is "not built" (ADR 0010).
    book = load_rulebook(rules_dir, checks={"chain_sum": FieldParams})
    assert [r.check for r in book.not_built({"chain_sum": FieldParams})] == ["title_block_field"]

    class Strict(BaseModel):
        field: int

    with pytest.raises(RulebookError, match=r"params\.field"):
        load_rulebook(rules_dir, checks={"title_block_field": Strict})


# --- CLI ---------------------------------------------------------------------------------------------


def test_cli_rules(rules_dir, tmp_path):
    r = runner.invoke(cli.app, ["rules", str(rules_dir)])
    assert r.exit_code == 0, r.output
    assert "2 rules" in r.output and "Title block" in r.output
    assert "empty" in runner.invoke(cli.app, ["rules", str(tmp_path / "none")]).output
    (rules_dir / "bad.yaml").write_text("rules: [{id: nope}]", encoding="utf-8")
    bad = runner.invoke(cli.app, ["rules", str(rules_dir)])
    assert bad.exit_code == 1 and "problem" in bad.output
