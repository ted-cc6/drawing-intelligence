"""Consistency checks: the drawing must agree with itself. Exact answers from stage 1, no LLM."""

from __future__ import annotations

import itertools
import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._geometry import Drawn, drawn_dimensions, supported_scales
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.checks._text import all_text
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference_p2 import HardnessTable, NumericTable
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import ChainCheck, EvidenceRef, Finding, PageExtraction

REVIEWER = "checks"


def _chain_evidence(page: PageExtraction, c: ChainCheck, first: str | None = None) -> list[EvidenceRef]:
    dims = ev.dims_by_id(page)
    ids = [c.overall_id, *c.chain_ids] if c.overall_id else list(c.chain_ids)
    if first in ids:
        ids.remove(first)
        ids.insert(0, first)
    return [ev.dimension(page, dims[i]) for i in ids if i in dims]


def _chains(ctx: ReviewContext) -> list[tuple[PageExtraction, ChainCheck]]:
    found = [(p, c) for p in ctx.pages for c in p.chain_checks]
    if not found:
        raise NotApplicable("no chain of dimensions with an overall dimension found")
    return found


@check("chain_sum")
def chain_sum(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Every chain of end-to-end dimensions adds up to the overall dimension that spans it."""
    out = []
    for page, c in _chains(ctx):
        if c.match:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=_chain_evidence(page, c),
                comment=f"{' + '.join(c.chain_texts)} = {c.chain_sum:g}, but the overall dimension is "
                f"{c.overall_text} (off by {c.diff:g}).",
                recommended_correction="Correct the overall dimension or the chain so that they agree.",
            )
        )
    return out


def _is_reference(page: PageExtraction, dim_id: str | None) -> bool:
    d = ev.dims_by_id(page).get(dim_id or "")
    return d is not None and (d.is_reference or d.text.strip().startswith("("))


@check("reference_dim_consistent")
def reference_dim_consistent(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A reference dimension agrees with the dimensions it summarises: a chain holding one must add up."""
    with_ref = [
        (p, c) for p, c in _chains(ctx) if any(_is_reference(p, i) for i in [c.overall_id, *c.chain_ids])
    ]
    if not with_ref:
        raise NotApplicable("no reference dimension in a dimension chain")
    out = []
    for page, c in with_ref:
        if c.match:
            continue
        ref = next(i for i in [*c.chain_ids, c.overall_id] if _is_reference(page, i))
        text = ev.dims_by_id(page)[ref or ""].text
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=_chain_evidence(page, c, first=ref),
                comment=f"The reference dimension {text} does not agree with the chain it belongs to: "
                f"{' + '.join(c.chain_texts)} = {c.chain_sum:g} against {c.overall_text}.",
                recommended_correction="Set the reference dimension to the value the others give.",
            )
        )
    return out


@check("conflicting_values")
def conflicting_values(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Two dimensions drawn the same length but given different values (ADR 0010: geometry first).

    The scales a sheet is drawn at are the standard scales several of its dimensions agree with. A dimension
    3-25% off every one of them is suspect (far-off ones are small dimensions with their arrows outside, not
    typos), and it is flagged when a dimension drawn to scale, in the same direction and of the same length,
    carries a different value. Reference dimensions are left to CN-004.
    """
    out = []
    measured = False
    for page in ctx.pages:
        drawn = drawn_dimensions(page)
        scales = supported_scales(drawn)
        if not scales:
            continue
        measured = True

        def off(x: Drawn, scales: dict[float, list[Drawn]] = scales) -> float:
            return min(abs(x.paper_scale / s - 1) for s in scales)

        for d in drawn:
            if not 0.03 < off(d) < 0.25:
                continue
            partners = [
                p
                for p in drawn
                if p is not d
                and p.orientation == d.orientation
                and off(p) <= 0.01
                and abs(p.length - d.length) <= max(0.5, 0.01 * d.length)
                and abs(p.value - d.value) > 1e-6
            ]
            if not partners:
                continue
            p = min(partners, key=lambda p: abs(p.length - d.length))
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.dimension(page, d.dim), ev.dimension(page, p.dim)],
                    comment=f"{d.dim.text} and {p.dim.text} are drawn the same length but differ in value; "
                    f"{p.dim.text} matches the drawing's scale and {d.dim.text} does not.",
                    recommended_correction=f"Check {d.dim.text}: if both features are the same size, "
                    "give them one value.",
                )
            )
    if not measured:
        raise NotCheckable("too few dimensions drawn at a standard scale to compare lengths")
    return out


class UnitParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flag_units: list[str] = []  # inch-pound units flagged wherever they appear (notes, title block, values)
    exclude_fields: list[str] = []  # title-block fields allowed to use them (e.g. surface_area in in^2)
    flag_on_dimensions: list[str] = []  # unit marks flagged only right after a dimension value (3.94")


def _unit_pattern(unit: str, after_number: bool) -> re.Pattern[str]:
    tail = r"\b" if unit[-1].isalnum() else ""
    head = r"\d(?:[.,]\d+)?\s*" if after_number else r"(?<![\w-])"
    return re.compile(head + re.escape(unit) + tail)


@check("no_mixed_unit_systems", UnitParams)
def no_mixed_unit_systems(ctx: ReviewContext, rule: Rule, params: UnitParams) -> list[Finding]:
    """A metric drawing uses metric units only.

    Inch marks are only flagged right after a dimension value: inch trade names in notes and titles
    (1/2" BSP, "20 INCH HOSE") are legitimate on a metric drawing.
    """
    units = [ev.value(p, "units") for p in ctx.pages if ev.value(p, "units")]
    if not units:
        raise NotCheckable("the drawing's unit statement was not found")
    if not any(u.lower() == "mm" for u in units if u):
        raise NotApplicable(f"not a metric drawing (units: {units[0]})")
    on_dims = [_unit_pattern(u, after_number=True) for u in params.flag_on_dimensions]
    anywhere = [_unit_pattern(u, after_number=False) for u in params.flag_units]
    out = []
    for page in ctx.pages:
        hits: list[EvidenceRef] = []
        for item in [*page.dimensions, *page.other_numeric]:
            if any(p.search(item.text) for p in on_dims + anywhere):
                hits.append(ev.dimension(page, item) if item.id else ev.text(page, item))
        for item in page.notes:
            if any(p.search(item.text) for p in anywhere):
                hits.append(ev.text(page, item))
        for name, f in page.title_block_fields.items():
            if name not in params.exclude_fields and f.value and any(p.search(f.value) for p in anywhere):
                hits.append(ev.field(page, name))
        for hit in hits:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[hit],
                    comment=f"{hit.quote!r} uses an inch-pound unit on a metric (mm) drawing.",
                    recommended_correction="Give the value in mm, or mark it as a declared dual dimension.",
                )
            )
    return out


@check("closed_chain")
def closed_chain(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A chain of end-to-end dimensions that closes on an overall dimension has one link marked as reference.

    A chain that does not add up is `chain_sum`'s finding, so only chains that add up are judged here.
    """
    closed = [(p, c) for p, c in _chains(ctx) if c.match]
    if not closed:
        raise NotApplicable("no dimension chain closes on an overall dimension")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=_chain_evidence(page, c),
            comment=f"{' + '.join(c.chain_texts)} = {c.overall_text}: the chain and its overall are all "
            "toleranced, so the part is dimensioned twice over.",
            recommended_correction="Mark one link or the overall as a reference dimension, e.g. (40), or "
            "drop it.",
        )
        for page, c in closed
        if not any(_is_reference(page, i) for i in [c.overall_id, *c.chain_ids])
    ]


def _squash(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


class TemplateNotesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: list[str]


@check("template_notes_present", TemplateNotesParams)
def template_notes_present(ctx: ReviewContext, rule: Rule, params: TemplateNotesParams) -> list[Finding]:
    """The template's standard notes (unspecified radii and chamfers, general tolerance) are on every sheet.

    Matched without spaces and punctuation: PARI's sheets print "UNSP.RADII" and "Gen Tol.: IS 2102".
    """
    out = []
    for page in ctx.pages:
        lines = [*page.tolerance_table_text, *page.title_block_text, *page.body_text, *page.notes]
        if not lines:
            continue
        text = _squash(" ".join(ln.text for ln in lines))
        missing = [n for n in params.notes if _squash(n) not in text]
        if missing:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.field(page, "number")],
                    comment=f"Sheet {page.page_number} does not show the standard note(s) "
                    f"{', '.join(missing)}.",
                    recommended_correction="Use the current drawing template, which prints these notes.",
                )
            )
    return out


_BORDERS = {
    "border_top": (1, "column"),
    "border_bottom": (1, "column"),
    "border_left": (0, "row"),
    "border_right": (0, "row"),
}  # strip -> (axis across the strip, which zone markers it holds)
_ZONE_MARKER = {"column": re.compile(r"^\d{1,2}$"), "row": re.compile(r"^[A-Z]$")}


def _marker_lines(
    page: PageExtraction, regions: dict[str, tuple[float, float, float, float]]
) -> dict[str, float]:
    """Per border strip, where its zone markers (1 2 3 ... along the top and bottom, A B C ... up the sides)
    sit
    across the strip: the middle of the margin, so anything reaching it is outside the drawing border."""
    out = {}
    lines = [*page.body_text, *page.title_block_text, *page.tolerance_table_text]
    for name, (axis, kind) in _BORDERS.items():
        r = regions[name]
        at = sorted(
            (ln.bbox[axis] + ln.bbox[axis + 2]) / 2
            for ln in lines
            if _ZONE_MARKER[kind].match(ln.text.strip())
            and r[0] <= (ln.bbox[0] + ln.bbox[2]) / 2 <= r[2]
            and r[1] <= (ln.bbox[1] + ln.bbox[3]) / 2 <= r[3]
        )
        if len(at) >= 2:
            out[name] = at[len(at) // 2]
    return out


@check("content_inside_border")
def content_inside_border(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Dimensions, notes and view labels stay inside the drawing border, not in the margin.

    The template's border strips are wider than the printed frame, so the line of zone markers in each strip
    is the test: an item that reaches it is in the margin. A sheet without zone markers is not judged.
    """
    out, judged = [], False
    for page in ctx.pages:
        regions = ctx.template.regions_for(*page.page_size_pts)
        if not all(b in regions for b in _BORDERS):
            raise NotCheckable("the template has no border regions")
        edges = _marker_lines(page, regions)
        if not edges:
            continue
        judged = True
        for item in [*page.dimensions, *page.notes, *page.view_labels]:
            b = item.bbox
            outside = [
                name
                for name, at in edges.items()
                if (name == "border_top" and b[1] < at)
                or (name == "border_bottom" and b[3] > at)
                or (name == "border_left" and b[0] < at)
                or (name == "border_right" and b[2] > at)
            ]
            if outside:
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[ev.text(page, item)],
                        comment=f"{item.text.strip()!r} runs into the sheet's "
                        f"{outside[0].split('_')[1]} margin, "
                        "outside the drawing border.",
                        recommended_correction="Move it inside the border.",
                    )
                )
    if not judged:
        raise NotCheckable("no zone markers found in the border to place it")
    return out


_ROTATED = re.compile(r"ROTATED", re.I)
_ANGLE = re.compile(r"\d+(?:\.\d+)?\s*(?:°|DEG)", re.I)
_DIRECTION = re.compile(r"\b(?:CCW|CW|CLOCKWISE|COUNTER[\s-]*CLOCKWISE|ANTI[\s-]*CLOCKWISE)\b", re.I)


class RotatedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label_pattern: str


@check("rotated_view_labelled", RotatedParams)
def rotated_view_labelled(ctx: ReviewContext, rule: Rule, params: RotatedParams) -> list[Finding]:
    """A view label that says ROTATED states the angle and the direction (ROTATED 90° CW)."""
    labels = [(p, v) for p in ctx.pages for v in p.view_labels if _ROTATED.search(v.text)]
    if not labels:
        raise NotApplicable("no view is labelled as rotated")
    out = []
    for page, v in labels:
        missing = [w for w, pat in (("angle", _ANGLE), ("direction", _DIRECTION)) if not pat.search(v.text)]
        if missing:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, v)],
                    comment=f"The view label {v.text.strip()!r} does not state the "
                    f"{' or '.join(missing)} of rotation.",
                    recommended_correction="Label it as e.g. 'SECTION A-A ROTATED 90° CW'.",
                )
            )
    return out


# "58-62 HRC (650-750 HV)", "250 HB", "HARDNESS 850 TO 1000 HV"
_HARDNESS = re.compile(r"(\d+(?:\.\d+)?)(?:\s*(?:-|~|–|TO)\s*(\d+(?:\.\d+)?))?\s*(HRC|HRB|HV|HB|BHN)\b", re.I)
_COLUMN = {"HRC": "hrc", "HRB": "hrb", "HV": "hv", "HB": "hb_steel_ball", "BHN": "hb_steel_ball"}


def _to_hv(table: HardnessTable, scale: str, value: float) -> tuple[float, float] | None:
    """Value in `scale` as HV, by linear interpolation in the table, with the size of one table step there."""
    col = _COLUMN[scale]
    pts = [(v, r.hv) for r in table.rows if (v := getattr(r, col)) is not None]
    for (a, ha), (b, hb) in itertools.pairwise(pts):
        if a <= value <= b:
            return ha + (hb - ha) * (value - a) / (b - a), hb - ha
    return None


class HardnessScaleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    tolerance: str = ""


@check("hardness_scales_agree", HardnessScaleParams)
def hardness_scales_agree(ctx: ReviewContext, rule: Rule, params: HardnessScaleParams) -> list[Finding]:
    """A hardness given in two scales in one call-out agrees with the steel comparison table, within one
    table step."""
    table = ctx.reference.get(params.table)
    if not isinstance(table, HardnessTable):
        raise NotCheckable(f"reference table {params.table!r} not loaded")
    out, judged = [], False
    for page, item in all_text(ctx):
        found = [(m[3].upper(), float(m[1]), float(m[2] or m[1]), m) for m in _HARDNESS.finditer(item.text)]
        if len({_COLUMN[s] for s, *_ in found}) < 2:
            continue
        hv = []
        for scale, low, high, m in found:
            lo, hi = _to_hv(table, scale, low), _to_hv(table, scale, high)
            if lo and hi:
                hv.append((m.group(0).strip(), lo[0] - lo[1], hi[0] + hi[1]))
        if len(hv) < 2:
            continue
        judged = True
        (a, a_lo, a_hi), (b, b_lo, b_hi) = hv[0], hv[1]
        if a_hi < b_lo or b_hi < a_lo:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, item)],
                    comment=f"{a} and {b} do not agree: the steel hardness comparison table puts them at "
                    "about "
                    f"{(a_lo + a_hi) / 2:.0f} HV and {(b_lo + b_hi) / 2:.0f} HV.",
                    recommended_correction="Correct one of the two values, or give the hardness in one scale "
                    "only.",
                )
            )
    if not judged:
        raise NotApplicable("no hardness given in two scales")
    return out


_VIEW_LABEL = re.compile(r"^\s*(SECTION|DETAIL|VIEW)\s+([A-Z])(?:\s*-\s*([A-Z]))?\b")
_LETTER = re.compile(r"^[A-Z]$")
_INSIDE = ("title_block", "tolerance_table")  # template blocks that sit in the margin by design


def _in_margin(ctx: ReviewContext, page: PageExtraction, bbox: tuple[float, float, float, float]) -> bool:
    """In a border strip, the title block or the tolerance table: where zone letters and labels live."""
    x, y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(
        r[0] <= x <= r[2] and r[1] <= y <= r[3]
        for name, r in ctx.template.regions_for(*page.page_size_pts).items()
        if name.startswith("border") or name in _INSIDE
    )


@check("section_labels_match")
def section_labels_match(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Every SECTION A-A, DETAIL B or VIEW C label has its letter on the drawing field (at the cutting line,
    detail circle or view arrow), on any sheet. A section whose two labels differ (SECTION A-B) is flagged
    too."""
    labels = [(p, v, m) for p in ctx.pages for v in p.view_labels if (m := _VIEW_LABEL.match(v.text))]
    if not labels:
        raise NotApplicable("no section, detail or view label")
    letters = {
        ln.text.strip()
        for p in ctx.pages
        for ln in [*p.body_text, *p.other_numeric, *p.dimensions]
        if _LETTER.match(ln.text.strip()) and not _in_margin(ctx, p, ln.bbox)
    }
    out = []
    for page, v, m in labels:
        problem = None
        if m[3] and m[3] != m[2]:
            problem = f"its two letters differ ({m[2]}-{m[3]})"
        elif m[2] not in letters:
            where = {"SECTION": "cutting line", "DETAIL": "detail circle", "VIEW": "view arrow"}[m[1]]
            problem = f"no {where} on the drawing is lettered {m[2]}"
        if problem:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, v)],
                    comment=f"The view label {v.text.strip()!r}: {problem}.",
                    recommended_correction="Letter the cutting line, detail circle or arrow to match the "
                    "label.",
                )
            )
    return out


_WEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.I)
_PLAIN_VALUE = re.compile(r"^\s*\(?(?:[Ø⌀]\s*)?(\d+(?:\.\d+)?)")
# Material class -> the specific-weight entries (gf/cm³) it may be; the heaviest is used, so the bound
# stays safe
_DENSITY_KEYS = {
    "ferrous": ["steel", "cast steel", "grey cast iron", "high-speed steel"],
    "aluminium": ["aluminium", "Al alloy (Al, Cu, Mg)"],
    "copper_alloy": ["brass", "Al bronze", "tin bronze", "lead bronze", "copper"],
}


class MassParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    specific_weight_gf_cm3: dict[str, float] = {}
    # Stage 1 does not always read the longest dimension (a long rail drawn broken), so the box can be too
    # small;
    # only a mass this many times over it is flagged: grams written as kg is 1000 times.
    margin: float = 50


@check("mass_within_envelope", MassParams)
def mass_within_envelope(ctx: ReviewContext, rule: Rule, params: MassParams) -> list[Finding]:
    """The stated mass is no more than a box of the part's three largest dimensions would weigh at the
    heaviest specific weight of its material family, times `margin`. Only a gross error (grams written as kg)
    is caught."""
    from drawing_intelligence.review.reference import Materials

    materials = ctx.reference.get("materials")
    table = ctx.reference.get(params.table)
    if not isinstance(materials, Materials) or not isinstance(table, NumericTable):
        raise NotCheckable("the materials or specific-weight table is not loaded")
    out, judged = [], False
    for page in ev.title_block_pages(ctx):
        weight, material = ev.value(page, "weight"), ev.value(page, "material")
        m = _WEIGHT.search(weight or "")
        cls = materials.classify(material)
        family = "ferrous" if materials.family(cls) == "ferrous" else cls
        if not m or float(m[1]) <= 0 or family not in _DENSITY_KEYS:
            continue
        sizes = sorted(
            {float(v[1]) for p in ctx.pages for d in p.dimensions if (v := _PLAIN_VALUE.match(d.text))}
        )
        if len(sizes) < 3:
            continue
        judged = True
        a, b, c = sizes[-3:]
        density = max(max(table.values.get(k, [0])) for k in _DENSITY_KEYS[family])
        bound_kg = a * b * c / 1000 * density / 1000
        kg = float(m[1]) / (1000 if m[2].lower() == "g" else 1)
        if kg > params.margin * bound_kg:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.field(page, "weight"), ev.field(page, "material")],
                    comment=f"The stated mass {weight} is over {params.margin:g} times what a solid {c:g} × "
                    f"{b:g} × "
                    f"{a:g} mm block of {material} would weigh ({bound_kg:.3g} kg).",
                    recommended_correction="Check the mass and its unit.",
                )
            )
    if not judged:
        raise NotApplicable("no stated mass with a known material and enough dimensions")
    return out
