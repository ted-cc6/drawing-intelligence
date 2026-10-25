"""The `checks` reviewer: runs every code and lookup rule's check function and records each rule's status."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping

from drawing_intelligence.review.checks import CheckSpec, NotApplicable, NotCheckable, registered
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule
from drawing_intelligence.schemas import Finding, ReviewerOutput, RuleStatus

log = logging.getLogger(__name__)
REVIEWER = "checks"


def _status(rule: Rule, findings: list[Finding]) -> RuleStatus:
    if not findings:
        return RuleStatus(rule_id=rule.id, status="pass")
    worst = "fail" if any(f.result == "fail" for f in findings) else "warning"
    return RuleStatus(rule_id=rule.id, status=worst, finding_ids=[f.id for f in findings])


def run_rule(ctx: ReviewContext, rule: Rule, spec: CheckSpec | None) -> tuple[list[Finding], RuleStatus]:
    """One rule's findings and status. A check that crashes never stops the review: it is `not_checked`."""
    if not rule.applies(ctx.part_family, ctx.drawing_type):
        return [], RuleStatus(rule_id=rule.id, status="not_applicable", note="outside the rule's applies_to")
    if spec is None:
        return [], RuleStatus(rule_id=rule.id, status="not_checked", note=f"check {rule.check!r} not built")
    try:
        findings = spec.fn(ctx, rule, spec.params.model_validate(rule.params))
        wrong = [f.id for f in findings if f.rule_id != rule.id]
        if wrong:
            raise ValueError(f"check {spec.name!r} returned findings for another rule: {wrong}")
    except NotApplicable as e:
        return [], RuleStatus(rule_id=rule.id, status="not_applicable", note=str(e) or None)
    except NotCheckable as e:
        return [], RuleStatus(rule_id=rule.id, status="not_checked", note=str(e) or None)
    except Exception as e:  # a broken check is a bug to fix, not a reason to lose the whole review
        log.exception("check %s failed on rule %s", spec.name, rule.id)
        return [], RuleStatus(rule_id=rule.id, status="not_checked", note=f"error: {type(e).__name__}: {e}")
    unique = list({f.id: f for f in findings}.values())  # the same issue reported twice is one finding
    return unique, _status(rule, unique)


def run_checks(ctx: ReviewContext, checks: Mapping[str, CheckSpec] | None = None) -> ReviewerOutput:
    """Every code and lookup rule of the rulebook, in rulebook order. LLM rules belong to other reviewers."""
    specs = registered() if checks is None else checks
    start = time.perf_counter()
    findings: list[Finding] = []
    statuses: list[RuleStatus] = []
    for rule in ctx.rulebook.rules:
        if rule.check_type == "llm":
            continue
        found, status = run_rule(ctx, rule, specs.get(rule.check or ""))
        findings += found
        statuses.append(status)
    return ReviewerOutput(
        reviewer=REVIEWER,
        findings=findings,
        rule_statuses=statuses,
        latency_s=round(time.perf_counter() - start, 3),
    )
