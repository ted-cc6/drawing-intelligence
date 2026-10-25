"""Consistency checks: the drawing must agree with itself. Exact answers from stage 1, no LLM."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from drawing_intelligence.review.checks import _evidence as ev
from drawing_intelligence.review.checks._geometry import Drawn, drawn_dimensions, supported_scales
from drawing_intelligence.review.checks._registry import NotApplicable, NotCheckable, check
from drawing_intelligence.review.context import ReviewContext
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
