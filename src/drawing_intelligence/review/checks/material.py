"""Material checks on the title block and the template's '#' notes block."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks import _process as pr
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference_des11 import MaterialHeatTreatment
from drawing_intelligence.review.reference_p2 import Equivalents, StockTable
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


def _grade(text: str) -> str:
    """En-8(D) -> EN8D, EN 24 -> EN24."""
    return _norm(re.sub(r"[()]", "", text))


@check("material_for_size", EquivalentParams)
def material_for_size(ctx: ReviewContext, rule: Rule, params: EquivalentParams) -> list[Finding]:
    """A round bar named in a stock note ("USE STD. Ø35 En-8(D) BRIGHT BAR") follows DES-11's selection: EN9
    (C45 / C55 / En8D) up to Ø32, EN24 above. Bars of other grades are not judged."""
    table = ctx.reference.get(params.table)
    if not isinstance(table, MaterialHeatTreatment):
        raise NotCheckable(f"reference table {params.table!r} not loaded")
    stock = pr.stock_notes(ctx)
    if not stock:
        raise NotApplicable("no stock note names a round bar")
    out = []
    for s in stock:
        rows = {r.key for r in table.candidates(_grade(s.material)) if r.key in {"EN9", "EN24"}}
        if len(rows) != 1:
            continue
        preferred = table.preferred_round_grade(s.diameter_mm)
        if preferred not in rows:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[s.evidence],
                    comment=f"A Ø{s.diameter_mm:g} bar in {s.material} ({next(iter(rows))}): PARI's DES-11 "
                    f"selects "
                    f"{preferred} for this size (EN9 up to Ø32, EN24 above).",
                    recommended_correction=f"Use {preferred}, or note why this grade is needed.",
                )
            )
    return out


class StockParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    allowance_mm: float = 0


@check("stock_size_available", StockParams)
def stock_size_available(ctx: ReviewContext, rule: Rule, params: StockParams) -> list[Finding]:
    """A bar size named in a stock note is one PARI's raw-material list stocks for that material (India raw
    material sizes, round). Materials the list does not hold are not judged."""
    table = ctx.reference.get(params.table)
    if not isinstance(table, StockTable):
        raise NotCheckable(f"reference table {params.table!r} not loaded")
    stock = pr.stock_notes(ctx)
    if not stock:
        raise NotApplicable("no stock note names a bar size")
    out = []
    for s in stock:
        grade = _grade(s.material)
        rows = [
            r
            for r in table.rows
            if r.form == "round" and _norm(r.material) and grade.startswith(_norm(r.material))
        ]
        if not rows:
            continue
        row = max(rows, key=lambda r: len(r.material))  # EN8 for En-8(D), not a shorter name
        if s.diameter_mm not in row.sizes_mm:
            near = min(row.sizes_mm, key=lambda v: abs(v - s.diameter_mm))
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[s.evidence],
                    comment=f"Ø{s.diameter_mm:g} {s.material} bar is not a size PARI's raw-material list "
                    f"stocks for "
                    f"{row.material} round (nearest: Ø{near:g}).",
                    recommended_correction="Use a stocked bar size, or confirm the size with purchase.",
                )
            )
    return out


_REFERS = re.compile(r"\bREF\b|AS\s+PER|SEE\s+NOTE|^\W*#\W*$", re.I)  # "REF. NOTE": the material is elsewhere


class ApprovedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str  # DES-11's material table: PARI's approved high-carbon and alloy steel grades
    classes_table: str  # material designation -> class, to tell which materials DES-11 governs
    governed_classes: list[str]  # the classes DES-11 lists grades for
    suggest_closest: bool = True


@check("material_approved", ApprovedParams)
def material_approved(ctx: ReviewContext, rule: Rule, params: ApprovedParams) -> list[Finding]:
    """A carbon or alloy steel is one of DES-11's grades (its 13 rows and their equivalents). DES-11 covers
    those steels only, so mild steel, stainless, aluminium and plastics are not judged; a material no list
    recognises at all is a warning, as it may be a spelling DES-11 does not print."""
    import difflib

    from drawing_intelligence.review.reference import Materials

    des11 = ctx.reference.get(params.table)
    classes = ctx.reference.get(params.classes_table)
    if not isinstance(des11, MaterialHeatTreatment) or not isinstance(classes, Materials):
        raise NotCheckable(f"reference tables {params.table!r} / {params.classes_table!r} not loaded")
    named = [(t, e) for t, e in pr.material_texts(ctx) if not ev.is_placeholder(t) and not _REFERS.search(t)]
    if not named:
        raise NotCheckable("no material on the drawing (title block or '# MATERIAL' note)")
    text, evidence = named[0]
    if pr.des11_rows(ctx, des11) is not None:
        return []
    cls = classes.classify(text)
    if cls is not None and cls not in params.governed_classes:
        raise NotApplicable(f"{text.strip()} is {cls.replace('_', ' ')}, which DES-11 does not cover")
    grades = [m.key for m in des11.materials]
    near = (
        difflib.get_close_matches(_norm(text), [_norm(g) for g in grades], n=1, cutoff=0.5)
        if params.suggest_closest
        else []
    )
    closest = next((g for g in grades if near and _norm(g) == near[0]), None)
    what = f"a {cls.replace('_', ' ')}" if cls else "a material no PARI list recognises"
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[evidence],
            comment=f"The material {text.strip()!r} is {what} and not one of DES-11's grades.",
            recommended_correction=(
                f"Use a DES-11 grade{f' (closest: {closest})' if closest else ''}, or have the material "
                "approved and added to DES-11."
            ),
            result="warning" if cls is None else None,
        )
    ]
