"""Stages 3-5: the review contracts shared by every reviewer, the verifier, the eval and the report.

The trust rules from the spikes are enforced here, not left to each reviewer:
- an LLM finding is at most a *warning*, never a *fail* (Spike E: precision 32-61%, risk R4);
- severity comes from the rulebook, never from a model (Spike E: the model rated a benign heat treatment
  Critical). A finding without a rule is a warning with severity `info`;
- a *fail* must rest on exact evidence - the PDF text layer or vector geometry - never on vision alone
  (Spike D: vision found 0/32 finish marks and 0/9 datum flags, risk R5).

Findings are issues only. Whether each rule passed is reported separately in `RuleStatus`, so the report can
show the client's Pass/Fail column without inventing "pass" findings.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REVIEW_SCHEMA_VERSION = "1.1"  # 1.1: ReviewerOutput and RejectedFinding (ADR 0010)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# The client's checklist categories (data/client_set/Check List.docx), plus the three the review adds:
# consistency (arithmetic/duplicates, code), manufacturability and design intent (Spike E, J5/J6).
# "Common rejection conditions" is not a category: such rules are `critical` rules in their own category.
Category = Literal[
    "title_block",
    "material",
    "tolerance",
    "gdt",
    "datum",
    "thread_weld",
    "surface_treatment",  # surface finish / coating / heat treatment
    "inspection",
    "consistency",
    "manufacturability",
    "design_intent",
]
CATEGORY_LABELS: dict[str, str] = {
    "title_block": "Title block",
    "material": "Material",
    "tolerance": "Tolerance",
    "gdt": "GD&T",
    "datum": "Datum scheme",
    "thread_weld": "Thread / weld callout",
    "surface_treatment": "Surface finish / coating / heat treatment",
    "inspection": "Inspection",
    "consistency": "Consistency",
    "manufacturability": "Manufacturability",
    "design_intent": "Design intent",
}

# Provisional until the client confirms its own levels.
Severity = Literal["critical", "major", "minor", "info"]

# Who produced a finding. Equals the `check_type` of the rule that was checked.
Source = Literal["code", "lookup", "llm"]

# Where a piece of evidence was read from. Only `pdf_text` and `vector` are exact.
Provenance = Literal["pdf_text", "vector", "vision"]
EXACT_PROVENANCE: frozenset[str] = frozenset({"pdf_text", "vector"})

EvidenceKind = Literal["dimension", "symbol", "note", "title_block", "text", "region"]


class EvidenceRef(_Strict):
    """One thing on the drawing that a finding points at. The verifier checks that it resolves."""

    kind: EvidenceKind
    ref: str | None = Field(
        default=None,
        description="id in the drawing JSON (D3, V1, S2, N1) or the title-block field name (material)",
    )
    page: int = Field(ge=1)
    bbox: list[float] | None = Field(default=None, description="[x0, y0, x1, y1] in PDF points")
    quote: str | None = Field(default=None, description="the text exactly as printed")
    provenance: Provenance

    @model_validator(mode="after")
    def _points_at_something(self) -> EvidenceRef:
        if self.kind in ("dimension", "symbol", "note", "title_block") and not self.ref:
            raise ValueError(f"{self.kind} evidence needs a ref (an id or a title-block field)")
        if self.kind == "text" and not self.quote:
            raise ValueError("text evidence needs the quoted text")
        if self.kind == "region" and not self.bbox:
            raise ValueError("region evidence needs a bbox")
        if self.bbox is not None and len(self.bbox) != 4:
            raise ValueError("bbox must be [x0, y0, x1, y1]")
        return self

    def key(self) -> str:
        """What identifies this evidence for a stable finding id (wording and bbox jitter excluded)."""
        return f"{self.page}:{self.kind}:{self.ref or self.quote or ''}"


def finding_id(rule_id: str | None, category: str, requirement: str, evidence: list[EvidenceRef]) -> str:
    """Deterministic id: the same rule on the same evidence gives the same id on every run.

    That is what lets the eval match findings across runs, the verifier drop duplicates, and an engineer's
    accept/reject attach to a finding the next time the drawing is reviewed.
    """
    anchor = rule_id or f"{category}:{requirement.strip().lower()}"
    raw = anchor + "|" + "|".join(sorted(e.key() for e in evidence))
    return "F-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


class Finding(_Strict):
    """One issue on the drawing, in the client's checklist columns."""

    id: str = Field(default="", description="set automatically from rule + evidence; see finding_id()")
    rule_id: str | None
    category: Category
    requirement: str
    result: Literal["fail", "warning"]
    severity: Severity
    evidence: list[EvidenceRef] = Field(min_length=1)
    comment: str
    recommended_correction: str | None = None
    reviewer: str = Field(description="the reviewer node that produced it, e.g. consistency")
    source: Source

    @model_validator(mode="after")
    def _trust_rules(self) -> Finding:
        if self.source == "llm" and self.result == "fail":
            raise ValueError("an LLM finding can only be a warning (Spike E, R4)")
        if self.rule_id is None and (self.result == "fail" or self.severity != "info"):
            raise ValueError("a finding without a rule must be a warning with severity info")
        if self.result == "fail":
            inexact = [e.key() for e in self.evidence if e.provenance not in EXACT_PROVENANCE]
            if inexact:
                raise ValueError(f"a fail must rest on pdf_text or vector evidence; vision-only: {inexact}")
        expected = finding_id(self.rule_id, self.category, self.requirement, self.evidence)
        if self.id and self.id != expected:
            raise ValueError(f"finding id {self.id} does not match its rule and evidence ({expected})")
        self.id = expected
        return self


RuleOutcome = Literal["pass", "fail", "warning", "not_applicable", "not_checked"]


class RuleStatus(_Strict):
    """How one rule came out on this drawing: one row of the report's Pass/Fail column."""

    rule_id: str
    status: RuleOutcome
    finding_ids: list[str] = []
    note: str | None = None

    @model_validator(mode="after")
    def _findings_match_status(self) -> RuleStatus:
        if self.status in ("fail", "warning") and not self.finding_ids:
            raise ValueError(f"rule {self.rule_id} is {self.status} but cites no finding")
        if self.status not in ("fail", "warning") and self.finding_ids:
            raise ValueError(f"rule {self.rule_id} is {self.status} but cites findings")
        return self


class FindingFeedback(_Strict):
    """An engineer's accept/reject of a finding. Session data: the comment may quote the drawing."""

    finding_id: str
    decision: Literal["accept", "reject"]
    comment: str | None = None
    role: Literal["checker", "designer", "rulebook_owner"] | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewerOutput(_Strict):
    """What one reviewer node saves (`review/<reviewer>.json`): its findings and the status of its own rules.

    The verifier reads every reviewer's output and sets the final rule statuses (ADR 0010).
    """

    schema_version: Literal["1.0", "1.1"] = REVIEW_SCHEMA_VERSION
    reviewer: str
    findings: list[Finding] = []
    rule_statuses: list[RuleStatus] = []
    cost_usd: float = 0.0
    latency_s: float = 0.0
    error: str | None = Field(
        default=None, description="set when the reviewer crashed; its rules are not_checked"
    )


RejectReason = Literal[
    "unknown_rule",
    "unknown_ref",
    "unknown_page",
    "bbox_off_sheet",
    "quote_mismatch",
    "unknown_title_block_field",
]


class RejectedFinding(_Strict):
    """A finding the verifier dropped, and why: kept for debugging, never shown as a result."""

    finding: Finding
    reason: RejectReason
    detail: str


class ReviewResult(BaseModel):
    """What the review workflow saves for one drawing (all pages)."""

    schema_version: Literal["1.0", "1.1"] = REVIEW_SCHEMA_VERSION
    source_file: str
    rulebook_version: str
    reviewers_run: list[str] = []
    reviewers_skipped: list[str] = []
    findings: list[Finding] = []
    rule_statuses: list[RuleStatus] = []
    cost_usd: float = 0.0
    latency_s: float = 0.0
    extra: dict[str, Any] = {}

    @model_validator(mode="after")
    def _consistent(self) -> ReviewResult:
        ids = [f.id for f in self.findings]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate findings (merge them before saving): {dupes}")
        known = set(ids)
        for s in self.rule_statuses:
            missing = [i for i in s.finding_ids if i not in known]
            if missing:
                raise ValueError(f"rule {s.rule_id} cites unknown findings {missing}")
        rules = [s.rule_id for s in self.rule_statuses]
        if len(rules) != len(set(rules)):
            raise ValueError("a rule has more than one status")
        return self

    def by_severity(self) -> list[Finding]:
        order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
        return sorted(self.findings, key=lambda f: (f.result != "fail", order[f.severity], f.category))
