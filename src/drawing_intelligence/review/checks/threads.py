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


_INSERT = re.compile(r"\bINSERTS?\b|HELI-?COILS?|KEENSERTS?", re.I)
# What specifies an insert: a length ("TOTAL LENGTH", 1.5D), the tapped-hole size (M8), an item or part number
# (four digits or more) or a make (Kerb Konus, Bollhoff, Recoil). The type alone ("HELICOIL") is not one.
_INSERT_SPEC = re.compile(
    r"LENGTH|\bM\s?\d|\d(?:\.\d+)?\s*(?:MM\b|X?D\b)|\d{4,}|KERB|KONUS|B[OÖ]LLHOFF|RECOIL|TAPPEX", re.I
)


@check("insert_spec")
def insert_spec(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A threaded insert or Helicoil note says which insert: its length, hole size, part number or make.

    A revision row that mentions an insert ('THREAD INSERTS ... ADDED') is history, not a note.
    """
    out, found = [], False
    for page in ctx.pages:
        history = {r.text for r in page.revision_rows}
        notes = [ln for ln in page.body_text if _INSERT.search(ln.text) and ln.text not in history]
        if not notes:
            continue
        found = True
        if not any(_INSERT_SPEC.search(ln.text) for ln in notes):
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[ev.text(page, notes[0])],
                    comment=f"'{notes[0].text}' names no insert part number, length or hole size.",
                    recommended_correction="Give the insert's part number or size and length, or its make.",
                )
            )
    if not found:
        raise NotApplicable("no threaded insert on the drawing")
    return out


# "Tr 40x14 (P7)": nominal diameter, lead, pitch. "Tr 12 x 3P" gives a pitch only (a single start).
_TRAPEZOIDAL = re.compile(
    r"\bTr\s*(?P<d>\d+(?:\.\d+)?)\s*[xX×]\s*(?P<lead>\d+(?:\.\d+)?)\s*\(\s*P\s*(?P<pitch>\d+(?:\.\d+)?)\s*\)"
)


@check("thread_lead_multiple_of_pitch")
def thread_lead_multiple_of_pitch(ctx: ReviewContext, rule: Rule, _: object) -> list[Finding]:
    """A multi-start trapezoidal thread's lead is a whole multiple of its pitch (Tr 40x14 (P7) has two)."""
    found = [
        (page, item, m)
        for page in ctx.pages
        for item in [*page.dimensions, *page.other_numeric, *page.body_text]
        for m in _TRAPEZOIDAL.finditer(item.text)
    ]
    if not found:
        raise NotApplicable("no trapezoidal thread with lead and pitch")
    out = []
    for page, item, m in found:
        lead, pitch = float(m["lead"]), float(m["pitch"])
        starts = lead / pitch
        if pitch > 0 and abs(starts - round(starts)) < 1e-6:
            continue
        evidence = ev.dimension(page, item) if isinstance(item, TextItem) and item.id else ev.text(page, item)
        out.append(
            new_finding(
                rule,
                reviewer=REVIEWER,
                evidence=[evidence],
                comment=f"'{m.group(0)}': lead {m['lead']} is not a whole multiple of pitch {m['pitch']}.",
                recommended_correction="Correct the lead or the pitch (lead = pitch x number of starts).",
            )
        )
    return out
