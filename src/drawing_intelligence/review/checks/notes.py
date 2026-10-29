"""Checks on the drawing body's text: notes, deferrals, placeholders, number formats, hardness callouts."""

from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, check
from drawing_intelligence.review.checks._text import COLUMN_TOLERANCE, numbered_lists
from drawing_intelligence.review.checks._text import term as _term_pattern
from drawing_intelligence.review.checks._tolerance import decimals, tolerances
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import Finding, PageExtraction, TextItem, TextLine

REVIEWER = "checks"


def _body(ctx: ReviewContext) -> list[tuple[PageExtraction, TextLine]]:
    return [(p, ln) for p in ctx.pages for ln in p.body_text]


def _values(ctx: ReviewContext) -> list[tuple[PageExtraction, TextItem]]:
    return [(p, d) for p in ctx.pages for d in [*p.dimensions, *p.other_numeric]]


def _flag(
    rule: Rule,
    page: PageExtraction,
    item: TextItem | TextLine,
    comment: str,
    fix: str,
    result: Literal["fail", "warning"] | None = None,
) -> Finding:
    evidence = ev.dimension(page, item) if isinstance(item, TextItem) and item.id else ev.text(page, item)
    return new_finding(
        rule,
        reviewer=REVIEWER,
        evidence=[evidence],
        comment=comment,
        recommended_correction=fix,
        result=result,
    )


class PhraseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phrases: list[str]


@check("no_model_deferral", PhraseParams)
def no_model_deferral(ctx: ReviewContext, rule: Rule, params: PhraseParams) -> list[Finding]:
    """No size is left to the 3D model ('SEE 3D', 'AS PER MODEL'): the drawing must define the part."""
    pattern = re.compile("|".join(re.escape(p) for p in params.phrases), re.IGNORECASE)
    return [
        _flag(
            rule,
            page,
            ln,
            f"'{ln.text}' defers to the model instead of dimensioning the part.",
            "Give the dimension on the drawing.",
        )
        for page, ln in _body(ctx)
        if pattern.search(ln.text)
    ]


class PlaceholderParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patterns: list[str]


@check("no_placeholder_text", PlaceholderParams)
def no_placeholder_text(ctx: ReviewContext, rule: Rule, params: PlaceholderParams) -> list[Finding]:
    """No note keeps an unfilled template blank ('H.T.PROCESS : XXXXX', 'TBD').

    A run of X's on its own is PARI's way of marking an area on a view (the hardened zone, an engraving),
    so an X placeholder only counts after a field label and its colon.
    """
    other = [re.escape(p) for p in params.patterns if p.upper().strip("X")]
    pattern = re.compile(r":\s*X{3,}\b" + "".join(f"|{p}" for p in other), re.IGNORECASE)
    return [
        _flag(
            rule,
            page,
            ln,
            f"'{ln.text}' still holds a template blank.",
            "Fill in the value, or remove the note if it does not apply.",
        )
        for page, ln in _body(ctx)
        if pattern.search(ln.text)
    ]


@check("leading_zero_decimal")
def leading_zero_decimal(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Decimals below 1 have a leading zero (0.5, not .5): a lost point turns .5 into 5."""
    pattern = re.compile(r"(?<![\w.])\.\d")  # not after a letter: hole tags like "A.1" are labels
    return [
        _flag(
            rule,
            page,
            d,
            f"'{d.text}' writes a decimal below 1 without its leading zero.",
            "Write the leading zero (0.5).",
        )
        for page, d in _values(ctx)
        if pattern.search(d.text)
    ]


class GroupingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_separator: str = "space"
    group_from_digits: int = 5


@check("digit_grouping", GroupingParams)
def digit_grouping(ctx: ReviewContext, rule: Rule, params: GroupingParams) -> list[Finding]:
    """No comma as a thousands separator (1,200): read as a decimal comma it is 1000 times smaller."""
    pattern = re.compile(r"\d,\d{3}(?!\d)")
    return [
        _flag(
            rule,
            page,
            d,
            f"'{d.text}' uses a comma to group digits.",
            "Write the number without a comma (1200), or group five or more digits with a space.",
        )
        for page, d in _values(ctx)
        if pattern.search(d.text)
    ]


class HardnessParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    HRC: list[float]
    HRB: list[float]
    HB_max_steel_ball: float
    HB_max_carbide_ball: float


_HARDNESS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:(?:-|~|–|TO)\s*(\d+(?:\.\d+)?))?\s*(HRC|HRB|HB|BHN)\b", re.IGNORECASE
)


@check("hardness_value_in_scale_range", HardnessParams)
def hardness_value_in_scale_range(ctx: ReviewContext, rule: Rule, params: HardnessParams) -> list[Finding]:
    """A hardness lies in its scale's working range ('15 HRC' or '450 HB' means the wrong scale or a typo)."""
    found = [(p, ln, m) for p, ln in _body(ctx) for m in _HARDNESS.finditer(ln.text)]
    if not found:
        raise NotApplicable("no hardness value")
    out = []
    for page, ln, m in found:
        scale = m.group(3).upper().replace("BHN", "HB")
        low, high = {"HRC": params.HRC, "HRB": params.HRB}.get(scale, [0, params.HB_max_carbide_ball])
        bad = [v for v in (m.group(1), m.group(2)) if v is not None and not low <= float(v) <= high]
        if bad:
            out.append(
                _flag(
                    rule,
                    page,
                    ln,
                    f"{', '.join(bad)} {scale} is outside the {scale} scale's range ({low:g}-{high:g}).",
                    "Check the value and the scale.",
                )
            )
    return out


# A heat-treatment instruction, not any mention of hardening ("LM GUIDE ROD (HARDENED & GROUND)" names a
# bought-out part; a revision note may say "HARDENING NOTE REMOVED").
_HEAT = re.compile(
    r"(\bTO\s+BE\b|H\.?\s*T\.?\s*PROCESS\s*:).*(HARDEN|TOUGHEN|TEMPER|CARBURI[SZ]|NITRID|INDUCTION|FLAME)",
    re.IGNORECASE,
)
_CASE = re.compile(r"CASE\s*HARDEN|CARBURI[SZ]|NITRID|INDUCTION|FLAME", re.IGNORECASE)
_HARDNESS_VALUE = re.compile(r"\b(HRC|HRB|HB|HV|BHN)\b|\bHARDNESS\b.*\d", re.IGNORECASE)


@check("hardness_spec_complete")
def hardness_spec_complete(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A heat treatment states its hardness; a surface hardening (case, induction) its depth too."""
    heat = [(p, ln) for p, ln in _body(ctx) if _HEAT.search(ln.text)]
    if not heat:
        raise NotApplicable("no heat treatment in the notes")
    out = []
    for page in ctx.pages:
        lines = [ln for p, ln in heat if p is page]
        if not lines:
            continue
        text = " ".join(ln.text for ln in page.body_text)
        missing = []
        if not _HARDNESS_VALUE.search(text):
            missing.append("a hardness value")
        if any(_CASE.search(ln.text) for ln in lines) and "DEPTH" not in text.upper():
            missing.append("the case depth")
        if missing:
            out.append(
                _flag(
                    rule,
                    page,
                    lines[0],
                    f"The heat treatment '{lines[0].text}' does not state {' or '.join(missing)}.",
                    "State the hardness (e.g. 58-62 HRC) and, for a surface hardening, the case depth.",
                )
            )
    return out


@check("general_notes_consecutive")
def general_notes_consecutive(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """Numbered notes run 1, 2, 3 ... with no gap, repeat or wrong start (a gap may be a deleted note)."""
    found = [(p, lst) for p in ctx.pages for lst in numbered_lists(ctx, p)]
    if not found:
        raise NotApplicable("no numbered notes")
    out = []
    for page, lst in found:
        expected = 1
        for n, ln in lst:
            if n == expected:
                expected += 1
                continue
            what = (
                f"starts at {n}, not 1"
                if expected == 1
                else f"repeats {n}"
                if n == expected - 1
                else f"goes from {expected - 1} to {n}"
            )
            out.append(
                _flag(
                    rule,
                    page,
                    ln,
                    f"Note numbering {what} ('{ln.text}').",
                    "Renumber the notes 1, 2, 3 ... with no gaps or repeats.",
                )
            )
            break
    return out


# "SEE NOTE 5", "REFER TO NOTE NO. 3", "AS PER NOTE 2". PARI's "REFER NOTE" with no number points at the
# general notes as a whole and is not a reference to resolve.
_NOTE_REF = re.compile(
    r"\b(?:SEE|REFER(?:\s+TO)?|AS\s+PER)\s+(?:THE\s+)?NOTES?\s*(?:NO\.?|#)?\s*(\d{1,2})\b", re.I
)


@check("note_references_resolve")
def note_references_resolve(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A numbered note reference ('SEE NOTE 5') points at a note the drawing has.

    Only the first half of the rule is checked: that a reference resolves. That every flagged note is flagged
    on the drawing field needs the flags, which stage 1 does not read.
    """
    refs = [(p, ln, m) for p, ln in _body(ctx) for m in _NOTE_REF.finditer(ln.text)]
    if not refs:
        raise NotApplicable("no numbered note reference")
    have = {n for p in ctx.pages for lst in numbered_lists(ctx, p) for n, _ in lst}
    have |= {  # the template's own notes ("1.ALL DIMENSIONS ARE ...", "1." with a point) are notes too
        int(m.group(1))
        for p in ctx.pages
        for ln in p.body_text
        if (m := re.match(r"^\s*(\d{1,2})\s*\.\s*[A-Za-z]", ln.text))
    }
    return [
        _flag(
            rule,
            page,
            ln,
            f"'{ln.text}' refers to note {m.group(1)}, which the drawing does not have.",
            "Correct the reference, or add the note.",
        )
        for page, ln, m in refs
        if int(m.group(1)) not in have
    ]


def _current(ctx: ReviewContext) -> list[tuple[PageExtraction, TextLine]]:
    """Body lines without the revision table's history ('DIA 17 MM ADDED' is a change note, not a callout)."""
    out = []
    for page in ctx.pages:
        history = {r.text for r in page.revision_rows}
        out += [(page, ln) for ln in page.body_text if ln.text not in history]
    return out


# "DIA 30", "DIA.6.6", "30 DIA", "RADIUS 5", "RAD. 5": the word where the symbol (⌀, R) belongs.
_WORD_FORM = re.compile(
    r"\b(?:DIA(?:METER)?|RAD(?:IUS)?)\b\.?\s*[-:=]?\s*\d|\d(?:\.\d+)?\s*(?:MM\s*)?DIA(?:METER)?\b", re.I
)


# "MAJOR DIA", "PITCH DIA": the name of a thread feature, not a diameter written out.
_THREAD_DIAMETER = re.compile(r"\b(?:MAJOR|MINOR|PITCH)\s+DIA", re.IGNORECASE)


@check("diameter_radius_symbol_prefix")
def diameter_radius_symbol_prefix(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A diameter or radius is written with its symbol (⌀ 30, R5), not as a word ('DIA 30', '30 DIA').

    A dimension value written with the word is a failure. The same word in a note ('WIRE DIA 4 mm') is a
    warning: prose may say 'DIA', but the symbol is the standard. Change notes ('DIA 17 MM ADDED') and file
    paths are history, not callouts, and 'MAJOR DIA' names a thread feature. A diameter with neither
    symbol nor word reads like a length.
    """
    out = [
        _flag(
            rule,
            page,
            d,
            f"'{d.text}' writes a diameter or radius as a word.",
            "Use the symbol: ⌀ before a diameter, R before a radius.",
        )
        for page, d in _values(ctx)
        if _WORD_FORM.search(d.text)
    ]
    values = {(page.page_number, d.text) for page, d in _values(ctx)}
    out += [
        _flag(
            rule,
            page,
            ln,
            f"The note '{ln.text}' writes a diameter or radius as a word.",
            "Use the symbol: ⌀ before a diameter, R before a radius.",
            result="warning",
        )
        for page, ln in _current(ctx)
        if _WORD_FORM.search(ln.text)
        and (page.page_number, ln.text) not in values
        and not _CHANGE_NOTE.search(ln.text)
        and not _THREAD_DIAMETER.search(ln.text)
        and "\\" not in ln.text
    ]
    return out


class UnitExamplesParams(BaseModel):
    """The rulebook's examples; kept so the rule's params validate (the check needs none)."""

    model_config = ConfigDict(extra="forbid")
    examples: list[str] = []


# A torque, pressure or preload with a number right after it and no unit: "TORQUE 25", "PRESSURE: 6".
_QUANTITY = re.compile(
    r"\b(?P<what>TORQUE|PRESSURE|PRELOAD)\b\s*(?:TO|OF|=|:|-)*\s*(?P<value>\d+(?:[.,]\d+)?)(?P<rest>.{0,10})",
    re.I,
)
_UNIT = re.compile(r"\s*(?:N\s*[.·]?\s*M\b|NM\b|KGF|KG\b|KPA|MPA|BAR\b|PSI|LBF|LB\b|N\b|%)", re.I)


@check("non_length_value_has_unit", UnitExamplesParams)
def non_length_value_has_unit(ctx: ReviewContext, rule: Rule, _: UnitExamplesParams) -> list[Finding]:
    """A torque, pressure or preload value carries its unit (25 N·m, 6 bar): the drawing's unit is mm."""
    return [
        _flag(
            rule,
            page,
            ln,
            f"'{ln.text}' gives a {m['what'].lower()} of {m['value']} with no unit.",
            "Write the unit with the value (N·m, kPa, bar, ...).",
        )
        for page, ln in _current(ctx)
        for m in _QUANTITY.finditer(ln.text)
        if not _UNIT.match(m["rest"])
    ]


class AngleFormatParams(BaseModel):
    """The rulebook's formats; the check accepts one format per drawing, whichever it is."""

    model_config = ConfigDict(extra="forbid")
    preferred: str
    allowed: list[str]


# Degrees-minutes(-seconds): 30°15', 30°15'20". The stray ' the text layer prints after THRU is not one.
_DMS = re.compile(r"\d\s*°\s*\d+\s*['′]|\d\s*['′]\s*\d+\s*[\"″]")
_DECIMAL_ANGLE = re.compile(r"\d\s*°(?!\s*\d+\s*['′])")
_RADIANS = re.compile(r"\d\s*RAD\b", re.I)


@check("angle_format_consistent", AngleFormatParams)
def angle_format_consistent(ctx: ReviewContext, rule: Rule, _: AngleFormatParams) -> list[Finding]:
    """Angles use one format on the drawing (30.5° or 30°30'), and never radians."""
    angles = [(p, d) for p, d in _values(ctx) if "°" in d.text or _RADIANS.search(d.text)]
    if not angles:
        raise NotApplicable("no angles")
    out = []
    for page, d in angles:
        if _RADIANS.search(d.text):
            out.append(
                _flag(rule, page, d, f"'{d.text}' gives an angle in radians.", "Give angles in degrees.")
            )
    dms = [(p, d) for p, d in angles if _DMS.search(d.text)]
    decimal = [(p, d) for p, d in angles if _DECIMAL_ANGLE.search(d.text) and not _DMS.search(d.text)]
    if dms and decimal:
        page, d = dms[0]
        out.append(
            _flag(
                rule,
                page,
                d,
                f"'{d.text}' is in degrees and minutes, but other angles are decimal degrees "
                f"(such as '{decimal[0][1].text}').",
                "Use one angle format throughout.",
            )
        )
    return out


class PitchNotationParams(BaseModel):
    """The rulebook's forms and examples; the check reads both 'x' and '@'."""

    model_config = ConfigDict(extra="forbid")
    forms: list[str]
    examples: list[str] = []


# "4 x 60 = 240", "7@75=525": count, pitch, total.
_PITCH = re.compile(
    r"(?<![\d.])(?P<n>\d+)\s*(?:[xX×]|@)\s*(?P<pitch>\d+(?:\.\d+)?)\s*=\s*(?P<total>\d+(?:\.\d+)?)(?![\d.])"
)


@check("pitch_notation_arithmetic", PitchNotationParams)
def pitch_notation_arithmetic(ctx: ReviewContext, rule: Rule, _: PitchNotationParams) -> list[Finding]:
    """For equal spacing written count x pitch = total, the product is the total (4 x 60 = 240)."""
    found = [(p, d, m) for p, d in _values(ctx) for m in _PITCH.finditer(d.text)]
    if not found:
        raise NotApplicable("no count x pitch = total dimension")
    return [
        _flag(
            rule,
            page,
            d,
            f"'{m.group(0)}': {m['n']} x {m['pitch']} is {int(m['n']) * float(m['pitch']):g}, "
            f"not {m['total']}.",
            "Correct the pitch, the count or the total.",
        )
        for page, d, m in found
        if abs(int(m["n"]) * float(m["pitch"]) - float(m["total"])) > 0.005
    ]


class CounterboreParams(BaseModel):
    """The rulebook's list of what a full callout holds; the check tests the depth only."""

    model_config = ConfigDict(extra="forbid")
    required: list[str]
    example: dict[str, float]


# A counterbore callout that gives its diameter ("C'BORE Ø 18 mm"); the bare word in a general note, or a hole
# callout ending "& C'BORE" whose size is drawn elsewhere, is not one.
_COUNTERBORE = re.compile(r"(?:C['’`]?\s?BORE|COUNTER-?\s?BORE)[^\d\n]{0,4}\d", re.I)
_DEPTH = re.compile(r"\d.*(?:DEEP|DEPTH)|↧", re.I)
_LINE_GAP = 14.0  # pts: a callout's second line starts within this of the first line's bottom


def _callout(page: PageExtraction, first: TextLine) -> str:
    """The line plus the lines directly under it in the same column ("C'BORE Ø 18 mm" / "- 10.8 mm DEEP")."""
    parts, last = [first.text], first
    for ln in sorted(page.body_text, key=lambda t: t.bbox[1]):
        if (
            ln is not first
            and abs(ln.bbox[0] - last.bbox[0]) <= COLUMN_TOLERANCE
            and 0 <= ln.bbox[1] - last.bbox[3] <= _LINE_GAP
        ):
            parts.append(ln.text)
            last = ln
    return " ".join(parts)


@check("counterbore_callout_complete", CounterboreParams)
def counterbore_callout_complete(ctx: ReviewContext, rule: Rule, _: CounterboreParams) -> list[Finding]:
    """A counterbore callout gives its depth ("C'BORE Ø 18 mm - 10.8 mm DEEP").

    Only the depth is checked: the hole's own diameter is a separate callout that text alone cannot tie to it.
    """
    bores = [(p, ln) for p, ln in _current(ctx) if _COUNTERBORE.search(ln.text)]
    if not bores:
        raise NotApplicable("no counterbore callout")
    return [
        _flag(
            rule,
            page,
            ln,
            f"The counterbore '{ln.text}' gives no depth.",
            "Add the counterbore depth (e.g. '- 6 mm DEEP').",
        )
        for page, ln in bores
        if not _DEPTH.search(_callout(page, ln))
    ]


class SofteningParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    softening_terms: list[str]
    annealed_max_hb: dict[str, list[float]]
    hardening_terms: list[str]


_HRC_AT_ANNEALED_MAX = 26.0  # HRC of the highest annealed hardness in the rule's table, 260 HB (ASTM E140)


@check("softening_treatment_vs_hardness", SofteningParams)
def softening_treatment_vs_hardness(ctx: ReviewContext, rule: Rule, params: SofteningParams) -> list[Finding]:
    """A drawing whose only heat treatment softens the steel does not also ask for a hardened-level hardness.

    Stress relieving after hardening is normal, so the check stays silent when any hardening is named.
    """
    soften = [_term_pattern(t) for t in params.softening_terms]
    harden = [_term_pattern(t) for t in params.hardening_terms]
    max_hb = max(v for limits in params.annealed_max_hb.values() for v in limits)
    lines = _current(ctx)
    softening = [(p, ln) for p, ln in lines if any(t.search(ln.text) for t in soften)]
    if not softening:
        raise NotApplicable("no softening heat treatment")
    if any(t.search(ln.text) for _, ln in lines for t in harden):
        return []
    out = []
    for page, ln in lines:
        for m in _HARDNESS.finditer(ln.text):
            scale = m.group(3).upper().replace("BHN", "HB")
            high = float(m.group(2) or m.group(1))
            if (scale == "HRC" and high > _HRC_AT_ANNEALED_MAX) or (scale == "HB" and high > max_hb):
                out.append(
                    _flag(
                        rule,
                        page,
                        ln,
                        f"'{ln.text}' asks for a hardened-level hardness, but the only heat treatment named "
                        f"('{softening[0][1].text}') softens it (annealed steel is at most {max_hb:g} HB).",
                        "Name the hardening process, or correct the hardness.",
                    )
                )
    return out


_SIXTEENTH_INCH_MM = 25.4 / 16  # 1.5875 mm


@check("soft_metric_conversion_suspect")
def soft_metric_conversion_suspect(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A size that is an exact inch fraction written in mm (19.05 = 3/4 in) may be a soft conversion.

    Only sizes with two or more decimals once trailing zeros are dropped (CAD prints 25.40 for 25.4), so that
    6.35, 19.05 and 31.75 count but 12.7 and 25.4 do not. A warning: an imperial interface can be right.
    """
    out = []
    for page in ctx.pages:
        for tol in tolerances(page):
            text = tol.nominal_text.rstrip("0") if "." in tol.nominal_text else tol.nominal_text
            if tol.nominal < 3 or decimals(text) < 2:
                continue
            fraction = tol.nominal / _SIXTEENTH_INCH_MM
            if abs(fraction - round(fraction)) * _SIXTEENTH_INCH_MM > 0.0051:
                continue
            whole, part = divmod(Fraction(round(fraction), 16), 1)
            inches = f"{whole} {part}" if part and whole else str(part or whole)
            out.append(
                _flag(
                    rule,
                    page,
                    tol.dim,
                    f"'{tol.dim.text}': {tol.nominal_text} mm equals {inches} in, so it may be an inch "
                    "value converted to mm.",
                    "Confirm the size is meant in mm; for a metric design round it to a hard metric value.",
                    result="warning",
                )
            )
    return out


# A welding note offers two options and the designer keeps one: "APPLICABLE" / "NOT APPLICABLE",
# "REQUIRED" / "NOT REQUIRED" (PARI's welding guideline: "choose only one details from the options").
_OPTION = re.compile(r"^\s*(NOT\s+)?(APPLICABLE|REQUIRED)\s*$", re.IGNORECASE)
_BOTH_ON_ONE_LINE = re.compile(r"\b(NOT\s+)?(APPLICABLE|REQUIRED)\s*/\s*(NOT\s+)?\2\b", re.IGNORECASE)
_OPTION_X, _OPTION_Y = 8.0, 14.0  # pts: the two options of one note are stacked, left edges aligned


def _note_label(page: PageExtraction, option: TextLine) -> TextLine | None:
    """The note's own words, left of its options on the same row ("1) DYE PENETRATION TEST FOR WELDING -")."""
    row = [
        o
        for o in page.body_text
        if o is not option
        and o.bbox[2] <= option.bbox[0] + 5
        and abs((o.bbox[1] + o.bbox[3]) / 2 - (option.bbox[1] + option.bbox[3]) / 2) <= 12
        and not _OPTION.match(o.text)
    ]
    return max(row, key=lambda o: o.bbox[2], default=None)


@check("weld_note_options_resolved")
def weld_note_options_resolved(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A welding note keeps one of its options; both printed means none was chosen."""
    options: list[tuple[PageExtraction, TextLine, bool, str]] = []
    out = []
    for page in ctx.pages:
        for ln in {(t.text, t.bbox): t for t in page.body_text}.values():
            m = _OPTION.match(ln.text)
            if m:
                options.append((page, ln, bool(m.group(1)), m.group(2).upper()))
            elif _BOTH_ON_ONE_LINE.search(ln.text):
                options.append((page, ln, True, "BOTH"))
                out.append(
                    _flag(
                        rule,
                        page,
                        ln,
                        f"'{ln.text}' offers both options.",
                        "Keep only the option that applies.",
                    )
                )
    if not options:
        raise NotApplicable("no welding-note options")
    for page, ln, negative, word in options:
        partner = next(
            (
                o
                for o in options
                if o[0] is page
                and o[2]
                and o[3] == word
                and abs(o[1].bbox[0] - ln.bbox[0]) <= _OPTION_X
                and abs(o[1].bbox[1] - ln.bbox[1]) <= _OPTION_Y
            ),
            None,
        )
        if not negative and partner:
            label = _note_label(page, ln)
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, t) for t in (label, ln, partner[1]) if t is not None],
                    comment=f"{f'{label.text!r}: ' if label else ''}'{ln.text}' and '{partner[1].text}' are "
                    "both printed, so no option was chosen.",
                    recommended_correction="Delete the option that does not apply.",
                )
            )
    return out


class ThreadCalloutParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_class: bool = False


_THREAD_SIZE = re.compile(r"(?<![\w.])M\s?\d+(?:\.\d+)?(?![\d.]|[A-WYZa-wyz])")
_HOLE_WORD = re.compile(r"\b(?:TAP(?:PED|PING)?|HOLES?)\b", re.IGNORECASE)
_DEPTH_WORD = re.compile(r"THRU|THROUGH|DEEP|DEPTH|↧|\bDP\b", re.IGNORECASE)
_CHANGE_NOTE = re.compile(
    r"\b(?:ADDED|CHANGED|REVISED|UPDATED|REMOVED|MODIFIED|CORRECTED|SHIFTED|DELETED|MISSING|NOS?)\b",
    re.IGNORECASE,
)


@check("thread_callout_complete", ThreadCalloutParams)
def thread_callout_complete(ctx: ReviewContext, rule: Rule, params: ThreadCalloutParams) -> list[Finding]:
    """A tapped-hole callout gives its depth or THRU ('M6 x 12 DEEP', 'M6 THRU').

    Only text that names a hole or tapping is judged: a bare 'M8' label cannot be told from an external
    thread, and change notes ('M6 TAP HOLE ADDED') describe history. The class is checked only if asked.
    """
    callouts = [
        (p, ln)
        for p, ln in _current(ctx)
        if _THREAD_SIZE.search(ln.text) and _HOLE_WORD.search(ln.text) and not _CHANGE_NOTE.search(ln.text)
    ]
    if not callouts:
        raise NotApplicable("no tapped-hole callout")
    out = []
    for page, ln in callouts:
        missing = []
        if not _DEPTH_WORD.search(_callout(page, ln)):
            missing.append("its depth (or THRU)")
        if params.require_class and not re.search(r"-\s*\d[A-Za-z]\b", ln.text):
            missing.append("its tolerance class")
        if missing:
            out.append(
                _flag(
                    rule,
                    page,
                    ln,
                    f"The thread callout '{ln.text}' does not give {' or '.join(missing)}.",
                    "Complete the callout, e.g. 'M6 x 12 DEEP' or 'M6 THRU'.",
                )
            )
    return out


class ChamferParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formats: list[str]
    example: str | None = None


# A chamfer written with a length only ("CH1.5") or an angle only ("CH 45°"); PARI's "1 x 45°" is complete.
_CHAMFER_LENGTH_ONLY = re.compile(r"^\s*CH(?:AMFER)?\.?'?\s*(?P<v>\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_CHAMFER_ANGLE_ONLY = re.compile(r"^\s*CH(?:AMFER)?\.?'?\s*(?P<v>\d+(?:\.\d+)?)\s*°\s*$", re.IGNORECASE)
_NEIGHBOUR_X, _NEIGHBOUR_Y = (
    70.0,
    6.0,
)  # pts: the rest of a split callout ("CH0.5" then "x45°") sits just right


def _beside(page: PageExtraction, ln: TextLine, pattern: re.Pattern[str]) -> bool:
    """Another line just to the right of `ln`, on the same row, matches `pattern`."""
    return any(
        o is not ln
        and -5 <= o.bbox[0] - ln.bbox[2] <= _NEIGHBOUR_X
        and abs(o.bbox[1] - ln.bbox[1]) <= _NEIGHBOUR_Y
        and pattern.search(o.text)
        for o in page.body_text
    )


@check("chamfer_callout_complete", ChamferParams)
def chamfer_callout_complete(ctx: ReviewContext, rule: Rule, params: ChamferParams) -> list[Finding]:
    """A chamfer gives its length and its angle ('1 x 45°'), in one callout or two beside each other."""
    out, seen = [], False
    for page, ln in _current(ctx):
        if length := _CHAMFER_LENGTH_ONLY.match(ln.text):
            seen = True
            if not _beside(page, ln, re.compile(r"°|[xX×]\s*\d")):
                out.append(
                    _flag(
                        rule,
                        page,
                        ln,
                        f"The chamfer '{ln.text}' gives a length ({length['v']}) but no angle.",
                        "Give the angle too, e.g. '1 x 45°'.",
                    )
                )
        elif angle := _CHAMFER_ANGLE_ONLY.match(ln.text):
            seen = True
            if not _beside(page, ln, re.compile(r"\d")):
                out.append(
                    _flag(
                        rule,
                        page,
                        ln,
                        f"The chamfer '{ln.text}' gives an angle ({angle['v']}°) but no length.",
                        "Give the length too, e.g. '1 x 45°'.",
                    )
                )
    if not seen:
        raise NotApplicable("no chamfer callout with only a length or only an angle")
    return out


class CountersinkParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required: list[str]
    example: dict[str, float]
    screw_seat_angle_deg: float


# A countersink callout that gives its diameter ("C'SINK Ø 12 mm x 90°"); a hole callout whose countersink is
# drawn elsewhere, or the bare word in a general note, is not one.
_COUNTERSINK = re.compile(r"(?:CSK|C['’`]?\s?SINK|COUNTER-?\s?SINK)[^\d\n]{0,4}\d", re.IGNORECASE)
_ANGLE = re.compile(r"\d\s*°")


@check("countersink_callout_complete", CountersinkParams)
def countersink_callout_complete(ctx: ReviewContext, rule: Rule, params: CountersinkParams) -> list[Finding]:
    """A countersink callout gives its included angle ("C'SINK Ø 12 mm x 90°"), on its line or the next.

    The hole diameter is a separate callout that text cannot tie to the countersink, so only the
    countersink's own diameter and angle are judged. Whether the angle is the 90° of a screw seat needs
    the part, not the text.
    """
    sinks = [(p, ln) for p, ln in _current(ctx) if _COUNTERSINK.search(ln.text)]
    if not sinks:
        raise NotApplicable("no countersink callout")
    return [
        _flag(
            rule,
            page,
            ln,
            f"The countersink '{ln.text}' gives no included angle.",
            f"Add the angle (e.g. 'x {params.screw_seat_angle_deg:g}°' for a countersunk-head screw).",
        )
        for page, ln in sinks
        if not _ANGLE.search(_callout(page, ln))
    ]


class TaperParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formula: str | None = None


_TAPER_RATIO = re.compile(r"\b1\s*:\s*(?P<x>\d+(?:\.\d+)?)")
_DEGREES = re.compile(
    r"(?P<deg>\d+(?:\.\d+)?)\s*°\s*(?:(?P<min>\d+(?:\.\d+)?)\s*['′]\s*(?:(?P<sec>\d+(?:\.\d+)?)\s*[\"″])?)?"
)


@check("taper_values_consistent", TaperParams)
def taper_values_consistent(ctx: ReviewContext, rule: Rule, _: TaperParams) -> list[Finding]:
    """A taper given as a ratio 1:x and as a cone angle has the same value in both: 1/x = 2 tan(angle / 2).

    Judged only on a line that names the taper and gives both. A scale label ('SCALE 1:2') is not a taper.
    """
    found = [
        (p, ln, r, a)
        for p, ln in _current(ctx)
        if re.search(r"TAPER|CONE", ln.text, re.IGNORECASE) and (r := _TAPER_RATIO.search(ln.text))
        for a in [_DEGREES.search(ln.text[r.end() :]) or _DEGREES.search(ln.text[: r.start()])]
        if a
    ]
    if not found:
        raise NotApplicable("no taper with both a ratio and a cone angle")
    out = []
    for page, ln, ratio, angle in found:
        stated = float(angle["deg"]) + float(angle["min"] or 0) / 60 + float(angle["sec"] or 0) / 3600
        expected = math.degrees(2 * math.atan(1 / (2 * float(ratio["x"]))))
        places = len(angle["deg"].split(".")[1]) if "." in angle["deg"] and not angle["min"] else 0
        # the last printed unit is rounded: half a second, half a minute (no seconds) or half a degree
        tolerance = (
            0.5 * 10**-places
            if places
            else (0.5 / 3600 if angle["sec"] else 0.5 / 60 if angle["min"] else 0.5)
        )
        if abs(stated - expected) > tolerance:
            out.append(
                _flag(
                    rule,
                    page,
                    ln,
                    f"'{ln.text}': a 1:{ratio['x']} taper has a cone angle of {expected:.4f}°, "
                    f"not {stated:.4f}°.",
                    "Correct the ratio or the angle so that they agree.",
                )
            )
    return out


class DualDimensionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mm_per_inch: float = 25.4


# A value with a second one in brackets: "25.4 (1.00)", "1.00 [25.4]".
_DUAL = re.compile(r"^\s*[⌀Ø]?\s*(?P<a>\d+(?:\.\d+)?)\s*[\[(]\s*(?P<b>\d+(?:\.\d+)?)\s*[\])]\s*$")
_CONVERSION_BAND = 0.15  # a bracketed value within 15% of the mm/inch ratio is a conversion, not a roughness


@check("dual_dimensioning", DualDimensionParams)
def dual_dimensioning(ctx: ReviewContext, rule: Rule, params: DualDimensionParams) -> list[Finding]:
    """Where a value is written with its inch (or mm) equivalent in brackets, the equivalent is right.

    A pair counts as dual dimensioning only when one value is about 25.4 times the other: PARI's
    '3.2 (0.8)' is a roughness, not a conversion. Whether a general note explains the second value is
    not judged.
    """
    k = params.mm_per_inch
    pairs = []
    for page, d in _values(ctx):
        m = _DUAL.match(d.text)
        if not m or float(m["b"]) == 0 or float(m["a"]) == 0:
            continue
        ratio = float(m["a"]) / float(m["b"])
        if abs(ratio - k) <= _CONVERSION_BAND * k or abs(ratio - 1 / k) <= _CONVERSION_BAND / k:
            pairs.append((page, d, m, ratio > 1))
    if not pairs:
        raise NotApplicable("no dual dimension")
    out = []
    for page, d, m, primary_is_mm in pairs:
        a, b = float(m["a"]), float(m["b"])
        places = len(m["b"].split(".")[1]) if "." in m["b"] else 0
        expected = a / k if primary_is_mm else a * k
        if abs(b - expected) > 0.5 * 10**-places + 1e-9:
            out.append(
                _flag(
                    rule,
                    page,
                    d,
                    f"'{d.text}': {m['a']} {'mm' if primary_is_mm else 'in'} is {expected:.{places}f} "
                    f"{'in' if primary_is_mm else 'mm'}, not {m['b']}.",
                    "Correct the converted value (1 in = 25.4 mm).",
                )
            )
    return out
