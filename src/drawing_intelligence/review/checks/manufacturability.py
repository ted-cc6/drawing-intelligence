"""Manufacturability checks on call-out text: hole depths, tapers, taper pins, centre holes (exact text)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.checks._text import all_text
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import Materials
from drawing_intelligence.review.reference_p2 import MorseTable, NumericTable
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import Finding

REVIEWER = "checks"
_NUM = r"(\d+(?:\.\d+)?)"
_MM = r"\s*(?:mm)?\s*"
# "Ø 6.40 mm x 18.00 mm DEEP", "C'BORE Ø 10.00 mm - 10.00 mm DEEP", "M6 x 12.00 mm DEEP",
# "M50 x 1.5 x 30 DEEP"
_HOLE_DEPTH = re.compile(
    r"(?:(?:[Ø⌀]|DIA\.?)\s*|(?<![\w.])M\s?)"
    + _NUM
    + r"(?:\s*[xX×]\s*\d+(?:\.\d+)?(?=\s*[xX×]))?"
    + _MM
    + r"[xX×\-]"
    + r"\s*"
    + _NUM
    + _MM
    + r"(?:DEEP|DP\b)",
    re.I,
)
_DEEP_HOLE_NOTE = re.compile(r"DEEP[\s-]*HOLE|GUN[\s-]*DRILL|DEEP[\s-]*DRILL", re.I)


def _table(ctx: ReviewContext, name: str, model: type) -> object:
    table = ctx.reference.get(name)
    if not isinstance(table, model):
        raise NotCheckable(f"reference table {name!r} not loaded (config/reference/{name}.yaml)")
    return table


class RatioParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_ratio: float


@check("depth_to_diameter", RatioParams)
def depth_to_diameter(ctx: ReviewContext, rule: Rule, params: RatioParams) -> list[Finding]:
    """A drilled or tapped hole is no deeper than `max_ratio` × its diameter, unless deep drilling is
    noted."""
    holes = [(p, item, m) for p, item in all_text(ctx) for m in _HOLE_DEPTH.finditer(item.text)]
    if not holes:
        raise NotApplicable("no hole call-out with a depth")
    if any(_DEEP_HOLE_NOTE.search(item.text) for _, item in all_text(ctx)):
        return []
    out, seen = [], set()
    for page, item, m in holes:
        d, depth = float(m[1]), float(m[2])
        if d <= 0 or depth / d <= params.max_ratio or (page.page_number, m.group(0)) in seen:
            continue
        seen.add((page.page_number, m.group(0)))
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.text(page, item)],
                comment=f"{m.group(0).strip()!r}: {depth:g} deep for a {d:g} hole is {depth / d:.1f} × D, "
                "over "
                f"{params.max_ratio:g} × D.",
                recommended_correction="Make the hole shallower or larger, or note deep drilling (gun "
                "drill).",
            )
        )
    return out


_TAPER_RATIO = re.compile(r"\b1\s*:\s*" + _NUM)
_TAPER_WORD = re.compile(r"TAPER", re.I)


class TaperParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    ratios: list[str] = []


@check("taper_ratio_standard", TaperParams)
def taper_ratio_standard(ctx: ReviewContext, rule: Rule, params: TaperParams) -> list[Finding]:
    """A taper call-out ("TAPER 1:20") uses one of IS 3458's standard ratios."""
    table = _table(ctx, params.table, NumericTable)
    assert isinstance(table, NumericTable)
    standard = set(table.values.get("denominators", []))
    tapers = [
        (p, item, m)
        for p, item in all_text(ctx)
        if _TAPER_WORD.search(item.text)
        for m in _TAPER_RATIO.finditer(item.text)
    ]
    if not tapers:
        raise NotApplicable("no taper ratio called out")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.text(page, item)],
            comment=f"The taper {m.group(0).strip()} is not one of IS 3458's standard ratios "
            f"(1:{', 1:'.join(f'{v:g}' for v in sorted(standard))}).",
            recommended_correction="Use a standard taper ratio, or note why a special taper is needed.",
        )
        for page, item, m in tapers
        if float(m[1]) not in standard
    ]


_TAPER_PIN = re.compile(r"TAPER\s*PIN", re.I)
_DIAMETER = re.compile(r"(?:[Ø⌀]|DIA\.?)\s*" + _NUM, re.I)


class TaperPinParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taper: str
    nominal_d_mm: list[float]
    table: str


@check("taper_pin_hole_callout", TaperPinParams)
def taper_pin_hole_callout(ctx: ReviewContext, rule: Rule, params: TaperPinParams) -> list[Finding]:
    """A taper-pin hole names the 1:50 taper and a standard nominal (small-end) diameter from IS 6688."""
    table = _table(ctx, params.table, NumericTable)
    assert isinstance(table, NumericTable)
    sizes = set(table.values.get("nominal_d_mm", params.nominal_d_mm))
    taper = re.compile(r"1\s*:\s*" + re.escape(params.taper.split(":")[1].strip()) + r"(?!\d)")
    pins = [(p, item) for p, item in all_text(ctx) if _TAPER_PIN.search(item.text)]
    if not pins:
        raise NotApplicable("no taper pin called out")
    out = []
    for page, item in pins:
        problems = []
        if not taper.search(item.text):
            problems.append(f"it does not state the {params.taper} taper")
        d = _DIAMETER.search(item.text) or re.search(r"TAPER\s*PIN\D{0,6}" + _NUM, item.text, re.I)
        if d is None:
            problems.append("it does not state the pin's nominal diameter")
        elif float(d[1]) not in sizes:
            problems.append(f"{float(d[1]):g} mm is not a standard IS 6688 size")
        if problems:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, item)],
                    comment=f"Taper pin call-out {item.text.strip()!r}: " + "; ".join(problems) + ".",
                    recommended_correction=f"Call out the hole as for a taper pin {params.taper} with a "
                    "standard "
                    "nominal diameter, e.g. 'TAPER PIN Ø6 (1:50) IS 6688'.",
                )
            )
    return out


_CENTRE_HOLE = re.compile(r"CENT(?:RE|ER)\s*HOLE", re.I)
_CENTRE_DESIGNATION = re.compile(r"HOLE\W{0,4}(?:TYPE\s*)?([AB])\s*[xX×\-]?\s*" + _NUM, re.I)


class CentreHoleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    types: list[str]
    d1_mm: list[float]
    type_B_max_d1_mm: float
    table: str


@check("centre_hole_designation_complete", CentreHoleParams)
def centre_hole_designation_complete(
    ctx: ReviewContext, rule: Rule, params: CentreHoleParams
) -> list[Finding]:
    """A centre-hole call-out gives its type (A or B), a standard pilot diameter and the standard
    (IS 2473)."""
    table = _table(ctx, params.table, NumericTable)
    assert isinstance(table, NumericTable)
    holes = [(p, item) for p, item in all_text(ctx) if _CENTRE_HOLE.search(item.text)]
    if not holes:
        raise NotApplicable("no centre hole called out")
    out = []
    for page, item in holes:
        problems = []
        m = _CENTRE_DESIGNATION.search(item.text)
        if m is None:
            problems.append("it gives no type and pilot diameter (e.g. A×4)")
        else:
            kind, d1 = m[1].upper(), float(m[2])
            if d1 not in set(table.values.get(kind, params.d1_mm)):
                problems.append(f"{d1:g} mm is not a standard pilot diameter for type {kind}")
            elif kind == "B" and d1 > params.type_B_max_d1_mm:
                problems.append(f"type B goes up to {params.type_B_max_d1_mm:g} mm only")
        if "2473" not in item.text:
            problems.append("it does not name the standard (IS 2473)")
        if problems:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, item)],
                    comment=f"Centre hole {item.text.strip()!r}: " + "; ".join(problems) + ".",
                    recommended_correction="Call it out as e.g. 'Centre Hole A×4 IS: 2473'.",
                )
            )
    return out


_SELF_HOLDING = re.compile(r"\b(MORSE|METRIC)\s*(?:TAPER\s*)?(?:NO\.?\s*)?(\d+)\b", re.I)
_THREAD_SIZE = re.compile(r"(?<![\w.])M\s?(\d+)(?![\d.])")


class MorseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


@check("self_holding_taper_matches_table", MorseParams)
def self_holding_taper_matches_table(ctx: ReviewContext, rule: Rule, params: MorseParams) -> list[Finding]:
    """A Morse or Metric self-holding taper has an IS 1715 designation, and a tapped-shank thread in the same
    call-out is the one IS 1715 gives for it (Morse 3: M12)."""
    table = _table(ctx, params.table, MorseTable)
    assert isinstance(table, MorseTable)
    rows = {r.designation.upper(): r for r in table.rows}
    tapers = [
        (p, item, m)
        for p, item in all_text(ctx)
        for m in _SELF_HOLDING.finditer(item.text)
        if m[1].upper() == "MORSE" or _TAPER_WORD.search(item.text)
    ]
    if not tapers:
        raise NotApplicable("no Morse or Metric taper called out")
    out = []
    for page, item, m in tapers:
        name = f"{m[1].capitalize()} {int(m[2])}"
        row = rows.get(name.upper())
        problem = None
        if row is None:
            problem = f"{name} is not an IS 1715 designation ({', '.join(r.designation for r in table.rows)})"
        elif row.thread and (t := _THREAD_SIZE.search(item.text)) and f"M{t[1]}" != row.thread:
            problem = f"the thread M{t[1]} does not match {name}'s {row.thread}"
        if problem:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, item)],
                    comment=f"{item.text.strip()!r}: {problem}.",
                    recommended_correction="Use the IS 1715 designation and its dimensions.",
                )
            )
    return out


# A blind tapped hole: "M6 x 12.00 mm DEEP", "M50 x 1.5 x 30 DEEP" (the 1.5 is the pitch)
_TAPPED = re.compile(
    r"(?<![\w.])M\s?"
    + _NUM
    + r"(?:\s*[xX×]\s*\d+(?:\.\d+)?(?=\s*[xX×]))?"
    + _MM
    + r"[xX×]\s*"
    + _NUM
    + _MM
    + r"(?:DEEP|DP\b)",
    re.I,
)
_MATERIAL_NOTE = re.compile(r"^[\W\d)]*(?:MATERIAL|MATL)\s*:\s*-?\s*(.+)$", re.I)


class EngagementParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_factor: dict[str, float]  # material family or class -> minimum thread depth as a multiple of D


def _material_kind(ctx: ReviewContext, factors: dict[str, float]) -> tuple[str, str] | None:
    """(the material as printed, the `min_factor` key it falls under): its class, else its family (steel for
    any ferrous class)."""
    materials = ctx.reference.get("materials")
    if not isinstance(materials, Materials):
        return None
    texts = [v for p in ctx.pages if (v := ev.value(p, "material")) and not ev.is_placeholder(v)]
    texts += [m[1].strip() for p in ctx.pages for ln in p.body_text if (m := _MATERIAL_NOTE.match(ln.text))]
    for text in texts:
        cls = materials.classify(text)
        if cls in factors:
            return text, cls
        if materials.family(cls) == "ferrous" and "steel" in factors:
            return text, "steel"
    return None


@check("thread_engagement", EngagementParams)
def thread_engagement(ctx: ReviewContext, rule: Rule, params: EngagementParams) -> list[Finding]:
    """A blind tapped hole is deep enough for the material: at least `min_factor` × D (1.5 × D in
    aluminium)."""
    holes = [(p, item, m) for p, item in all_text(ctx) for m in _TAPPED.finditer(item.text)]
    if not holes:
        raise NotApplicable("no blind tapped hole with a depth")
    kind = _material_kind(ctx, params.min_factor)
    if kind is None:
        raise NotCheckable("the material is not stated or not one the rule gives a factor for")
    material, key = kind
    factor = params.min_factor[key]
    out, seen = [], set()
    for page, item, m in holes:
        d, depth = float(m[1]), float(m[2])
        if depth >= factor * d or (page.page_number, m.group(0)) in seen:
            continue
        seen.add((page.page_number, m.group(0)))
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[ev.text(page, item)],
                comment=f"{m.group(0).strip()!r} in {material}: {depth:g} deep is {depth / d:.2f} × D, "
                f"under the "
                f"{factor:g} × D a thread in {key.replace('_', ' ')} needs.",
                recommended_correction=f"Tap at least {factor * d:g} deep, or use a thread insert.",
            )
        )
    return out


_HOLE_TABLE = re.compile(r"^\s*HOLE\s+TABLE\s*$", re.I)
_COORD = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")
_HAS_DEPTH = re.compile(r"THRU|DEEP|\bDP\b|↧", re.I)
ROW_PITCH = 30.0  # pts: a gap larger than this below the last row ends the table


@check("hole_table_complete")
def hole_table_complete(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Every row of a HOLE TABLE gives the hole's X, Y and its size with a depth (or THRU)."""
    out, found = [], False
    for page in ctx.pages:
        for title in [ln for ln in page.body_text if _HOLE_TABLE.match(ln.text)]:
            below = [ln for ln in page.body_text if 0 < ln.bbox[1] - title.bbox[1] < 40]
            heads = {
                key: next((ln for ln in below if ln.text.strip().upper() == key), None)
                for key in ("X", "Y", "SIZE")
            }
            if any(h is None for h in heads.values()):
                continue
            found = True
            hx, hy, hs = heads["X"], heads["Y"], heads["SIZE"]
            assert hx is not None and hy is not None and hs is not None
            right = max((ln.bbox[2] for ln in below), default=hs.bbox[2])  # the header's last column (REMARK)
            cells = sorted(
                (
                    ln
                    for ln in page.body_text
                    if ln.bbox[1] > hs.bbox[1] + 5 and hx.bbox[0] - 60 <= ln.bbox[0] <= right
                ),
                key=lambda ln: ln.bbox[1],
            )
            rows: list[list] = []
            for ln in cells:
                if rows and ln.bbox[1] - rows[-1][0].bbox[1] < 6:
                    rows[-1].append(ln)
                elif not rows or ln.bbox[1] - rows[-1][0].bbox[1] <= ROW_PITCH:
                    rows.append([ln])
                else:
                    break

            holes: list[tuple[list, str, object]] = []  # (coordinate cells, size text, first cell)
            for row in rows:
                coords = [c for c in sorted(row, key=lambda c: c.bbox[0]) if _COORD.match(c.text)]
                size = " ".join(
                    c.text for c in row if _DIAMETER.search(c.text) or _THREAD_SIZE.search(c.text)
                )
                if not coords and not size:
                    break  # past the last row of the table
                if not coords and holes:  # the size cell wraps: "C'BORE Ø 10.00 mm - 10.00 mm DEEP"
                    holes[-1] = (holes[-1][0], f"{holes[-1][1]} {size}", holes[-1][2])
                    continue
                holes.append((coords, size, row[0]))
            for coords, size, first in holes:
                missing = [
                    name
                    for name, ok in (
                        ("X and Y", len(coords) >= 2),
                        ("size", bool(size)),
                        ("depth or THRU", bool(size) and _HAS_DEPTH.search(size)),
                    )
                    if not ok
                ]
                if missing:
                    out.append(
                        new_finding(
                            rule,
                            reviewer=REVIEWER,
                            evidence=[ev.text(page, first)],  # type: ignore[arg-type]
                            comment=f"A HOLE TABLE row ({' | '.join(c.text.strip() for c in coords)} "
                            f"{size}) has "
                            f"no {', '.join(missing)}.",
                            recommended_correction="Give every hole its X, Y, size and depth (or THRU) in "
                            "the table.",
                        )
                    )
    if not found:
        raise NotApplicable("no hole table")
    return out


# Words that make a text a hole call-out rather than a shaft diameter ("⌀ 30" alone is either).
_HOLE_WORDS = re.compile(
    r"\bDRILL|\bHOLES?\b|\bTAP(?:PED|PING)?\b|C\W?BORE|\bCSK\b|C\W?SINK|SPOT\s*FACE|\bREAM", re.I
)
_SIZE = re.compile(r"(?:[Ø⌀]|DIA\.?)\s*\d|(?<![\w.])M\s?\d", re.I)
# A revision description ("2-M6 TAP & DIA.6.6 ADDED."), not a call-out
_CHANGE_WORDS = re.compile(r"\b(?:CHANGED|ADDED|REVISED|REMOVED|DELETED|UPDATED|WAS)\b", re.I)


def _depth_below(page, item) -> bool:
    """A call-out wrapped onto two lines: its depth on the line just below, at the same left edge."""
    return any(
        0 < ln.bbox[1] - item.bbox[1] <= 14
        and abs(ln.bbox[0] - item.bbox[0]) <= 40
        and _HAS_DEPTH.search(ln.text)
        for ln in page.body_text
    )


@check("hole_depth_stated")
def hole_depth_stated(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A hole call-out (DRILL, TAP, C'BORE ... with a size) states its depth or THRU. Revision rows and
    general notes about holes ("ALL HOLES ... C.D") are not call-outs."""
    calls = []
    for page, item in all_text(ctx):
        text = item.text
        revision = {r.text for r in page.revision_rows}
        if (
            text in revision
            or not (_HOLE_WORDS.search(text) and _SIZE.search(text))
            or re.search(r"\bALL\b", text, re.I)
            or _CHANGE_WORDS.search(text)
        ):
            continue
        calls.append((page, item))
    if not calls:
        raise NotApplicable("no hole call-out")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[ev.text(page, item)],
            comment=f"The hole call-out {item.text.strip()!r} gives no depth and does not say THRU.",
            recommended_correction="State the depth (e.g. '↧ 12' or 'x 12 DEEP') or THRU.",
        )
        for page, item in calls
        if not _HAS_DEPTH.search(item.text) and not _depth_below(page, item)
    ]
