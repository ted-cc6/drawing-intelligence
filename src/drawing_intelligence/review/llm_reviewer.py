"""The LLM reviewers (ADR 0010): one text-only call each over the rules that need engineering judgement.

Each reviewer gets its `llm` rules and the drawing as JSON (stage 2's `DrawingKnowledge`, no images). It
answers in a strict schema whose `rule_id` can only be one of its rules. Every item becomes a *warning*
through `new_finding` (ADR 0008: an LLM never fails a rule), citing dimensions, notes or title-block fields
by id. The verifier then drops any citation that doesn't resolve or misquotes the drawing.

A rule the model raises nothing on is `not_checked`, not `pass` (2026-10-25): silence from a reviewer measured
at 32-61% precision (Spike E) is not evidence that the rule holds.
"""

from __future__ import annotations

import json
import logging
import time
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from drawing_intelligence.llm import LLMClient, TextPart
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reviewers import reviewer_for
from drawing_intelligence.review.rulebook import Rule, new_finding
from drawing_intelligence.schemas import EvidenceRef, Finding, ReviewerOutput, RuleStatus

log = logging.getLogger(__name__)
PROMPT = resources.files(__package__).joinpath("prompts/reviewer.md").read_text(encoding="utf-8")
SILENT = "LLM judged: no issue raised (not proof of a pass)"

# What a rule may need beyond the drawing's text (its `params.needs`), and what stage 1 provides so far.
# Symbols come with Spike D's stage-1 work; feature locations with view and feature geometry. Without them the
# reviewer can only guess (calibration 2026-10-25: "no roughness specified" on drawings whose finish marks it
# cannot see), so such rules are not_checked until their input exists.
AVAILABLE_INPUTS: frozenset[str] = frozenset({"symbols"})  # symbols: stage 1 reads them (Spike D)

# What the model sees of each page: the drawing's content, without bookkeeping it cannot use. The vision
# model's symbols are left out (it misses most of them, Spike D); a reviewer whose rules need symbols
# gets stage 1's exact ones instead (`needs_symbols`).
_KNOWLEDGE_VIEW: dict[str, Any] = {
    "dimensions": {"__all__": {"bbox", "source"}},
    "symbols": True,
    "uncertain": True,
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(_Strict):
    kind: Literal["dimension", "note", "title_block"]
    ref: str  # D7, N2, or a title-block field name (material)
    page: int
    quote: str  # the text exactly as it appears in DRAWING


class SymbolCitation(_Strict):
    """A citation that may also point at a symbol (S1): for reviewers that are given the symbols."""

    kind: Literal["dimension", "note", "title_block", "symbol"]
    ref: str  # D7, N2, S3, or a title-block field name (material)
    page: int
    quote: str  # the text exactly as it appears in DRAWING


def needs_symbols(rules: list[Rule]) -> bool:
    return any("symbols" in r.params.get("needs", []) for r in rules)


def output_schema(rule_ids: list[str], symbols: bool = False) -> type[BaseModel]:
    """The reviewer's answer schema: findings whose rule id can only be one of this reviewer's rules."""
    rule_id = Literal.__getitem__(tuple(rule_ids))  # type: ignore[attr-defined]
    citation = SymbolCitation if symbols else Citation
    item = create_model(
        "ReviewItem",
        __config__=ConfigDict(extra="forbid"),
        rule_id=(rule_id, ...),
        evidence=(list[citation], ...),
        comment=(str, ...),
        recommended_correction=(str, ...),
    )
    return create_model("Review", __config__=ConfigDict(extra="forbid"), findings=(list[item], ...))


def build_message(ctx: ReviewContext, rules: list[Rule]) -> str:
    # A rule's `llm_instruction` narrows what may be reported under it (MF-007: only a stated conflict).
    rules_json = [
        {"id": r.id, "requirement": r.requirement}
        | ({"only_when": r.params["llm_instruction"]} if r.params.get("llm_instruction") else {})
        for r in rules
    ]
    pages = []
    for p in ctx.pages:
        k = ctx.knowledge_of(p)
        if k is None:
            continue
        page = {"page": p.page_number, **k.model_dump(mode="json", exclude=_KNOWLEDGE_VIEW)}
        # the template's own printed notes are on every sheet; they are not the designer's notes
        page["notes"] = [n for n in page["notes"] if not ctx.template.is_boilerplate(n["text"])]
        if needs_symbols(rules):  # stage 1's exact symbols; an empty list means none is drawn on the page
            page["symbols"] = [{"id": s.id, "type": s.type, "text": s.text} for s in p.symbols]
        pages.append(page)
    return (
        PROMPT
        + "\n\nRULES:\n"
        + json.dumps(rules_json, ensure_ascii=False)
        + "\n\nDRAWING:\n"
        + json.dumps(pages, ensure_ascii=False)
    )


def _evidence(ctx: ReviewContext, c: Citation | SymbolCitation) -> EvidenceRef:
    """A citation as evidence, with the bbox and provenance stage 1 knows (the verifier checks the rest)."""
    page = next((p for p in ctx.pages if p.page_number == c.page), None)
    bbox = None
    provenance: Literal["pdf_text", "vector", "vision"] = "pdf_text"
    if page is not None and c.kind == "dimension":
        dim = next((d for d in page.dimensions if d.id == c.ref), None)
        bbox = list(dim.bbox) if dim else None
        provenance = "vision" if c.ref.startswith("V") else "pdf_text"
    elif page is not None and c.kind == "title_block" and (f := page.title_block_fields.get(c.ref)):
        bbox = list(f.bbox)
    elif (
        page is not None
        and c.kind == "symbol"
        and (sym := next((s for s in page.symbols if s.id == c.ref), None))
    ):
        bbox, provenance = list(sym.bbox), sym.provenance
    return EvidenceRef(kind=c.kind, ref=c.ref, page=c.page, bbox=bbox, quote=c.quote, provenance=provenance)


def run_llm_reviewer(
    ctx: ReviewContext, name: str, client: LLMClient, model: str | None = None, thinking: str | None = None
) -> ReviewerOutput:
    """One reviewer's call, findings and rule statuses."""
    mine = [r for r in ctx.rulebook.rules if r.check_type == "llm" and reviewer_for(r) == name]
    rules = [r for r in mine if r.applies(ctx.part_family, ctx.drawing_type)]
    statuses = [
        RuleStatus(rule_id=r.id, status="not_applicable", note="outside the rule's applies_to")
        for r in mine
        if r not in rules
    ]
    blocked = [r for r in rules if set(r.params.get("needs", [])) - AVAILABLE_INPUTS]
    for r in blocked:
        missing = ", ".join(sorted(set(r.params["needs"]) - AVAILABLE_INPUTS))
        statuses.append(
            RuleStatus(
                rule_id=r.id,
                status="not_checked",
                note=f"needs {missing}, which the review does not have yet",
            )
        )
    rules = [r for r in rules if r not in blocked]
    if not rules:
        return ReviewerOutput(reviewer=name, rule_statuses=statuses)
    if not any(ctx.knowledge_of(p) for p in ctx.pages):
        note = "no understanding of the drawing to review"
        statuses += [RuleStatus(rule_id=r.id, status="not_checked", note=note) for r in rules]
        return ReviewerOutput(reviewer=name, rule_statuses=statuses)

    start = time.perf_counter()
    schema = output_schema([r.id for r in rules], symbols=needs_symbols(rules))
    resp = client.complete(
        [TextPart(build_message(ctx, rules))],
        role="review",
        node=f"review:{name}",
        model=model,
        thinking=thinking,
        schema=schema,
    )
    by_id = {r.id: r for r in rules}
    findings: list[Finding] = []
    dropped = 0
    try:
        items = json.loads(resp.text or "{}").get("findings", [])
    except json.JSONDecodeError:
        items = []
        log.warning("reviewer %s returned invalid JSON", name)
    for raw in items:
        try:
            item = schema.model_validate({"findings": [raw]}).findings[0]  # type: ignore[attr-defined]
            evidence = [_evidence(ctx, c) for c in item.evidence]
            findings.append(
                new_finding(
                    by_id[item.rule_id],
                    reviewer=name,
                    evidence=evidence,
                    comment=item.comment,
                    recommended_correction=item.recommended_correction,
                )
            )
        except (ValidationError, ValueError, KeyError):
            dropped += 1  # no evidence, an unknown rule: nothing a verifier could check
    if dropped:
        log.warning("reviewer %s: %d item(s) without usable evidence dropped", name, dropped)
    findings = list({f.id: f for f in findings}.values())
    for r in rules:
        ids = [f.id for f in findings if f.rule_id == r.id]
        statuses.append(
            RuleStatus(rule_id=r.id, status="warning", finding_ids=ids)
            if ids
            else RuleStatus(rule_id=r.id, status="not_checked", note=SILENT)
        )
    return ReviewerOutput(
        reviewer=name,
        findings=findings,
        rule_statuses=statuses,
        cost_usd=0.0 if resp.cached else resp.cost_usd,
        latency_s=resp.latency_s if not resp.cached else round(time.perf_counter() - start, 3),
    )
