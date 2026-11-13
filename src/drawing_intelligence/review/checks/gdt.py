"""GD&T and datum checks, on the symbols stage 1 reads from the PDF (frames exact from the text layer, datum
flags from vector geometry)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks._registry import NotApplicable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, PageExtraction, SymbolItem

REVIEWER = "checks"
FORM = frozenset({"flatness", "straightness", "cylindricity", "circularity"})  # never take a datum


def symbol(page: PageExtraction, s: SymbolItem) -> EvidenceRef:
    return EvidenceRef(
        kind="symbol",
        ref=s.id,
        page=page.page_number,
        bbox=list(s.bbox),
        quote=s.text,
        provenance=s.provenance,
    )


def _frames(ctx: ReviewContext) -> list[tuple[PageExtraction, SymbolItem]]:
    return [(p, s) for p in ctx.pages for s in p.symbols if s.type == "gdt"]


def _flags(ctx: ReviewContext) -> list[tuple[PageExtraction, SymbolItem]]:
    return [(p, s) for p in ctx.pages for s in p.symbols if s.type == "datum"]


def _letters(datums: list[str]) -> set[str]:
    """Datum letters in a frame's references; a compound reference "A-B" names both."""
    return {c for d in datums for c in d.split("-") if len(c) == 1}


@check("datum_referenced_defined")
def datum_referenced_defined(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Every datum a frame references is defined by a datum flag somewhere on the drawing."""
    frames = [(p, s) for p, s in _frames(ctx) if s.datums]
    if not frames:
        raise NotApplicable("no feature control frame references a datum")
    defined = {s.datums[0] for _, s in _flags(ctx) if s.datums}
    out = []
    for page, s in frames:
        missing = sorted(_letters(s.datums) - defined)
        if missing:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[symbol(page, s)],
                    comment=f"The frame '{s.text}' references datum {', '.join(missing)}, "
                    "which no datum flag on the drawing defines.",
                    recommended_correction="Flag the datum feature, or correct the reference.",
                )
            )
    return out


class DatumParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    characteristics: list[str]


@check("fcf_has_datum", DatumParams)
def fcf_has_datum(ctx: ReviewContext, rule: Rule, params: DatumParams) -> list[Finding]:
    """Orientation, location and runout tolerances are related to a datum."""
    needing = {c.replace(" ", "_") for c in params.characteristics} | {"circular_runout"}
    frames = [(p, s) for p, s in _frames(ctx) if s.characteristic in needing]
    if not frames:
        raise NotApplicable("no orientation, location or runout tolerance")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s)],
            comment=f"'{s.text}' is an orientation, location or runout tolerance with no datum reference.",
            recommended_correction="Add the datum the tolerance is measured from.",
        )
        for page, s in frames
        if not s.datums
    ]


class LetterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    illegal: list[str] = []


@check("datum_letters_valid", LetterParams)
def datum_letters_valid(ctx: ReviewContext, rule: Rule, params: LetterParams) -> list[Finding]:
    """No datum uses a letter the standard reserves (I, O, Q look like 1, 0)."""
    flags = _flags(ctx)
    if not flags:
        raise NotApplicable("no datum flags")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s)],
            comment=f"Datum letter {s.datums[0]} is not allowed: it is easily read as a digit.",
            recommended_correction="Use another letter for this datum.",
        )
        for page, s in flags
        if s.datums and s.datums[0] in params.illegal
    ]


_NOTE_DATUMS = re.compile(
    r"\b(?:DATUMS?|SURFACES?|FACES?|W\.?\s?R\.?\s?T\.?)\s*[:.]?\s*([A-Z](?:\s*(?:&|AND|,|/)\s*[A-Z])*)\b"
)


def _named_in_notes(ctx: ReviewContext) -> set[str]:
    """Datum letters a note refers to ("CO-PLANARITY OF SURFACE A & B ...", "W.R.T. DATUM C")."""
    letters: set[str] = set()
    for page in ctx.pages:
        for line in page.body_text:
            for m in _NOTE_DATUMS.finditer(line.text.upper()):
                letters |= set(re.findall(r"[A-Z]", re.sub(r"\bAND\b", "", m.group(1))))
    return letters


@check("datum_unused")
def datum_unused(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A datum that is flagged is used by some feature control frame or note."""
    flags = _flags(ctx)
    if not flags:
        raise NotApplicable("no datum flags")
    used = {c for _, s in _frames(ctx) for c in _letters(s.datums)} | _named_in_notes(ctx)
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s)],
            comment=f"Datum {s.datums[0]} is defined but no feature control frame or note refers to it.",
            recommended_correction="Remove the datum flag, or add the tolerance that needs it.",
        )
        for page, s in flags
        if s.datums and s.datums[0] not in used
    ]


@check("datum_on_same_sheet")
def datum_on_same_sheet(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """On a drawing of several sheets, a datum a frame uses is flagged on that sheet too."""
    if len(ctx.pages) < 2:
        raise NotApplicable("a single sheet")
    defined_anywhere = {s.datums[0] for _, s in _flags(ctx) if s.datums}
    out = []
    for page in ctx.pages:
        here = {s.datums[0] for s in page.symbols if s.type == "datum" and s.datums}
        for s in page.symbols:
            if s.type != "gdt":
                continue
            elsewhere = sorted((_letters(s.datums) - here) & defined_anywhere)
            if elsewhere:
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[symbol(page, s)],
                        comment=f"'{s.text}' on sheet {page.page_number} uses datum {', '.join(elsewhere)}, "
                        "which is flagged on another sheet only.",
                        recommended_correction="Show the datum on this sheet as well, or note where it is.",
                    )
                )
    return out


@check("fcf_grammar")
def fcf_grammar(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A frame states a tolerance value, and a form tolerance (flatness, straightness, ...) takes no datum."""
    frames = _frames(ctx)
    if not frames:
        raise NotApplicable("no feature control frames")
    out = []
    for page, s in frames:
        if not s.tolerance or not any(ch.isdigit() for ch in s.tolerance):
            problem = "states no tolerance value"
        elif s.characteristic in FORM and s.datums:
            problem = f"is a form tolerance but references datum {', '.join(s.datums)}"
        else:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[symbol(page, s)],
                comment=f"The frame '{s.text}' {problem}.",
                recommended_correction="Correct the feature control frame.",
            )
        )
    return out


NEAR = 60.0  # pts: a symbol and a call-out this close (bbox to bbox) belong together


def _gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return max(dx, dy)


def _near_thread(ctx: ReviewContext, page: PageExtraction, s: SymbolItem) -> str | None:
    from drawing_intelligence.review.checks.threads import threads

    return next((t.text for t in threads(ctx) if t.page is page and _gap(s.bbox, t.item.bbox) <= NEAR), None)


def _nearest_is_thread(ctx: ReviewContext, page: PageExtraction, s: SymbolItem) -> str | None:
    """The thread a datum flag is attached to: the call-out nearest the flag must be the thread itself (a
    flag on the Ø4 next to an M6 x 5 DEEP is on the Ø4)."""
    from drawing_intelligence.review.checks.threads import threads

    items = [
        it
        for it in [*page.dimensions, *page.other_numeric, *page.body_text]
        if re.search(r"\d", it.text)
        and not re.fullmatch(r"\s*\d{1,2}\s*", it.text)
        and _gap(s.bbox, it.bbox) <= NEAR
    ]
    if not items:
        return None
    nearest = min(items, key=lambda it: _gap(s.bbox, it.bbox))
    return next((t.text for t in threads(ctx) if t.page is page and t.item.text == nearest.text), None)


def _text_near(page: PageExtraction, s: SymbolItem) -> str:
    return " ".join(ln.text for ln in [*page.body_text, *page.other_numeric] if _gap(s.bbox, ln.bbox) <= 8)


_THREAD_QUALIFIER = re.compile(r"\b(?:MD|PD|LD|MAJOR\s+DIA|PITCH\s+DIA|MINOR\s+DIA)\b", re.I)


@check("thread_datum_qualifier")
def thread_datum_qualifier(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A datum flag on a thread says which diameter it means (MD, PD or LD); unqualified, ISO 1101 takes the
    pitch diameter, which may not be what the designer meant. Judged by nearness on the sheet."""
    on_threads = [(p, s, t) for p, s in _flags(ctx) if (t := _nearest_is_thread(ctx, p, s))]
    if not on_threads:
        raise NotApplicable("no datum flag next to a thread call-out")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s)],
            comment=f"Datum {', '.join(s.datums)} sits on the thread {thread} without MD, PD or LD.",
            recommended_correction="Add the qualifier, e.g. 'MD' under the datum flag, or move the datum to "
            "a plain "
            "feature.",
        )
        for page, s, thread in on_threads
        if not _THREAD_QUALIFIER.search(_text_near(page, s))
    ]


_PROJECTED = re.compile(r"Ⓟ|\(P\)|PROJECTED", re.I)


class ProjectedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    features: list[str]


@check("projected_zone_on_threads", ProjectedParams)
def projected_zone_on_threads(ctx: ReviewContext, rule: Rule, params: ProjectedParams) -> list[Finding]:
    """A position tolerance on a tapped hole uses a projected tolerance zone (Ⓟ with its height). Judged by
    nearness of the position frame to a thread call-out."""
    on_threads = [
        (p, s, t)
        for p, s in _frames(ctx)
        if s.characteristic == "position" and (t := _near_thread(ctx, p, s))
    ]
    if not on_threads:
        raise NotApplicable("no position tolerance on a tapped hole")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s)],
            comment=f"The position tolerance {s.text!r} on {thread} has no projected tolerance zone (Ⓟ).",
            recommended_correction="Add Ⓟ and the projected height (e.g. the mating part's thickness).",
        )
        for page, s, thread in on_threads
        if not _PROJECTED.search(f"{s.tolerance or ''} {_text_near(page, s)}")
    ]


_MATERIAL_MODIFIER = re.compile(r"Ⓜ|Ⓛ|\((?:M|L)\)")
# Characteristics that never apply at a material condition: form of a surface, and runout
_NO_MODIFIER = frozenset({"flatness", "circularity", "cylindricity", "circular_runout", "total_runout"})


@check("material_modifier_on_feature_of_size")
def material_modifier_on_feature_of_size(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """MMC or LMC (Ⓜ / Ⓛ) is not used with flatness, circularity, cylindricity or runout, nor on the
    position of a
    tapped hole. The modifier is read from the frame's printed text."""
    with_modifier = [
        (p, s)
        for p, s in _frames(ctx)
        if _MATERIAL_MODIFIER.search(f"{s.tolerance or ''} {_text_near(p, s)}")
    ]
    if not with_modifier:
        raise NotApplicable("no MMC or LMC modifier on the drawing")
    out = []
    for page, s in with_modifier:
        reason = None
        if s.characteristic in _NO_MODIFIER:
            reason = f"{(s.characteristic or '').replace('_', ' ')} cannot take a material condition"
        elif s.characteristic == "position" and (t := _near_thread(ctx, page, s)):
            reason = f"it is the position of the tapped hole {t}"
        if reason:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[symbol(page, s)],
                    comment=f"{s.text!r} carries MMC/LMC, but {reason}.",
                    recommended_correction="Remove the modifier (use RFS).",
                )
            )
    return out
