"""Manufacturability checks on call-out text: hole depths, tapers, taper pins, centre holes (exact text)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.checks._text import all_text
from drawing_intelligence.review.context import ReviewContext
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
