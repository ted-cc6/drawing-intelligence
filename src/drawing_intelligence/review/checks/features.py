"""Split checks: stage 2's tagger says which dimension is a keyway's width or an undercut's diameter (an AI
judgement), and code compares the value with the standard table (2026-11-13).

Without the tagger (no understanding run) these rules are not checked. A finding rests on the tagger's reading
of the drawing, so these rules only warn (`result: warning` in the rulebook).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.extraction.geometry import nominal_value
from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import MetricThreads
from drawing_intelligence.review.reference_p2 import KeywayRow, Keyways, UndercutRow, UndercutTable
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import DimensionTag, EvidenceRef, Finding, PageExtraction, TextItem

REVIEWER = "checks"


@dataclass(frozen=True)
class Tagged:
    page: PageExtraction
    tag: DimensionTag
    dim: TextItem


def tagged(ctx: ReviewContext, *roles: str) -> list[Tagged]:
    """The dimensions the tagger gave one of `roles`, with stage 1's exact text."""
    if not ctx.tagged:
        raise NotCheckable("no dimension tags (the understanding and tagger did not run)")
    out = []
    for page in ctx.pages:
        dims = ev.dims_by_id(page)
        for t in ctx.tags.get(page.page_number, []):
            d = dims.get(t.dimension_id)
            if t.role in roles and d is not None and not _LIMIT_ONLY.fullmatch(d.text):
                out.append(Tagged(page, t, d))  # a stacked limit printed apart ("-0.2") is not a size
    return out


_LIMIT_ONLY = re.compile(r"\s*(?:0|[+\-–]\s*\d+(?:[.,]\d+)?)\s*")
_DIAMETER = re.compile(r"[Ø⌀фO]\s*(\d+(?:[.,]\d+)?)|DIA\.?\s*(\d+(?:[.,]\d+)?)", re.I)


def _value(text: str) -> float | None:
    """A dimension's nominal number: "Ø30 h7" -> 30, "R 0.5" -> 0.5, "8 P9" -> 8."""
    m = re.search(r"\d+(?:[.,]\d+)?", text.replace("⌀", "").replace("Ø", ""))
    return float(m[0].replace(",", ".")) if m else nominal_value(text)


def _of(t: Tagged) -> tuple[float, EvidenceRef | None] | None:
    """The shaft or bore diameter a keyway or groove is in: the Ø dimension the tagger names, or the Ø it
    quotes (a bar size in a note). Anything that is not marked as a diameter is not used: a keyway's d - t1
    (16.5) read as the shaft would be judged against the wrong row."""
    if not t.tag.of:
        return None
    dims = ev.dims_by_id(t.page)
    d = dims.get(t.tag.of.strip())
    m = _DIAMETER.search(d.text if d is not None else t.tag.of)
    if not m:
        return None
    v = float((m[1] or m[2]).replace(",", "."))
    return v, (ev.dimension(t.page, d) if d is not None else None)


# --- WST-206: fit letter case matches the feature -----------------------------------------------------------

_FIT_LETTERS = re.compile(r"(?<![A-Za-z])([A-Za-z]{1,2})(\d{1,2})(?![\d.])")


@check("fit_letter_case_matches_feature")
def fit_letter_case_matches_feature(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A fit on an internal feature (hole, bore, slot) uses a capital letter (H7), one on an external feature
    (shaft, pin, key) a lower-case letter (g6). The tagger says which feature a fit is on, from the feature
    and not from the letter."""
    fits = tagged(ctx, "internal_fit", "external_fit")
    found = [
        (t, m) for t in fits if (m := _FIT_LETTERS.search(t.dim.text)) and m[1].upper() not in ("M", "X")
    ]
    if not found:
        raise NotApplicable("no fit code on a feature the tagger identified")
    out = []
    for t, m in found:
        letters = m[1]
        internal = t.tag.role == "internal_fit"
        if internal == letters.isupper():
            continue
        if not letters.isupper() and not letters.islower():
            continue  # mixed case (Js): not judged
        feature = (
            "an internal feature (hole, bore or slot)" if internal else "an external feature (shaft or pin)"
        )
        want = letters.upper() if internal else letters.lower()
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.dimension(t.page, t.dim)],
                comment=f"{t.dim.text.strip()} is on {feature}, but its fit letter {letters} is "
                f"{'lower' if internal else 'upper'} case.",
                recommended_correction=f"Use {want}{m[2]}, or check which feature the fit is on.",
            )
        )
    return out


# --- MC-007: keyways ----------------------------------------------------------------------------------------


class TableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


_CALLOUT = re.compile(r"[xX×°]")  # a chamfer or count call-out is never a keyway's or an undercut's size


def _plausible_keyway(role: str, value: float, d: float) -> bool:
    """A keyway's size is of the shaft's order (IS 2292: width 0.2-0.5 d, t1 0.1-0.2 d). The fresh run
    (2026-11-13) tagged a chamfer as a depth and the shaft's own diameter as a width."""
    if role == "keyway_width":
        return 0.15 * d <= value <= 0.5 * d
    if role == "keyway_depth_shaft":
        return 0.05 * d <= value <= 0.25 * d
    return 0.7 * d <= value < d  # keyway_bottom_shaft: d - t1


def _keyway_row(rows: list[KeywayRow], d: float) -> KeywayRow | None:
    for r in rows:
        low_ok = d >= r.shaft_over_mm if r.lower_inclusive else d > r.shaft_over_mm
        if low_ok and d <= r.shaft_up_to_mm:
            return r
    return None


@check("keyway_standard", TableParams)
def keyway_standard(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """A keyway's width and shaft depth are the standard ones for its shaft diameter (IS 2292, Westermann:
    width and keyseat depth t1 are the same series for taper and parallel keys). The hub depth differs
    between key types and is not judged; the table has no tolerances, so only nominal sizes are."""
    table = ctx.reference.get(params.table)
    if not isinstance(table, Keyways):
        raise NotCheckable(f"reference table {params.table!r} not loaded")
    keyways = tagged(ctx, "keyway_width", "keyway_depth_shaft", "keyway_bottom_shaft")
    if not keyways:
        raise NotApplicable("no keyway the tagger identified")
    out, judged = [], False
    for t in keyways:
        of = _of(t)
        value = _value(t.dim.text)
        if of is None or value is None or _CALLOUT.search(t.dim.text):
            continue
        d, of_ev = of
        if not _plausible_keyway(t.tag.role, value, d):
            continue  # the tagger's pick cannot be this shaft's keyway (a chamfer, the shaft itself)
        row = _keyway_row(table.taper_keys_is2292, d)
        if row is None:
            continue
        judged = True
        if t.tag.role == "keyway_width":
            want, what = row.width_mm, "width"
        elif t.tag.role == "keyway_depth_shaft":
            want, what = row.shaft_depth_mm, "keyseat depth t1"
        else:
            want, what = round(d - row.shaft_depth_mm, 3), "dimension to the keyseat bottom (d - t1)"
        if abs(value - want) <= 0.05:
            continue
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.dimension(t.page, t.dim), *([of_ev] if of_ev else [])],
                comment=f"The keyway {what} is {t.dim.text.strip()}; for a Ø{d:g} shaft the standard gives "
                f"{want:g} (IS 2292, {row.shaft_over_mm:g}-{row.shaft_up_to_mm:g} mm).",
                recommended_correction=f"Use {want:g}, or check the shaft diameter and key size.",
            )
        )
    if not judged:
        raise NotCheckable("keyways found, but none with a shaft diameter the table covers")
    return out


# --- MC-008: retaining-ring grooves -------------------------------------------------------------------------


@check("circlip_groove_standard", TableParams)
def circlip_groove_standard(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """A retaining-ring groove follows the ring standard. PARI has not named the standard (DIN 471/472, IS
    3075 ...), so there is no table yet: grooves the tagger finds are reported not checked."""
    grooves = tagged(ctx, "circlip_groove_diameter", "circlip_groove_width")
    if not grooves:
        raise NotApplicable("no retaining-ring groove the tagger identified")
    raise NotCheckable(
        f"{len(grooves)} groove dimension(s) found, but no {params.table!r} table: PARI to name the "
        "retaining-ring standard (DIN 471/472, IS 3075 ...)"
    )


# --- WST-242: thread undercuts ------------------------------------------------------------------------------


class UndercutParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    g1_minus_d_mm: float


_THREAD = re.compile(r"M\s?(\d+(?:\.\d+)?)(?:\s*[xX×]\s*(\d+(?:\.\d+)?))?")


def _undercut_row(rows: list[UndercutRow], d: float) -> UndercutRow | None:
    return next((r for r in rows if any(abs(d - x) < 1e-6 for x in r.diameters_mm)), None)


@check("thread_undercut_matches", UndercutParams)
def thread_undercut_matches(ctx: ReviewContext, rule: Rule, params: UndercutParams) -> list[Finding]:
    """A thread undercut is at least as wide and as round as IS 1369 gives for the thread, and deep enough: no
    larger than d - g on an external thread, at least d + 0.5 on an internal one. Coarse threads only; the
    table has no fine-pitch rows and nothing is extrapolated."""
    table = ctx.reference.get(params.table)
    if not isinstance(table, UndercutTable):
        raise NotCheckable(f"reference table {params.table!r} not loaded")
    undercuts = tagged(ctx, "undercut_width", "undercut_diameter", "undercut_radius")
    if not undercuts:
        raise NotApplicable("no thread undercut the tagger identified")
    by_id = {(t.page.page_number, t.dim.id): t for t in undercuts}
    out, judged = [], False
    for t in undercuts:
        thread_text = t.tag.of or ""
        if (d_of := ev.dims_by_id(t.page).get(thread_text.strip())) is not None:
            thread_text = d_of.text
        m = _THREAD.search(thread_text)
        value = _value(t.dim.text)
        if (
            not m
            or value is None
            or _CALLOUT.search(t.dim.text)
            or re.search(r"DEEP|\bDP\b", thread_text, re.I)
        ):
            continue  # a blind tapped hole ("M5 x 10 DEEP") has no undercut drawn
        d = float(m[1])
        if not _plausible(t.tag.role, value, d):
            continue  # the tagger's pick cannot be this thread's undercut (34.5 for an M5)
        row = _undercut_row(table.rows, d)
        if row is None or (m[2] and _fine(ctx, d, float(m[2]))):
            continue  # a size or a fine pitch the table does not have
        # external if the undercut's diameter on this thread is below d (or no diameter is tagged)
        diameters = [
            _value(o.dim.text)
            for (pg, _), o in by_id.items()
            if pg == t.page.page_number and o.tag.role == "undercut_diameter" and o.tag.of == t.tag.of
        ]
        diam = diameters[0] if diameters else None
        external = diam is None or diam < d
        judged = True
        problem = None
        if t.tag.role == "undercut_width":
            by_angle = (
                row.external_width_mm_by_min_angle_deg if external else row.internal_width_mm_by_min_angle_deg
            )
            widths = [w for w in by_angle.values() if w is not None]
            if widths and value < min(widths) - 1e-6:
                problem = f"width {value:g} is less than the {min(widths):g} IS 1369 gives for M{d:g}"
        elif t.tag.role == "undercut_radius":
            r_min = row.external_radius_mm if external else row.internal_radius_mm
            if r_min is not None and value < r_min - 1e-6:
                problem = f"radius {value:g} is less than the {r_min:g} IS 1369 gives for M{d:g}"
        elif external and row.external_g_subtract_mm is not None and d > 5:
            g = round(d - row.external_g_subtract_mm, 3)
            if value > g + 1e-6:
                problem = f"diameter {value:g} is larger than g = {g:g} (d - {row.external_g_subtract_mm:g})"
        elif not external:
            g1 = round(d + params.g1_minus_d_mm, 3)
            if value < g1 - 1e-6:
                problem = f"diameter {value:g} is smaller than g1 = {g1:g} (d + {params.g1_minus_d_mm:g})"
        if problem:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.dimension(t.page, t.dim)],
                    comment=f"The {'external' if external else 'internal'} thread undercut for "
                    f"{m[0]}: its {problem}.",
                    recommended_correction="Size the undercut to IS 1369 for the thread.",
                )
            )
    if not judged:
        raise NotCheckable("undercuts found, but none on a coarse thread the table covers")
    return out


def _plausible(role: str, value: float, d: float) -> bool:
    """An undercut's size is of the thread's order: its diameter within 0.7-1.1 d, its width at most 0.6 d,
    its radius at most 0.2 d. The held-out run (2026-11-13) tagged a bar length and tolerance fragments."""
    if role == "undercut_diameter":
        return 0.7 * d <= value <= 1.1 * d
    if role == "undercut_width":
        return value <= 0.6 * d
    return value <= 0.2 * d


def _fine(ctx: ReviewContext, d: float, pitch: float) -> bool:
    """A pitch that is not the size's coarse one (ISO 261, `iso_metric_threads`)."""
    threads = ctx.reference.get("iso_metric_threads")
    size = threads.sizes.get(d) if isinstance(threads, MetricThreads) else None
    return size is None or size.coarse is None or abs(pitch - size.coarse) > 1e-6
