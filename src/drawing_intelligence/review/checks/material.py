"""Material checks on the title block and the template's '#' notes block."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference_p2 import Equivalents
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import Finding, PageExtraction, TextLine

REVIEWER = "checks"


def _norm(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _material_note(ctx: ReviewContext, page: PageExtraction) -> tuple[TextLine, str] | None:
    """The '# MATERIAL: ...' line of the notes block (the English one), with its value."""
    marker = ctx.template.notes_marker
    label = next((k for k, v in ctx.template.notes_fields.items() if v == "material"), None)
    if not marker or not label:
        return None
    mark = re.escape(marker)
    pattern = re.compile(rf"{mark}\s*{re.escape(label)}\s*:\s*([^{mark}]+)", re.IGNORECASE)
    for line in page.body_text:
        m = pattern.search(line.text)
        if m and m.group(1).strip():
            return line, m.group(1).strip()
    return None


@check("material_written_consistently")
def material_written_consistently(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """The title block and the notes block name the material the same way (punctuation and case aside)."""
    pairs = []
    for page in ev.title_block_pages(ctx):
        field = page.title_block_fields.get("material")
        note = _material_note(ctx, page)
        if field and field.source == "cell" and field.value and not ev.is_placeholder(field.value) and note:
            pairs.append((page, field.value, note))
    if not pairs:
        raise NotApplicable("the material is stated in one place only")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.field(page, "material"), ev.text(page, line)],
            comment=f"The title block says {value!r}, the notes {note_value!r}.",
            recommended_correction="Write the material the same way in both places.",
        )
        for page, value, (line, note_value) in pairs
        if _norm(value) != _norm(note_value)
    ]


class EquivalentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


@check("us_india_equivalent", EquivalentParams)
def us_india_equivalent(ctx: ReviewContext, rule: Rule, params: EquivalentParams) -> list[Finding]:
    """A US (or European) material designation the PARI equivalents list pairs with an Indian grade is shown
    with that Indian grade too. Only the list's literal grade pairs are used, never its prose rows."""
    table = ctx.reference.get(params.table)
    if not isinstance(table, Equivalents):
        raise NotCheckable(f"reference table {params.table!r} not loaded")
    pairs = [r for r in table.rows if r.automatic]
    texts = []
    for page in ctx.pages:
        if (v := ev.value(page, "material")) and not ev.is_placeholder(v):
            texts.append((page, v, ev.field(page, "material")))
        texts += [
            (page, ln.text, ev.text(page, ln)) for ln in page.body_text if re.search(r"MAT", ln.text, re.I)
        ]
    everything = _norm(" ".join(t for _, t, _ in texts))
    out, judged = [], False
    for row in pairs:
        hit = next(((p, t, e) for p, t, e in texts if _norm(row.us) in _norm(t)), None)
        if hit is None:
            continue
        judged = True
        if _norm(row.india) not in everything:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[hit[2]],
                    comment=f"The material {hit[1].strip()!r} is a US designation; PARI's equivalents list "
                    "gives "
                    f"{row.india} as the Indian grade, which the drawing does not show.",
                    recommended_correction=f"Add the Indian equivalent, e.g. '{row.us} ({row.india})'.",
                )
            )
    if not judged:
        raise NotApplicable("no material on PARI's US-India equivalents list")
    return out
