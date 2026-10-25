"""Checks on the drawing body's text: notes, deferrals, placeholders, number formats, hardness callouts."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import Finding, PageExtraction, TextItem, TextLine

REVIEWER = "checks"


def _body(ctx: ReviewContext) -> list[tuple[PageExtraction, TextLine]]:
    return [(p, ln) for p in ctx.pages for ln in p.body_text]


def _values(ctx: ReviewContext) -> list[tuple[PageExtraction, TextItem]]:
    return [(p, d) for p in ctx.pages for d in [*p.dimensions, *p.other_numeric]]


def _flag(rule: Rule, page: PageExtraction, item: TextItem | TextLine, comment: str, fix: str) -> Finding:
    evidence = ev.dimension(page, item) if isinstance(item, TextItem) and item.id else ev.text(page, item)
    return new_finding(
        rule, reviewer=REVIEWER, evidence=[evidence], comment=comment, recommended_correction=fix
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
