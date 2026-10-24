"""Tolerance checks, on the tolerances printed in the dimension text and the general tolerance table."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.checks._tolerance import decimals, general_for, tolerances
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import Finding

REVIEWER = "checks"


@check("tolerance_limits_valid")
def tolerance_limits_valid(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A pair of limits (upper/lower, as stacked on the drawing) has the upper limit above the lower one."""
    limits = [(p, t) for p in ctx.pages for t in tolerances(p) if t.explicit and len(t.deviation_texts) == 2]
    if not limits:
        raise NotApplicable("no dimension with an upper and a lower limit")
    out = []
    for page, t in limits:
        if t.upper is not None and t.lower is not None and t.upper <= t.lower:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.dimension(page, t.dim)],
                    comment=f"{t.dim.text}: the upper limit {t.deviation_texts[0]} is not above the lower "
                    f"limit {t.deviation_texts[1]}.",
                    recommended_correction="Swap or correct the limits so that the upper one is the larger.",
                )
            )
    return out


class DecimalsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Untoleranced sizes are compared with the general tolerance without their trailing zeros ("18.00" -> 18),
    # which CAD adds by default. A size with its own tolerance is always compared as printed (10.000±0.1).
    ignore_trailing_zeros_under_general: bool = False


@check("decimals_vs_tolerance", DecimalsParams)
def decimals_vs_tolerance(ctx: ReviewContext, rule: Rule, params: DecimalsParams) -> list[Finding]:
    """A size shows no more decimals than its tolerance (its own, else the general one for its size)."""
    out = []
    checked = False
    for page in ctx.pages:
        for t in tolerances(page):
            if t.explicit:
                allowed, of = (
                    t.deviation_decimals,
                    f"its tolerance {t.dim.text[len(t.nominal_text) :].strip()}",
                )
            elif t.fit is None and (row := general_for(page, t.nominal)) is not None:
                allowed, of = (
                    decimals(row.tolerance.lstrip("±").strip()),
                    f"the general tolerance {row.tolerance}",
                )
            else:
                continue  # a fit without limits, or no general tolerance for this size
            checked = True
            shown = decimals(t.nominal_text)
            if not t.explicit and params.ignore_trailing_zeros_under_general and "." in t.nominal_text:
                shown = decimals(t.nominal_text.rstrip("0").rstrip("."))
            if shown > allowed:
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[ev.dimension(page, t.dim)],
                        comment=f"{t.dim.text} gives {shown} decimal places for {of} ({allowed}).",
                        recommended_correction=f"Write the size with {allowed} decimal places, or give "
                        "it the tolerance those decimals imply.",
                    )
                )
    if not checked:
        raise NotCheckable("no toleranced size, and no general tolerance table read")
    return out


class TighterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ratio: float | None = None  # flag a tolerance this many times tighter than the general one; None: not set


@check("tolerance_tighter_than_general", TighterParams)
def tolerance_tighter_than_general(ctx: ReviewContext, rule: Rule, params: TighterParams) -> list[Finding]:
    """A ± tolerance far tighter than the general tolerance for its size: a warning for the designer.

    Fits (H7, g6) are deliberately tight and are left out. The threshold is the rule's `ratio`.
    """
    if not params.ratio:
        raise NotCheckable("the rule's ratio is not set yet (to agree with PARI)")
    out = []
    checked = False
    for page in ctx.pages:
        for t in tolerances(page):
            row = general_for(page, t.nominal)
            if not t.explicit or t.fit or row is None or not row.value_mm or not t.band:
                continue
            checked = True
            tighter = (2 * row.value_mm) / t.band
            if tighter >= params.ratio:
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[ev.dimension(page, t.dim)],
                        comment=f"{t.dim.text} is {tighter:.0f}x tighter than the general tolerance "
                        f"{row.tolerance} for its size.",
                        recommended_correction="Confirm the function needs this tolerance and the process "
                        "can hold it; otherwise open it up.",
                        result="warning",  # the rule asks the designer to confirm, it does not reject
                    )
                )
    if not checked:
        raise NotApplicable("no ± tolerance with a general tolerance to compare")
    return out
