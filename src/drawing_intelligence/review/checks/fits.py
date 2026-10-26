"""Fit and general-tolerance checks against the IS 919 and IS 2102 tables (config/reference)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import FitDeviations, GeneralTolerances
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, GeneralToleranceRow, PageExtraction, TextItem

REVIEWER = "checks"


class TableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str


def _table[T](ctx: ReviewContext, name: str, model: type[T]) -> T:
    table = ctx.reference.get(name)
    if not isinstance(table, model):
        raise NotCheckable(f"reference table {name!r} is not loaded")
    return table


# a size, then a fit code right after it ("⌀20 H7", "12 g6 -0.006"); not "0.5 X45°", "A/F16", "M8"
_FIT = re.compile(
    r"(?:^|(?<=[\s⌀Ø-]))(?P<size>\d+(?:\.\d+)?)\s*(?P<letters>[A-Za-z]{1,2})(?P<grade>\d{1,2})(?![\d.°'\"/])(?P<rest>.*)$"
)
_DEVIATION = re.compile(r"[+\-]\s*\d*\.\d+|[+\-]\s*0\b|(?<![\d.])0(?:\.0+)?(?![\d.])")


@dataclass(frozen=True)
class Fit:
    page: PageExtraction
    item: TextItem
    size: float
    letters: str
    grade: int
    deviations: tuple[str, ...]  # as printed, in mm

    @property
    def zone(self) -> str:
        return f"{self.letters}{self.grade}"


def _stacked_partner(page: PageExtraction, item: TextItem) -> list[str]:
    """A deviation printed as its own item, stacked against the fit's text (stage 1 reads '-0.018' apart)."""
    x0, y0, x1, y1 = item.bbox
    out = []
    for other in [*page.dimensions, *page.other_numeric]:
        if other is item or not re.fullmatch(r"\s*[+\-]\s*\d*\.\d+\s*", other.text):
            continue
        a0, b0, a1, b1 = other.bbox
        if a0 <= x1 + 2 and a1 >= x0 - 2 and b0 <= y1 + 2 and b1 >= y0 - 2:  # touching or overlapping
            out.append(other.text.replace(" ", ""))
    return out


def fits(ctx: ReviewContext) -> list[Fit]:
    out = []
    for page in ctx.pages:
        for item in [*page.dimensions, *page.other_numeric]:
            m = _FIT.search(item.text.strip())
            if not m or m["letters"].upper() == "X":
                continue  # "2X45°" is a chamfer: X is a legal ISO letter, but on a drawing it means "times"
            devs = [d.replace(" ", "") for d in _DEVIATION.findall(m["rest"])]
            if item.limits:
                devs = list(item.limits)
            elif len(devs) < 2:
                devs += _stacked_partner(page, item)
            out.append(Fit(page, item, float(m["size"]), m["letters"], int(m["grade"]), tuple(devs)))
    return out


def _evidence(f: Fit) -> EvidenceRef:
    return ev.dimension(f.page, f.item) if f.item.id else ev.text(f.page, f.item)


@check("fit_code_valid", TableParams)
def fit_code_valid(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """A fit code is one ISO 286 defines: a deviation letter (I, L, O, Q, W are not used), one case, a grade
    1-18. Matching the mating part's drawing needs the assembly (phase 2)."""
    table = _table(ctx, params.table, FitDeviations)
    found = fits(ctx)
    if not found:
        raise NotApplicable("no fit codes")
    return [
        new_finding(
            rule,
            reviewer=REVIEWER,
            evidence=[_evidence(f)],
            comment=f"'{f.zone}' in '{f.item.text}' is not an ISO 286 fit code.",
            recommended_correction="Use a valid tolerance zone (e.g. H7 for a hole, g6 for a shaft).",
        )
        for f in found
        if not table.valid_code(f.letters, f.grade)
    ]


def _microns(text: str) -> int:
    return round(float(text) * 1000)


def _signed(um: int) -> str:
    return "0" if um == 0 else f"{um / 1000:+.3f}"


@check("fit_deviations_match_table", TableParams)
def fit_deviations_match_table(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """A fit printed with its deviations has the deviations IS 919 gives for that zone and size."""
    table = _table(ctx, params.table, FitDeviations)
    found = [(f, devs) for f in fits(ctx) if f.deviations and (devs := table.deviations(f.zone, f.size))]
    if not found:
        raise NotApplicable("no tabulated fit printed with deviations")
    out = []
    for f, (upper, lower) in found:
        wrong = [d for d in f.deviations if _microns(d) not in (upper, lower)]
        if wrong:
            out.append(
                new_finding(
                    rule,
                    reviewer=REVIEWER,
                    evidence=[_evidence(f)],
                    comment=f"{f.size:g} {f.zone} is {_signed(upper)}/{_signed(lower)} by IS 919; "
                    f"the drawing gives {' / '.join(f.deviations)}.",
                    recommended_correction=f"Use {_signed(upper)}/{_signed(lower)}, or correct the fit code.",
                )
            )
    return out


def _range(r: GeneralToleranceRow) -> str:
    return f"over {r.over:g}" if r.up_to is None else f"{r.over:g}-{r.up_to:g}"


_ANGLE = re.compile(r"±\s*(?:(\d+(?:\.\d+)?)\s*°)?\s*(?:(\d+)\s*['′])?")


def _minutes(text: str) -> float | None:
    m = _ANGLE.search(text)
    if not m or (m[1] is None and m[2] is None):
        return None
    return float(m[1] or 0) * 60 + float(m[2] or 0)


@check("general_tolerance_table_matches", TableParams)
def general_tolerance_table_matches(ctx: ReviewContext, rule: Rule, params: TableParams) -> list[Finding]:
    """Each printed general-tolerance table (machining, fabrication; linear, angular) is one IS 2102 class:
    every row equals that class's value for the step it starts at (steps the book leaves blank aside)."""
    table = _table(ctx, params.table, GeneralTolerances)
    pages = [p for p in ctx.pages if p.general_tolerances]
    if not pages:
        raise NotApplicable("no general tolerance table printed")
    out = []
    for page in pages:
        for process in ("machining", "fabrication"):
            for kind in ("linear", "angular"):
                rows = [r for r in page.general_tolerances if r.process == process and r.kind == kind]
                if not rows:
                    continue
                ref = table.linear if kind == "linear" else table.angular
                printed = [(r, r.value_mm if kind == "linear" else _minutes(r.tolerance)) for r in rows]
                misses: dict[str, list[str]] = {}
                for name, values in ref.classes().items():
                    misses[name] = []
                    for r, v in printed:
                        i = ref.step_from(r.over)
                        want = values[i] if i is not None else None
                        if v is not None and want is not None and abs(v - want) > 1e-9:
                            unit = "" if kind == "linear" else "'"
                            misses[name].append(f"{_range(r)}: {r.tolerance}, {name} ±{want:g}{unit}")
                if any(not m for m in misses.values()):
                    continue
                closest = min(misses, key=lambda n: len(misses[n]))
                out.append(
                    new_finding(
                        rule,
                        reviewer=REVIEWER,
                        evidence=[
                            EvidenceRef(kind="region", page=page.page_number, bbox=list(r.bbox),
                                        quote=r.tolerance, provenance="pdf_text")
                            for r, _ in printed if any(x.startswith(_range(r) + ":") for x in misses[closest])
                        ][:3],
                        comment=f"The {process} {kind} general-tolerance table matches no IS 2102 class; "
                        f"closest is {closest}, which differs at {'; '.join(misses[closest])}.",
                        recommended_correction="Use the template's table: IS 2102 medium (machining), "
                        "coarse (fabrication).",
                    )
                )  # fmt: skip
    return out
