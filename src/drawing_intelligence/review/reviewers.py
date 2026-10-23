"""Which reviewer runs which rules (ADR 0010): split by how a rule is checked, not by its category.

- `checks` (code) runs every `code` and `lookup` rule.
- Three LLM reviewers run the `llm` rules, chosen by the rule's category below.
"""

from __future__ import annotations

from drawing_intelligence.review.rulebook import Rule

CHECKS = "checks"

LLM_REVIEWER_FOR_CATEGORY: dict[str, str] = {
    "consistency": "drawing_practice",
    "datum": "drawing_practice",
    "thread_weld": "drawing_practice",
    "inspection": "drawing_practice",
    "manufacturability": "manufacturability",
    "design_intent": "design_intent",
    "surface_treatment": "design_intent",
}

# Every reviewer the workflow will have, in the order the verifier reads their outputs.
PLANNED_REVIEWERS: tuple[str, ...] = (CHECKS, "drawing_practice", "manufacturability", "design_intent")

# The ones built so far; the others are listed as skipped in every review result.
BUILT_REVIEWERS: tuple[str, ...] = (CHECKS,)


def reviewer_for(rule: Rule) -> str:
    if rule.check_type != "llm":
        return CHECKS
    try:
        return LLM_REVIEWER_FOR_CATEGORY[rule.category]
    except KeyError as e:
        raise KeyError(f"no LLM reviewer for category {rule.category!r} (rule {rule.id})") from e
