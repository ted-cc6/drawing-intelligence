"""Stage 4: no finding reaches the report unless its evidence exists on the drawing (ADR 0010).

Reads every reviewer's output and:
1. drops a finding whose evidence does not resolve (an unknown id, page, rule or title-block field, a bbox off
   the sheet, or a quote that is not what the drawing says), keeping each drop with its reason;
2. merges duplicates (same finding id = same rule on the same evidence; ADR 0008);
3. gives every rule in the rulebook exactly one status.
All of this is code: it catches invented findings at no LLM cost.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from drawing_intelligence.review.reviewers import PLANNED_REVIEWERS
from drawing_intelligence.review.rulebook import Rulebook
from drawing_intelligence.schemas import (
    DrawingKnowledge,
    EvidenceRef,
    Extraction,
    Finding,
    PageExtraction,
    RejectedFinding,
    ReviewerOutput,
    ReviewResult,
    RuleStatus,
    TitleBlock,
)
from drawing_intelligence.schemas.review import RejectReason

BBOX_SLACK_PTS = 1.0
_ORDER = {"fail": 0, "warning": 1, "not_applicable": 2, "not_checked": 2, "pass": 3}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _page_texts(page: PageExtraction) -> list[str]:
    lines = [*page.title_block_text, *page.tolerance_table_text, *page.body_text]
    items = [*page.dimensions, *page.view_labels, *page.notes, *page.other_numeric]
    return [_norm(t.text) for t in [*lines, *items]] + [
        _norm(f.value) for f in page.title_block_fields.values() if f.value
    ]


class _Unresolved(Exception):
    def __init__(self, reason: RejectReason, detail: str):
        super().__init__(detail)
        self.reason: RejectReason = reason
        self.detail = detail


def _check(
    e: EvidenceRef, pages: dict[int, PageExtraction], knowledge: Mapping[int, DrawingKnowledge | None]
) -> None:
    page = pages.get(e.page)
    if page is None:
        raise _Unresolved("unknown_page", f"page {e.page} is not in the drawing")
    if e.bbox is not None:
        w, h = page.page_size_pts
        x0, y0, x1, y1 = e.bbox
        s = BBOX_SLACK_PTS
        if x0 < -s or y0 < -s or x1 > w + s or y1 > h + s or x1 < x0 or y1 < y0:
            raise _Unresolved("bbox_off_sheet", f"bbox {e.bbox} is not on the {w:g}x{h:g} pt sheet")
    k = knowledge.get(e.page)
    exact = e.provenance == "pdf_text" and e.quote is not None
    if e.kind == "dimension":
        dims = {d.id: d for d in page.dimensions if d.id}
        if e.ref in dims:
            if exact and _norm(e.quote or "") != _norm(dims[e.ref].text):
                raise _Unresolved("quote_mismatch", f"{e.ref} reads {dims[e.ref].text!r}, not {e.quote!r}")
        elif not (k and any(d.id == e.ref for d in k.dimensions)):
            raise _Unresolved("unknown_ref", f"no dimension {e.ref} on page {e.page}")
    elif e.kind == "symbol":
        read = {s.id: s for s in page.symbols}  # stage 1's exact symbols (S1...)
        if e.ref in read:
            if exact and _norm(e.quote or "") != _norm(read[e.ref].text):
                raise _Unresolved("quote_mismatch", f"{e.ref} reads {read[e.ref].text!r}, not {e.quote!r}")
        elif not (k and any(s.id == e.ref for s in k.symbols)):
            raise _Unresolved("unknown_ref", f"no symbol {e.ref} on page {e.page}")
    elif e.kind == "note":
        if not (k and any(n.id == e.ref for n in k.notes)):
            raise _Unresolved("unknown_ref", f"no note {e.ref} on page {e.page}")
    elif e.kind == "title_block":
        field = page.title_block_fields.get(e.ref or "")
        if field is None and e.ref not in TitleBlock.model_fields:
            raise _Unresolved("unknown_title_block_field", f"no title-block field {e.ref!r}")
        if field is not None and exact and _norm(e.quote or "") != _norm(field.value or ""):
            raise _Unresolved("quote_mismatch", f"{e.ref} reads {field.value!r}, not {e.quote!r}")
    elif e.kind == "text" and exact:
        quote = _norm(e.quote or "")
        if not any(quote in t for t in _page_texts(page)):
            raise _Unresolved("quote_mismatch", f"{e.quote!r} is not on page {e.page}")


def check_finding(
    f: Finding,
    rulebook: Rulebook,
    pages: dict[int, PageExtraction],
    knowledge: Mapping[int, DrawingKnowledge | None],
) -> RejectedFinding | None:
    """None if every citation resolves, else why the finding is dropped."""
    if f.rule_id is not None and f.rule_id not in {r.id for r in rulebook.rules}:
        return RejectedFinding(
            finding=f, reason="unknown_rule", detail=f"no rule {f.rule_id} in the rulebook"
        )
    for e in f.evidence:
        try:
            _check(e, pages, knowledge)
        except _Unresolved as u:
            return RejectedFinding(finding=f, reason=u.reason, detail=u.detail)
    return None


def _reviewer_order(o: ReviewerOutput) -> tuple[int, str]:
    return (
        PLANNED_REVIEWERS.index(o.reviewer) if o.reviewer in PLANNED_REVIEWERS else len(PLANNED_REVIEWERS),
        o.reviewer,
    )


def verify(
    outputs: list[ReviewerOutput],
    extraction: Extraction,
    rulebook: Rulebook,
    knowledge: Mapping[int, DrawingKnowledge | None] | None = None,
    skipped: list[str] | None = None,
) -> tuple[ReviewResult, list[RejectedFinding]]:
    """The review result of one drawing, and the findings dropped on the way.

    Outputs are read in reviewer order, so the result does not depend on which parallel node finished first.
    """
    knowledge = knowledge or {}
    pages = {p.page_number: p for p in extraction.pages}
    outputs = sorted(outputs, key=_reviewer_order)
    kept: dict[str, Finding] = {}
    raised_by: dict[str, list[str]] = {}
    rejected: list[RejectedFinding] = []
    for out in outputs:
        for f in out.findings:
            if f.id in kept:
                raised_by[f.id].append(out.reviewer)
                continue
            drop = check_finding(f, rulebook, pages, knowledge)
            if drop:
                rejected.append(drop)
            else:
                kept[f.id] = f
                raised_by[f.id] = [out.reviewer]
    findings = []
    for fid, f in kept.items():
        others = sorted(set(raised_by[fid]) - {f.reviewer})
        findings.append(
            f.model_copy(update={"comment": f"{f.comment} (also raised by {', '.join(others)})"})
            if others
            else f
        )

    reported: dict[str, RuleStatus] = {}
    for out in outputs:
        for s in out.rule_statuses:
            if s.rule_id not in reported or _ORDER[s.status] < _ORDER[reported[s.rule_id].status]:
                reported[s.rule_id] = s
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        if f.rule_id:
            by_rule.setdefault(f.rule_id, []).append(f)
    errors = {o.reviewer: o.error for o in outputs if o.error}
    statuses = []
    for rule in rulebook.rules:
        mine = by_rule.get(rule.id, [])
        if mine:
            worst = "fail" if any(f.result == "fail" for f in mine) else "warning"
            statuses.append(RuleStatus(rule_id=rule.id, status=worst, finding_ids=[f.id for f in mine]))
            continue
        s = reported.get(rule.id)
        if s is None:
            statuses.append(
                RuleStatus(rule_id=rule.id, status="not_checked", note="its reviewer did not run")
            )
        elif s.status in ("fail", "warning"):
            statuses.append(
                RuleStatus(rule_id=rule.id, status="not_checked", note="its findings were rejected")
            )
        else:
            statuses.append(s)

    ran = [o.reviewer for o in outputs if not o.error]
    result = ReviewResult(
        source_file=extraction.source_file,
        rulebook_version=rulebook.version,
        reviewers_run=ran,
        reviewers_skipped=sorted(set(skipped or []) | set(errors)),
        findings=findings,
        rule_statuses=statuses,
        cost_usd=round(sum(o.cost_usd for o in outputs), 6),
        latency_s=round(sum(o.latency_s for o in outputs), 3),
        extra={"rejected": len(rejected), **({"reviewer_errors": errors} if errors else {})},
    )
    return result, rejected
