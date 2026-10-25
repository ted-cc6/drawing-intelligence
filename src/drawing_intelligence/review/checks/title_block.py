"""Title-block checks, on the fields stage 1 reads by position (exact text, no LLM)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.extraction.template import resolve_rect
from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._geometry import drawn_dimensions, supported_scales
from drawing_intelligence.review.checks._registry import NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, PageExtraction

REVIEWER = "checks"
_RATIO = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*$")
_SCALE_LABEL = re.compile(r"SCALE\s*(\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?)", re.IGNORECASE)


class FieldParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    placeholder_ok: list[str] = []  # placeholders that are a real answer for this field ("N.A." = none)
    must_contain: list[str] = []  # the value must contain one of these (e.g. IS 2102)


def _missing(value: str | None, placeholder_ok: list[str]) -> bool:
    if not value:
        return True
    return ev.is_placeholder(value) and value not in placeholder_ok


@check("title_block_field", FieldParams)
def title_block_field(ctx: ReviewContext, rule: Rule, params: FieldParams) -> list[Finding]:
    """The field is filled (a bare placeholder only counts if the rule accepts it) and says what it must."""
    out = []
    for page in ev.title_block_pages(ctx):
        value = ev.value(page, params.field)
        if _missing(value, params.placeholder_ok):
            shown = f"only {value!r}" if value else "empty"
            comment, fix = f"The {params.field.replace('_', ' ')} field is {shown}.", "Fill in the field."
        elif params.must_contain and not any(m.lower() in (value or "").lower() for m in params.must_contain):
            wanted = " or ".join(params.must_contain)
            comment = f"The {params.field.replace('_', ' ')} field says {value!r}, not {wanted}."
            fix = f"State {params.must_contain[0]}."
        else:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.field(page, params.field)],
                comment=comment,
                recommended_correction=fix,
            )
        )
    return out


class PatternParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    pattern: str | None = None  # a full-match regex; None until PARI agrees its numbering format


@check("title_block_pattern", PatternParams)
def title_block_pattern(ctx: ReviewContext, rule: Rule, params: PatternParams) -> list[Finding]:
    """The field is filled and, when the rule gives a pattern, follows it."""
    out = []
    for page in ev.title_block_pages(ctx):
        value = ev.value(page, params.field)
        if _missing(value, []):
            comment = f"The {params.field.replace('_', ' ')} field is empty."
        elif params.pattern and not re.fullmatch(params.pattern, value or ""):
            comment = f"{value!r} does not follow the required format {params.pattern!r}."
        else:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.field(page, params.field)],
                comment=comment,
                recommended_correction=f"Enter the {params.field.replace('_', ' ')} in the company format.",
            )
        )
    return out


@check("dates_in_order")
def dates_in_order(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Checked and approved are not dated before drawn (dates in the template's format, day/month/year)."""
    out = []
    checked_any = False
    for page in ev.title_block_pages(ctx):
        drawn = ctx.parse_date(ev.value(page, "drawn_date"))
        if drawn is None:
            continue
        for name in ("checked_date", "approved_date"):
            later = ctx.parse_date(ev.value(page, name))
            if later is None:
                continue
            checked_any = True
            if later < drawn:
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[ev.field(page, name), ev.field(page, "drawn_date")],
                        comment=f"{name.replace('_', ' ').capitalize()} {ev.value(page, name)} is before the "
                        f"drawn date {ev.value(page, 'drawn_date')}.",
                        recommended_correction="Correct the dates: checking and approval come after drawing.",
                    )
                )
    if not checked_any:
        raise NotCheckable(
            f"no drawn date with a checked or approved date in the format {ctx.template.date_format}"
        )
    return out


def _ratio_text(factor: float) -> str:
    return f"{factor:g} : 1" if factor >= 1 else f"1 : {1 / factor:g}"


def _ratio(text: str) -> float | None:
    m = _RATIO.match(text)
    return float(m[1]) / float(m[2]) if m and float(m[2]) else None


@check("scale_consistent")
def scale_consistent(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """The title-block scale is one the views state; with no view labels, one the dimensions are drawn at.

    Views at other scales (a detail at 2:1) are fine: only a stated scale nothing on the sheet uses is wrong.
    """
    out = []
    checked_any = False
    for page in ev.title_block_pages(ctx):
        stated = ev.value(page, "scale")
        factor = _ratio(stated or "")
        if factor is None:
            continue
        labels = [
            (item, _ratio(m))
            for item in page.view_labels
            for m in _SCALE_LABEL.findall(item.text)
            if _ratio(m)
        ]
        if labels:
            checked_any = True
            if any(abs(f - factor) < 1e-6 for _, f in labels if f):
                continue
            evidence: list[EvidenceRef] = [
                ev.field(page, "scale"),
                *(ev.text(page, item) for item, _ in labels),
            ]
            seen = ", ".join(sorted({item.text for item, _ in labels}))
            comment = f"The title block says scale {stated}, but the views say {seen}."
        elif scales := supported_scales(drawn_dimensions(page)):
            checked_any = True
            if any(abs(s / factor - 1) <= 0.01 for s in scales):
                continue
            main, on = max(scales.items(), key=lambda kv: len(kv[1]))
            evidence = [ev.field(page, "scale"), *(ev.dimension(page, d.dim) for d in on[:3])]
            comment = (
                f"The title block says scale {stated}, but {len(on)} dimensions are drawn at "
                f"{_ratio_text(main)} and none at {stated}."
            )
        else:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=evidence,
                comment=comment,
                recommended_correction="Make the title-block scale match the main view's scale.",
            )
        )
    if not checked_any:
        raise NotCheckable("no readable scale in the title block, or nothing to compare it with")
    return out


def _revision_table(ctx: ReviewContext, page: PageExtraction) -> EvidenceRef | None:
    if ctx.template.revision_rows is None:
        return None
    w, h = page.page_size_pts
    return EvidenceRef(
        kind="region",
        page=page.page_number,
        bbox=[round(v, 1) for v in resolve_rect(ctx.template.revision_rows, w, h)],
        provenance="pdf_text",
    )


@check("revision_matches_table")
def revision_matches_table(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """The title-block revision is present and equals the latest revision-table row (no rows -> 0)."""
    out = []
    checked_any = False
    for page in ev.title_block_pages(ctx):
        rev = ev.value(page, "revision")
        latest = max((int(n.text) for n in page.revision_numbers), default=0)
        table = _revision_table(ctx, page)
        if _missing(rev, []):
            checked_any = True
            comment = "The revision field is empty."
        elif rev and rev.strip().isdigit():
            checked_any = True
            if int(rev) == latest:
                continue
            rows = f"its latest row is revision {latest}" if page.revision_numbers else "it has no rows"
            comment = f"The title block says revision {rev}, but the revision table {rows}."
        else:
            continue  # a letter revision (A, B): not this template's convention, so not compared
        evidence = [ev.field(page, "revision"), *([table] if table else [])]
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=evidence,
                comment=comment,
                recommended_correction="Add the revision-table row for this revision, or correct it.",
            )
        )
    if not checked_any:
        raise NotCheckable("the revision is not a number")
    return out


class BlankParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[str]


@check("fields_blank_at_submission", BlankParams)
def fields_blank_at_submission(ctx: ReviewContext, rule: Rule, params: BlankParams) -> list[Finding]:
    """Sign-off fields are still blank when a drawing enters review (pre-signed drawings bypass the check)."""
    out = []
    for page in ev.title_block_pages(ctx):
        filled = [n for n in params.fields if not _missing(ev.value(page, n), [])]
        if filled:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.field(page, n) for n in filled],
                    comment="Already filled at submission: "
                    + ", ".join(n.replace("_", " ") for n in filled)
                    + ".",
                    recommended_correction="Leave sign-off fields blank until the drawing has been checked.",
                )
            )
    return out
