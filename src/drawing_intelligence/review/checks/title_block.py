"""Title-block checks, on the fields stage 1 reads by position (exact text, no LLM)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.extraction.template import resolve_rect
from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._geometry import drawn_dimensions, supported_scales
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
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


class DateFieldsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[str]


@check("dates_valid", DateFieldsParams)
def dates_valid(ctx: ReviewContext, rule: Rule, params: DateFieldsParams) -> list[Finding]:
    """The listed date fields are filled with a date in the template's format."""
    out = []
    for page in ev.title_block_pages(ctx):
        for name in params.fields:
            value = ev.value(page, name)
            if _missing(value, []):
                problem = "is empty"
            elif ctx.parse_date(value) is None:
                problem = f"says {value!r}, not a date in the {ctx.template.date_format} format"
            else:
                continue
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.field(page, name)],
                    comment=f"The {name.replace('_', ' ')} field {problem}.",
                    recommended_correction="Enter the date.",
                )
            )
    return out


_SHEET = re.compile(r"^\s*(\d+)\s*OF\s*(\d+)\s*$", re.IGNORECASE)


@check("sheet_numbering")
def sheet_numbering(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """'Sheet x of y' is consistent: x within 1..y, and the sheets in one file numbered in order."""
    pages = [(p, _SHEET.match(ev.value(p, "sheet") or "")) for p in ev.title_block_pages(ctx)]
    read = [(p, int(m[1]), int(m[2])) for p, m in pages if m]
    if not read:
        raise NotCheckable("no 'sheet x of y' field read")
    out = []
    for i, (page, x, y) in enumerate(read):
        prev = read[i - 1] if i else None
        if not 1 <= x <= y:
            problem = f"says sheet {x} of {y}"
        elif prev and (x != prev[1] + 1 or y != prev[2]):
            problem = f"says sheet {x} of {y} after sheet {prev[1]} of {prev[2]}"
        else:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.field(page, "sheet")],
                comment=f"The sheet field {problem}.",
                recommended_correction="Correct the sheet numbering.",
            )
        )
    return out


# ISO 216 sheet sizes in PDF points (short side, long side).
SHEET_SIZES = {
    "A4": (595, 842),
    "A3": (842, 1191),
    "A2": (1191, 1684),
    "A1": (1684, 2384),
    "A0": (2384, 3370),
}


@check("sheet_size_matches_page")
def sheet_size_matches_page(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """The sheet size in the title block is the size of the page it is printed on."""
    out = []
    checked = False
    for page in ev.title_block_pages(ctx):
        stated = (ev.value(page, "sheet_size") or "").strip().upper()
        if stated not in SHEET_SIZES:
            continue
        checked = True
        short, long = sorted(page.page_size_pts)
        es, el = SHEET_SIZES[stated]
        if abs(short - es) <= 0.03 * es and abs(long - el) <= 0.03 * el:
            continue
        actual = next(
            (
                n
                for n, (s, ln) in SHEET_SIZES.items()
                if abs(short - s) <= 0.03 * s and abs(long - ln) <= 0.03 * ln
            ),
            f"{page.page_size_pts[0]:.0f} x {page.page_size_pts[1]:.0f} pt",
        )
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.field(page, "sheet_size")],
                comment=f"The title block says {stated}, but the sheet is {actual}.",
                recommended_correction="Use the template for the sheet size, or correct the field.",
            )
        )
    if not checked:
        raise NotCheckable("no standard sheet size (A0-A4) read from the title block")
    return out


class TemplateTextParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().upper()


@check("template_text_present", TemplateTextParams)
def template_text_present(ctx: ReviewContext, rule: Rule, params: TemplateTextParams) -> list[Finding]:
    """The template's ownership note is on the drawing (it is printed with the title block)."""
    # the note is printed over two lines, so look for its distinctive words, not the joined text
    words = set(re.findall(r"[A-Z]{4,}", params.text.upper()))
    for page in ctx.pages:
        lines = [*page.title_block_text, *page.body_text, *page.tolerance_table_text]
        found = {w for t in lines for w in re.findall(r"[A-Z]{4,}", t.text.upper())}
        if words <= found:
            return []
    page = ctx.pages[0]
    w, h = page.page_size_pts
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[
                EvidenceRef(kind="region", page=page.page_number, bbox=[0, 0, w, h], provenance="pdf_text")
            ],
            comment=f"The note '{params.text}' is not on the drawing.",
            recommended_correction="Use the company template, which carries the note.",
        )
    ]


@check("revision_sequence")
def revision_sequence(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """The revision table's numbers run 1, 2, 3 ... with no gap or repeat."""
    pages = [p for p in ctx.pages if p.revision_numbers]
    if not pages:
        raise NotApplicable("no revision rows")
    out = []
    for page in pages:
        numbers = sorted(int(n.text) for n in page.revision_numbers)
        if numbers != list(range(1, len(numbers) + 1)):
            table = _revision_table(ctx, page)
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[table] if table else [ev.field(page, "revision")],
                    comment=f"The revision table numbers its rows {', '.join(map(str, numbers))}.",
                    recommended_correction="Number the revisions 1, 2, 3 ... without gaps or repeats.",
                )
            )
    return out


class SheetsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_sheets: int = 2


def _across_sheets(
    ctx: ReviewContext, rule: Rule, params: SheetsParams, name: str, what: str
) -> list[Finding]:
    pages = [p for p in ev.title_block_pages(ctx) if ev.value(p, name)]
    if len(ctx.pages) < params.min_sheets:
        raise NotApplicable("a single sheet")
    if len(pages) < 2:
        raise NotCheckable(f"the {what} was read on fewer than two sheets")
    first = ev.value(pages[0], name)
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.field(pages[0], name), ev.field(p, name)],
            comment=f"Sheet {p.page_number} has {what} {ev.value(p, name)!r}, sheet {pages[0].page_number} "
            f"{first!r}.",
            recommended_correction=f"Give every sheet the same {what}.",
        )
        for p in pages[1:]
        if _squash(ev.value(p, name) or "") != _squash(first or "")
    ]


@check("sheets_same_revision", SheetsParams)
def sheets_same_revision(ctx: ReviewContext, rule: Rule, params: SheetsParams) -> list[Finding]:
    """All sheets of a multi-sheet drawing carry the same revision."""
    return _across_sheets(ctx, rule, params, "revision", "revision")


@check("sheets_same_size", SheetsParams)
def sheets_same_size(ctx: ReviewContext, rule: Rule, params: SheetsParams) -> list[Finding]:
    """All sheets of a multi-sheet drawing are the same size."""
    return _across_sheets(ctx, rule, params, "sheet_size", "sheet size")
