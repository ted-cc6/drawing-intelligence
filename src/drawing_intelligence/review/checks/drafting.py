"""Drafting checks: how dimensions are drawn (ISO 129 and the drafting rules in PARI's guidelines), from stage
1's graphics (`PageExtraction.graphics`): arrowheads, the line each value sits on, its reading direction, and
what is drawn around and through it. No LLM.

A drawing extracted before schema 2.3 has no graphics, and these rules are not checked on it.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.extraction.geometry import nominal_value
from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._geometry import MM_PTS, STANDARD_SCALES
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import (
    DimensionGraphics,
    EvidenceRef,
    Finding,
    PageExtraction,
    TextItem,
)

REVIEWER = "checks"


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TerminationParams(_Params):
    terminations: list[Literal["arrowhead", "oblique_stroke", "origin_indication"]]


class ArrowStyleParams(_Params):
    styles: list[Literal["open", "closed", "closed_filled"]]
    small_space_substitutes: list[Literal["oblique_stroke", "dot"]] = []  # allowed where there is no room


class RadiusParams(_Params):
    arrowheads: int = 1


class MethodParams(_Params):
    methods: list[Literal["method_1_aligned", "method_2_unidirectional"]]


class ReadingParams(_Params):
    read_from: list[Literal["bottom", "right"]]
    value_method: list[Literal["method_1"]]


class NotToScaleParams(_Params):
    not_to_scale_marker: Literal["underline"]


BBox = tuple[float, float, float, float]


def _gap(a: BBox | list[float], b: BBox | list[float]) -> float:
    return max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3], 0.0)


def _height(b: BBox) -> float:
    return min(b[2] - b[0], b[3] - b[1])


def _centre(b: BBox | list[float]) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def graphic_pages(ctx: ReviewContext) -> list[PageExtraction]:
    pages = [p for p in ctx.pages if p.graphics is not None]
    if not pages:
        raise NotCheckable("stage 1 did not read the drawing's graphics (extracted before schema 2.3)")
    return pages


_FRAGMENT = re.compile(r"\s*(?:0|[+-]\s*\d+(?:\.\d+)?)\s*")  # the "0" or "-0.1" of a stacked tolerance


def _not_a_value(page: PageExtraction, d: TextItem, g: DimensionGraphics) -> bool:
    """Numbers stage 1 classes as dimensions that are not dimension values: table cells, revision numbers
    (in their triangle or the revision table), Ra values in finish marks, item balloons, and the upper or
    lower limit of a stacked tolerance printed apart from its value."""
    graphics = page.graphics
    assert graphics is not None
    b = d.bbox
    cx, cy = _centre(b)
    h = _height(b)
    if g.in_table:
        return True
    marks = [m.bbox for m in graphics.revision_marks] + list(graphics.revision_cells)
    if any(m[0] - 1 <= cx <= m[2] + 1 and m[1] - 1 <= cy <= m[3] + 1 for m in marks):
        return True
    if len(d.text.strip()) <= 2 and any(_gap(b, m) <= 0.5 for m in marks):
        return True  # a revision label overlapping its triangle's edge
    if any(_gap(b, n.bbox) <= 1 for n in page.revision_numbers):
        return True
    if any(s.type == "surface_finish" and _gap(b, s.bbox) <= 3 for s in page.symbols):
        return True
    if any(math.dist((cx, cy), c.centre) < c.radius and c.radius <= 3 * h for c in graphics.circles):
        return True  # an item balloon: a number in a small circle
    if re.fullmatch(r"\s*\d{1,2}\s*", d.text) and any(
        re.match(r"\s*REV", t.text, re.I) and _gap(b, t.bbox) <= 80 for t in page.body_text
    ):
        return True  # a revision number in a revision table PARI draws outside the title block
    if _FRAGMENT.fullmatch(d.text):
        others = [*page.dimensions, *page.other_numeric, *page.body_text]
        if any(o.bbox != d.bbox and _gap(b, o.bbox) <= 0.6 * h for o in others):
            return True
    return False


def _values(ctx: ReviewContext) -> list[tuple[PageExtraction, TextItem, DimensionGraphics]]:
    """Every real dimension value on the drawing with how it is drawn."""
    out = []
    for page in graphic_pages(ctx):
        assert page.graphics is not None
        dims = ev.dims_by_id(page)
        for g in page.graphics.dimensions:
            d = dims.get(g.dimension_id)
            if d is not None and not _not_a_value(page, d, g):
                out.append((page, d, g))
    return out


def _region(page: PageExtraction, box: BBox | list[float], quote: str | None = None) -> EvidenceRef:
    return EvidenceRef(
        kind="region",
        page=page.page_number,
        bbox=[round(min(box[0], box[2]), 1), round(min(box[1], box[3]), 1), round(max(box[0], box[2]), 1),
              round(max(box[1], box[3]), 1)],
        quote=quote,
        provenance="vector",
    )  # fmt: skip


def _is_radius(text: str) -> bool:
    return bool(re.match(r"\s*(?:\d+\s*[xX×]\s*)?R\s*\d", text))


def _is_angle(text: str) -> bool:
    return "°" in text


# --- CN-003, ISO-023: every value has a dimension line, and every dimension line has terminations -----------


def _matched(page: PageExtraction) -> set[str]:
    return {m.dimension_id for m in page.matched_lines}


@check("unattached_dimension")
def unattached_dimension(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A dimension value with no line at all near it: no arrowed dimension line or leader, no line along it
    (a dimension line without arrowheads is ISO-023's), and no extension line ending at it (an ordinate
    value). Usually a value left behind when its feature was moved or deleted."""
    values = _values(ctx)
    if not values:
        raise NotApplicable("no dimension values on the drawing")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.dimension(page, d)],
            comment=f"{d.text.strip()} has no dimension line, leader or extension line next to it, so it "
            "does not say what it measures.",
            recommended_correction="Attach the value to its dimension line or leader, or delete it if its "
            "feature has gone.",
        )
        for page, d, g in values
        if g.line is None and not g.ordinate and d.id not in _matched(page)
    ]


@check("dimension_line_terminations", TerminationParams)
def dimension_line_terminations(ctx: ReviewContext, rule: Rule, _: TerminationParams) -> list[Finding]:
    """A value sits on a line running along it, but no arrowhead ends that line (or any line joined to it).
    Ordinate values, which run from an origin with no arrowheads, are not judged."""
    values = [(p, d, g) for p, d, g in _values(ctx) if not g.ordinate]
    if not values:
        raise NotApplicable("no dimension values on the drawing")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.dimension(page, d)],
            comment=f"The dimension line under {d.text.strip()} ends without an arrowhead or oblique stroke "
            "at either end.",
            recommended_correction="Give the dimension line its terminations (arrowheads, or oblique strokes "
            "where there is no room).",
        )
        for page, d, g in values
        if g.line is None and d.id in _matched(page)
    ]


# --- ISO-025: one arrowhead style ---------------------------------------------------------------------------


@check("single_arrowhead_style", ArrowStyleParams)
def single_arrowhead_style(ctx: ReviewContext, rule: Rule, _: ArrowStyleParams) -> list[Finding]:
    """All arrowheads on a sheet are drawn one way: filled, outlined (closed) or open."""
    out = []
    seen = False
    for page in graphic_pages(ctx):
        assert page.graphics is not None
        styles = {k: v for k, v in page.graphics.arrowhead_styles.items() if v}
        if not styles:
            continue
        seen = True
        if len(styles) < 2:
            continue
        main = max(styles, key=lambda k: styles[k])
        odd = [a for a in page.graphics.arrowheads if a.style != main]
        counts = ", ".join(f"{v} {k}" for k, v in sorted(styles.items(), key=lambda kv: -kv[1]))
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[
                    _region(
                        page, (a.tip[0] - 6, a.tip[1] - 6, a.tip[0] + 6, a.tip[1] + 6), f"{a.style} arrowhead"
                    )
                    for a in odd[:3]
                ],
                comment=f"The sheet mixes arrowhead styles ({counts}).",
                recommended_correction=f"Draw every arrowhead {main}, the style used on most of the sheet.",
            )
        )
    if not seen:
        raise NotApplicable("no arrowheads on the drawing")
    return out


# --- ISO-027, WST-050: radius dimensions --------------------------------------------------------------------


def _radii(ctx: ReviewContext) -> list[tuple[PageExtraction, TextItem, DimensionGraphics]]:
    found = [(p, d, g) for p, d, g in _values(ctx) if _is_radius(d.text) and g.line is not None]
    if not found:
        raise NotApplicable("no radius dimension with a dimension line")
    return found


@check("radius_single_arrowhead", RadiusParams)
def radius_single_arrowhead(ctx: ReviewContext, rule: Rule, params: RadiusParams) -> list[Finding]:
    """A radius dimension has one arrowhead, on the arc. Two on its line make it read as a diameter."""
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.dimension(page, d)],
            comment=f"The radius {d.text.strip()} has {g.line_arrowheads} arrowheads on its dimension line; "
            "a radius has one, at the arc.",
            recommended_correction="Draw the radius line from the centre (or from outside) to the arc with "
            "one arrowhead.",
        )
        for page, d, g in _radii(ctx)
        if g.line_arrowheads > params.arrowheads
    ]


@check("full_circle_by_diameter")
def full_circle_by_diameter(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A full circle is dimensioned by its diameter: a radius whose arrowhead lands on a full circle (drawn
    closed) should be a Ø."""
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.dimension(page, d)],
            comment=f"{d.text.strip()} points at a full circle; full circles are dimensioned by diameter.",
            recommended_correction=f"Dimension the circle as Ø{_doubled(d.text)} instead of a radius.",
        )
        for page, d, g in _radii(ctx)
        if g.tip_on_circle
    ]


def _doubled(text: str) -> str:
    m = re.search(r"R\s*(\d+(?:\.\d+)?)", text)
    if not m:
        return "…"
    v = 2 * float(m[1])
    return f"{v:g}"


# --- ISO-029: no line through a value -----------------------------------------------------------------------


@check("dimension_text_not_crossed")
def dimension_text_not_crossed(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """No line runs through a dimension value (hatching, centre, extension or outline lines are broken
    around it). Judged on values that sit on a dimension line, leader or ordinate line; table cells are not
    dimension values."""
    values = [(p, d, g) for p, d, g in _values(ctx) if g.line is not None or g.ordinate]
    if not values:
        raise NotApplicable("no dimension values on a dimension line")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[
                ev.dimension(page, d),
                *(_region(page, s, "line through the value") for s in g.crossed_by[:2]),
            ],
            comment=f"A line runs through the value {d.text.strip()}, which makes it hard to read.",
            recommended_correction="Break the line (hatching, centre or extension line) around the value, or "
            "move the value clear of it.",
        )
        for page, d, g in values
        if g.crossed_by
    ]


# --- ISO-030, ISO-031: which way values read ----------------------------------------------------------------


def _vertical(line: BBox) -> bool:
    return abs(line[0] - line[2]) < 0.5 and abs(line[1] - line[3]) > 0.5


@check("dimension_value_method_consistent", MethodParams)
def dimension_value_method_consistent(ctx: ReviewContext, rule: Rule, _: MethodParams) -> list[Finding]:
    """One placement method per sheet: on vertical dimension lines, values either all read along the line
    (method 1, aligned) or all read horizontally (method 2, unidirectional). Judged on values between two
    opposed arrowheads on a vertical line."""
    out = []
    judged = False
    for page in graphic_pages(ctx):
        aligned, level = [], []
        for p, d, g in _values(ctx):
            if p is not page or g.line is None or g.span_pts is None or not _vertical(g.line):
                continue
            if _is_angle(d.text) or _is_radius(d.text):
                continue
            (aligned if abs(g.direction[1]) > 0.9 else level if abs(g.direction[0]) > 0.9 else []).append(d)
        if not aligned and not level:
            continue
        judged = True
        if aligned and level:
            minority, method = (level, "aligned") if len(aligned) >= len(level) else (aligned, "horizontal")
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.dimension(page, d) for d in minority[:5]],
                    comment=f"On vertical dimension lines, {len(aligned)} values read along the line and "
                    f"{len(level)} read horizontally: the sheet mixes ISO 129's two methods.",
                    recommended_correction=f"Place these {len(minority)} values the way the rest are "
                    f"({method}).",
                )
            )
    if not judged:
        raise NotApplicable("no value on a vertical dimension line")
    return out


@check("dimension_text_readable_direction", ReadingParams)
def dimension_text_readable_direction(ctx: ReviewContext, rule: Rule, _: ReadingParams) -> list[Finding]:
    """Values read from the bottom or the right of the sheet. A value reading from the left (top to
    bottom) or upside down fails; one on an oblique line within 30 degrees of straight down (ISO 129
    figure 17's zone to avoid) is a warning."""
    values = _values(ctx)
    if not values:
        raise NotApplicable("no dimension values on the drawing")
    out = []
    for page, d, g in values:
        dx, dy = g.direction
        if dx < -0.1 or dy > 0.98:
            how = "upside down" if dx < -0.1 and abs(dy) < 0.5 else "from the left"
            result = "warning" if _is_angle(d.text) else "fail"  # ISO 129 orients angles by its figure 22
        elif dy > math.cos(math.radians(30)):
            result, how = "warning", "steeply downward, in the zone ISO 129 says to avoid"
        else:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.dimension(page, d)],
                comment=f"{d.text.strip()} reads {how}; values read from the bottom or the right of the "
                "sheet.",
                recommended_correction="Turn the value to read from the bottom or the right.",
                result=result,  # type: ignore[arg-type]
            )
        )
    return out


# --- DSM-023: out-of-scale dimensions are underlined --------------------------------------------------------


@check("dimension_matches_scale_or_underlined", NotToScaleParams)
def dimension_matches_scale_or_underlined(
    ctx: ReviewContext, rule: Rule, _: NotToScaleParams
) -> list[Finding]:
    """A dimension drawn at a length its value does not match is underlined (not to scale).

    Lengths are measured tip to tip between a value's two arrowheads; a radius by fitting a circle to the arc
    its arrow lands on. The sheet's scales are the standard ones at least 3 lengths agree with (1%), plus the
    scales the sheet states (title block, "SCALE 2:1" under a view). A length 5-50% off all of them, or a
    radius 3 times or more off, not underlined and at least 1.5 mm off on paper, is flagged. A length further
    off is a view at another scale or a line matched wrongly; a length at the same ratio as two others is a
    view drawn at a scale the sheet does not state.
    """
    out = []
    measured = False
    for page in graphic_pages(ctx):
        lengths, radii = [], []
        for p, d, g in _values(ctx):
            callout = re.search(r"[xX×]|^\s*M\d|^\s*\d+\s*-\s*[Ø⌀]", d.text)
            if p is not page or _is_angle(d.text) or callout:
                continue  # angles, thread and count call-outs
            if _is_radius(d.text):
                m = re.search(r"R\s*(\d+(?:\.\d+)?)", d.text)
                if g.arc_radius_pts and m and float(m[1]) > 0:
                    radii.append((d, g, g.arc_radius_pts, g.arc_radius_pts / (float(m[1]) * MM_PTS)))
                continue
            if g.span_pts is None or g.line_arrowheads != 2 or not _between_tips(d, g):
                continue  # both arrowheads on its own line and the value between them: the span is its length
            v = nominal_value(d.text.replace("Ø", "").replace("⌀", ""))
            if v and v > 0:
                lengths.append((d, g, g.span_pts, g.span_pts / (v * MM_PTS)))
        scales = {s for s in STANDARD_SCALES if sum(abs(r / s - 1) <= 0.01 for *_, r in lengths) >= 3}
        if not scales:
            continue
        measured = True
        scales |= _stated_scales(page)
        for kind, items in (("length", lengths), ("radius", radii)):
            for d, g, drawn_pts, r in items:
                best = min(scales, key=lambda s: abs(r / s - 1))
                off = abs(r / best - 1)
                if off < 0.05 or g.underlined or abs(drawn_pts - drawn_pts * best / r) < 1.5 * MM_PTS:
                    continue
                if any(abs(r / s - 1) <= 0.02 for s in STANDARD_SCALES):
                    continue  # exactly at a standard scale: a view drawn at a scale no label states
                if kind == "radius" and 1 / 3 < r / best < 3:
                    continue  # an arc fit settles a radius only roughly: just a gross error (a slipped digit)
                if kind == "length":
                    if off >= 0.5:
                        continue  # another view's scale, or a line matched wrongly
                    if sum(abs(r2 / r - 1) <= 0.02 for d2, *_, r2 in lengths if d2 is not d) >= 2:
                        continue  # drawn at the same ratio as others: a view at a scale the sheet omits
                drawn_mm = drawn_pts / (best * MM_PTS)
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[ev.dimension(page, d)],
                        comment=f"{d.text.strip()} is drawn as {'R' if kind == 'radius' else ''}"
                        f"{drawn_mm:.3g} at the sheet's scale "
                        f"({', '.join(_ratio(s) for s in sorted(scales, reverse=True))}) and is not "
                        "underlined as not to scale.",
                        recommended_correction="Redraw the feature to scale, or underline the value to mark "
                        "it not to scale.",
                    )
                )
    if not measured:
        raise NotCheckable("too few dimensions drawn at a standard scale to measure against")
    return out


def _between_tips(d: TextItem, g: DimensionGraphics) -> bool:
    """The value's centre falls between the two arrow tips along the line. A value outside them may sit by
    a neighbouring dimension's line (in a chain they share extension lines), so it is not measured."""
    if len(g.arrow_tips) != 2:
        return False
    (ax, ay), (bx, by) = g.arrow_tips
    cx, cy = _centre(d.bbox)
    dx, dy = bx - ax, by - ay
    n2 = dx * dx + dy * dy
    return n2 > 0 and 0 <= ((cx - ax) * dx + (cy - ay) * dy) / n2 <= 1


_STATED_SCALE = re.compile(r"SCALE\s*:?\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", re.I)
_RATIO_FIELD = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*$")


def _stated_scales(page: PageExtraction) -> set[float]:
    """The scales the sheet states: its title-block scale and the view labels' SCALE n:m."""
    found = [m for ln in page.body_text for m in _STATED_SCALE.finditer(ln.text)]
    if (v := ev.value(page, "scale")) and (m := _RATIO_FIELD.match(v)):
        found.append(m)
    return {float(m[1]) / float(m[2]) for m in found if float(m[2]) > 0}


def _ratio(s: float) -> str:
    return f"{s:g}:1" if s >= 1 else f"1:{1 / s:g}"


# --- DTT-002: basic dimensions are boxed and untoleranced ---------------------------------------------------

_TOLERANCED = re.compile(r"±|\+\s*\d|-\s*0[.,]\d|\b[A-HJ-Za-hj-z]{1,2}\d{1,2}\b")


def boxed_values(ctx: ReviewContext) -> list[tuple[PageExtraction, TextItem]]:
    """Dimension values framed by a drawn rectangle (basic dimensions), not counting the cells of a GD&T
    frame or a datum flag."""
    out = []
    for page, d, g in _values(ctx):
        if not g.boxed:
            continue
        if any(s.type in ("gdt", "datum") and _gap(d.bbox, s.bbox) <= 1 for s in page.symbols):
            continue
        out.append((page, d))
    return out


@check("basic_dimension_untoleranced")
def basic_dimension_untoleranced(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A boxed (basic) dimension is exact: its tolerance comes from the GD&T frame, so it carries none of
    its own."""
    boxed = boxed_values(ctx)
    if not boxed:
        raise NotApplicable("no boxed (basic) dimension on the drawing")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.dimension(page, d)],
            comment=f"The basic dimension {d.text.strip()} carries its own tolerance; a basic dimension is "
            "exact and takes its tolerance from the feature control frame.",
            recommended_correction="Drop the tolerance from the boxed value, or unbox it if it is a normal "
            "toleranced dimension.",
        )
        for page, d in boxed
        if d.limits or _TOLERANCED.search(d.text)
    ]
