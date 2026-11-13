"""GD&T and datum checks, on the symbols stage 1 reads from the PDF (frames exact from the text layer, datum
flags from vector geometry)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, PageExtraction, SymbolItem, TextItem, TextLine

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


# --- From stage 1's graphics (schema 2.3): basic dimensions and what a datum flag sits on -------------------


@check("basic_dims_for_position")
def basic_dims_for_position(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A position tolerance locates its feature from basic (boxed) dimensions. A sheet with a position frame
    and no boxed dimension at all leaves the true position undefined. Which feature each frame is on is not
    known, so a sheet with some boxed dimensions passes."""
    from drawing_intelligence.review.checks.drafting import boxed_values, graphic_pages

    pages = graphic_pages(ctx)
    frames = [(p, s) for p, s in _frames(ctx) if s.characteristic == "position" and p in pages]
    if not frames:
        raise NotApplicable("no position tolerance on the drawing")
    boxed_on = {p.page_number for p, _ in boxed_values(ctx)}
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s)],
            comment=f"The position tolerance '{s.text}' has no basic (boxed) dimension anywhere on the sheet "
            "to locate its true position.",
            recommended_correction="Box the dimensions that locate the feature (basic dimensions), or "
            "state them in a note.",
        )
        for page, s in frames
        if page.page_number not in boxed_on
    ]


def _foot(page: PageExtraction, flag: SymbolItem) -> tuple[float, float] | None:
    """The centre of the flag's triangle: the filled triangle nearest its letter, within 40 pt."""
    if page.graphics is None:
        return None
    cx, cy = (flag.bbox[0] + flag.bbox[2]) / 2, (flag.bbox[1] + flag.bbox[3]) / 2
    feet = [((t[0] + t[2]) / 2, (t[1] + t[3]) / 2) for t in page.graphics.datum_triangles]
    near = [f for f in feet if ((f[0] - cx) ** 2 + (f[1] - cy) ** 2) ** 0.5 <= 40]
    return min(near, key=lambda f: (f[0] - cx) ** 2 + (f[1] - cy) ** 2) if near else None


def _on_dimension_line(foot: tuple[float, float], line: tuple[float, float, float, float]) -> float | None:
    """How far a datum triangle is from a dimension line it sits on: on the line itself or on its
    continuation just past an end (where it replaces an arrowhead). None when it is not on the line."""
    x0, y0, x1, y1 = line
    cx, cy = foot
    dx, dy = x1 - x0, y1 - y0
    n = (dx * dx + dy * dy) ** 0.5
    if n == 0:
        return None
    across = abs((cx - x0) * dy - (cy - y0) * dx) / n
    t = ((cx - x0) * dx + (cy - y0) * dy) / (n * n)
    along = 0.0 if 0 <= t <= 1 else (-t if t < 0 else t - 1) * n
    if across <= 3 and along <= 15:
        return across + along
    return None


def datum_dimensions(ctx: ReviewContext) -> list[tuple[PageExtraction, SymbolItem, TextItem]]:
    """Datum flags whose triangle sits on a dimension line (or its continuation): the datum is the feature
    of size that dimension measures. The nearest such dimension per flag."""
    from drawing_intelligence.review.checks.drafting import _values

    values = _values(ctx)
    out = []
    for page, s in _flags(ctx):
        foot = _foot(page, s)
        if foot is None:
            continue
        best = None
        for p, d, g in values:
            if p is not page or g.line is None or g.span_pts is None:
                continue
            dist = _on_dimension_line(foot, g.line)
            if dist is not None and (best is None or dist < best[0]):
                best = (dist, d)
        if best is not None:
            out.append((page, s, best[1]))
    return out


def _explicitly_toleranced(page: PageExtraction, d: TextItem) -> bool:
    from drawing_intelligence.review.checks.fits import _stacked_partner, parse_fit

    t = d.text
    return bool(
        d.limits or re.search(r"±|\+\s*\d|[-–]\s*0[.,]\d", t) or parse_fit(t) or _stacked_partner(page, d)
    )


@check("datum_feature_size_toleranced")
def datum_feature_size_toleranced(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A datum that is a feature of size (a datum flag in line with a size's dimension line) has a size
    tolerance of its own; the general tolerance is too loose to set up a datum from."""
    on_sizes = [(p, s, d) for p, s, d in datum_dimensions(ctx) if "°" not in d.text and not d.is_reference]
    if not on_sizes:
        raise NotApplicable("no datum flag on a dimensioned feature of size")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[symbol(page, s), ev.dimension(page, d)],
            comment=f"Datum {', '.join(s.datums)}'s triangle sits in line with the dimension "
            f"{d.text.strip()}, which makes the datum that feature of size (ASME Y14.5); the size has no "
            "tolerance of its own, only the general tolerance.",
            recommended_correction=f"Tolerance {d.text.strip()} directly, e.g. with a fit or ± limits; or, "
            "if the face is meant, move the triangle off the dimension line.",
        )
        for page, s, d in on_sizes
        if not _explicitly_toleranced(page, d)
    ]


# "4X Ø9", "4 x M6", "4-M6", "6 HOLES": a count of two or more and a hole, thread or diameter
_PATTERN = re.compile(r"^\s*(?:[2-9]|\d{2,})\s*(?:[xX×]|-|NOS?\.?)?\s*(?:[Ø⌀M]|DIA|HOLES?\b|DRILL|TAP)", re.I)


def _nearest_callout(page: PageExtraction, s: SymbolItem) -> TextItem | TextLine | None:
    items = [
        it
        for it in [*page.dimensions, *page.other_numeric, *page.body_text]
        if re.search(r"\d", it.text) and _gap(s.bbox, it.bbox) <= NEAR
    ]
    return min(items, key=lambda it: _gap(s.bbox, it.bbox)) if items else None


@check("pattern_datum_defined")
def pattern_datum_defined(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A pattern used as a datum (a flag on '4X Ø9') is defined by a position tolerance on the pattern, so
    the datum axis is the pattern's true positions. Judged by nearness on the sheet."""
    on_patterns = []
    for page, s in _flags(ctx):
        c = _nearest_callout(page, s)
        if c is not None and _PATTERN.match(c.text):
            on_patterns.append((page, s, c))
    if not on_patterns:
        raise NotApplicable("no datum flag next to a pattern call-out")
    positions = [(p, f) for p, f in _frames(ctx) if f.characteristic == "position"]
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[
                symbol(page, s),
                ev.dimension(page, c) if isinstance(c, TextItem) and c.id else ev.text(page, c),
            ],
            comment=f"Datum {', '.join(s.datums)} is the pattern {c.text.strip()}, but no position tolerance "
            "near it defines the pattern.",
            recommended_correction="Add a position frame to the pattern call-out so the datum is the "
            "pattern's true positions.",
        )
        for page, s, c in on_patterns
        if not any(p is page and _gap(f.bbox, c.bbox) <= NEAR for p, f in positions)
    ]
