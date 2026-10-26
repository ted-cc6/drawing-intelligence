"""Metric thread checks against the ISO 261 sizes and the IS 4218 tolerance classes (config/reference)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import MetricThreads
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, PageExtraction, TextItem, TextLine

REVIEWER = "checks"

# "M8", "M20 x 1.5", "M18X 2.5 P", "M10x1.25-6H", "M8 x 16 DEEP" (16 is a depth, not a pitch)
_THREAD = re.compile(
    r"(?<![\w.])M\s?(?P<d>\d+(?:\.\d+)?)(?![\d.]|[A-WYZa-wyz])"
    r"(?:\s*[xX×]\s*(?P<second>\d+(?:\.\d+)?)\s*(?P<p>P\b)?)?"
    r"(?:\s*-\s*(?P<cls>\d[A-Za-z](?:\d[A-Za-z])?)\b)?"
)


@dataclass(frozen=True)
class Thread:
    page: PageExtraction
    item: TextItem | TextLine
    text: str
    diameter: float
    pitch: float | None
    tolerance_class: str | None


def _is_pitch(diameter: float, second: str | None, marked: bool) -> float | None:
    """The number after 'x' is a pitch when marked 'P', or when it is pitch-sized (at most a quarter of the
    diameter, so M8 x 16 is a depth and M8 x 1 a pitch)."""
    if second is None:
        return None
    v = float(second)
    return v if marked or v <= diameter / 4 else None


def threads(ctx: ReviewContext) -> list[Thread]:
    out = []
    for page in ctx.pages:
        for item in [*page.dimensions, *page.other_numeric, *page.body_text]:
            for m in _THREAD.finditer(item.text):
                d = float(m["d"])
                out.append(
                    Thread(
                        page, item, m.group(0).strip(), d, _is_pitch(d, m["second"], bool(m["p"])), m["cls"]
                    )
                )
    return out


def _evidence(t: Thread) -> EvidenceRef:
    return (
        ev.dimension(t.page, t.item)
        if isinstance(t.item, TextItem) and t.item.id
        else ev.text(t.page, t.item)
    )


class TableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


def _table(ctx: ReviewContext, name: str) -> MetricThreads:
    table = ctx.reference.get(name)
    if not isinstance(table, MetricThreads):
        raise NotCheckable(f"reference table {name!r} is not loaded")
    return table


@check("standard_thread_size", TableParams)
def standard_thread_size(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """A metric thread has an ISO 261 diameter and, where a pitch is given, one of that size's pitches."""
    table = _table(ctx, params.table)
    found = [t for t in threads(ctx) if t.diameter <= table.largest]
    if not found:
        raise NotApplicable("no metric threads up to M80")
    out = []
    for t in found:
        if t.diameter not in table.sizes:
            problem, fix = f"M{t.diameter:g} is not an ISO 261 size", "Use a standard size (e.g. M12, M16)."
        elif t.pitch is not None and t.pitch not in table.pitches(t.diameter):
            allowed = ", ".join(f"{p:g}" for p in sorted(table.pitches(t.diameter), reverse=True))
            problem, fix = (
                f"M{t.diameter:g} has no {t.pitch:g} pitch (ISO 261: {allowed})",
                "Use a standard pitch.",
            )
        else:
            continue
        out.append(
            new_finding(rule, reviewer=REVIEWER, evidence=[_evidence(t)], comment=f"'{t.text}': {problem}.",
                        recommended_correction=fix)
        )  # fmt: skip
    return out


class ClassParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    internal_classes: list[str]
    external_classes: list[str]
    table: str


@check("thread_tolerance_class_valid", ClassParams)
def thread_tolerance_class_valid(ctx: ReviewContext, rule: Rule, params: ClassParams) -> list[Finding]:
    """A thread tolerance class is one the IS 4218 table gives for the size (5H/6H/7H nut, 4h/6g/8g bolt).
    Whether a capital class sits on an internal thread needs to know the feature (the vision pass)."""
    table = _table(ctx, params.table)
    found = [t for t in threads(ctx) if t.tolerance_class]
    if not found:
        raise NotApplicable("no thread tolerance classes")
    smallest = {c: d for kind in table.tolerance_classes.values() for c, d in kind.items()}
    out = []
    for t in found:
        c = t.tolerance_class or ""
        if c not in {*params.internal_classes, *params.external_classes}:
            listed = ", ".join(params.internal_classes + params.external_classes)
            problem = f"{c} is not one of the tabulated classes ({listed})"
        elif t.diameter < smallest.get(c, 0):
            problem = f"{c} is not given for M{t.diameter:g} (from M{smallest[c]:g})"
        else:
            continue
        out.append(
            new_finding(rule, reviewer=REVIEWER, evidence=[_evidence(t)], comment=f"'{t.text}': {problem}.",
                        recommended_correction="Use a tabulated class (6H for a tapped hole, 6g for a bolt).")
        )  # fmt: skip
    return out
