"""Surface finish, coating and heat-treatment checks on the title block and the notes (exact text)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import Finding, PageExtraction, TextItem

REVIEWER = "checks"
_REFERS_TO_NOTE = re.compile(r"\bREF\b|\bNOTE\b|\bSEE\b", re.IGNORECASE)
# Words that make a note a heat-treatment specification, not just its heading.
HEAT_TREATMENT_TERMS = (
    "harden", "tough", "temper", "anneal", "normali", "carburi", "nitrid", "case", "induction", "flame",
    "quench", "stress reliev", "HRC", "HRB", "HB", "HV",
)  # fmt: skip


def _term(term: str) -> re.Pattern[str]:
    """A rulebook term as a word-start pattern: 'tempering' matches TEMPERED, 'carburizing' CARBURISED."""
    stem = re.sub(r"(ing|ed|e)$", "", term.strip().lower())
    stem = re.escape(stem).replace("z", "[sz]").replace(r"\-", r"[\s-]?").replace(r"\ ", r"\s+")
    return re.compile(r"(?<![a-z])" + stem, re.IGNORECASE)


def _notes(page: PageExtraction) -> list[TextItem]:
    return page.notes


class NoteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str


@check("referenced_note_exists", NoteParams)
def referenced_note_exists(ctx: ReviewContext, rule: Rule, params: NoteParams) -> list[Finding]:
    """A title-block field that says 'REF NOTE' has its note: a note that actually specifies the treatment."""
    pages = [p for p in ev.title_block_pages(ctx) if _REFERS_TO_NOTE.search(ev.value(p, params.field) or "")]
    if not pages:
        raise NotApplicable(f"the {params.field.replace('_', ' ')} field does not refer to a note")
    terms = [_term(t) for t in HEAT_TREATMENT_TERMS]
    if any(any(t.search(n.text) for t in terms) for p in ctx.pages for n in _notes(p)):
        return []
    page = pages[0]
    name, value = params.field.replace("_", " "), ev.value(page, params.field)
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.field(page, params.field)],
            comment=f"The {name} field says {value!r}, but no note on the drawing specifies the treatment.",
            recommended_correction="Add the note the field refers to, or state the treatment in the field.",
        )
    ]


class HardeningParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    needs_prior_hardening: list[str]
    hardening_terms: list[str]


@check("hardened_only_treatments_have_hardening", HardeningParams)
def hardened_only_treatments_have_hardening(
    ctx: ReviewContext, rule: Rule, params: HardeningParams
) -> list[Finding]:
    """Tempering or sub-zero treatment is only defined for hardened steel: the part must also be hardened."""
    needs = [_term(t) for t in params.needs_prior_hardening]
    hardening = [_term(t) for t in params.hardening_terms]
    texts: list[tuple[PageExtraction, TextItem | None, str]] = []
    for p in ctx.pages:
        texts += [(p, n, n.text) for n in _notes(p)]
        if v := ev.value(p, "heat_treatment"):
            texts.append((p, None, v))
    asking = [(p, n, t) for p, n, t in texts if any(x.search(t) for x in needs)]
    if not asking:
        raise NotApplicable("no tempering or sub-zero treatment specified")
    # "hardened and tempered" names its hardening in the same words, so a hardening term anywhere counts
    if any(h.search(t) for _, _, t in texts for h in hardening):
        return []
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.text(p, n) if n else ev.field(p, "heat_treatment")],
            comment=f"{t.strip()!r} asks for a treatment that only follows hardening, but no hardening "
            "process is specified.",
            recommended_correction="Name the hardening process (e.g. hardened and tempered, toughened), or "
            "correct the treatment.",
        )
        for p, n, t in asking
    ]
