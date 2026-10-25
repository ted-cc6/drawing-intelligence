"""Stage 2: one vision-LLM call per page turns the images + exact text into a `DrawingKnowledge`.

The model organises and interprets the exact text and adds only what text cannot see (symbols); it must not
re-read numbers from pixels. A reply that fails schema validation is retried once with the error.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from drawing_intelligence.llm import ImagePart, LLMClient, LLMResponse, Part, TextPart
from drawing_intelligence.schemas import DrawingKnowledge, PageExtraction, UnderstandingResult

NODE = "understand"
PROMPT = resources.files(__package__).joinpath("prompts/understand.md").read_text(encoding="utf-8")

# Sent to the model as the extracted text: everything except image bookkeeping and line geometry, and the
# fields stage 1 derives by code (title-block fields, tolerance table rows, ordered limits, chain ids). Their
# raw text is in the prompt already; leaving them out keeps the prompt that ADR 0009 chose the model on.
_PER_ITEM = {"__all__": {"limits"}}
_EXCLUDE_FROM_TEXT: dict[str, Any] = {
    "images": True,
    "matched_lines": True,
    "title_block_layout": True,
    "title_block_fields": True,
    "revision_rows": True,
    "revision_numbers": True,
    "general_tolerances": True,
    "symbols": True,
    "dimensions": _PER_ITEM,
    "view_labels": _PER_ITEM,
    "notes": _PER_ITEM,
    "other_numeric": _PER_ITEM,
    "chain_checks": {"__all__": {"chain_ids", "overall_id"}},
}


def image_caption(page: PageExtraction, file: str) -> str:
    imgs = page.images
    assert imgs is not None
    name = Path(file).name
    if file == imgs.full:
        w, h = page.page_size_pts
        return f"Image {name}: the whole sheet ({w:.0f} x {h:.0f} pt), downscaled."
    if file == imgs.title_block:
        return f"Image {name}: close-up of the title block (bottom-right corner of the sheet)."
    tile = next(t for t in imgs.tiles if t.file == file)
    x0, y0, x1, y1 = (round(v * 72 / imgs.dpi) for v in tile.pixel_box)
    return f"Image {name}: zoomed tile covering PDF points x {x0}-{x1}, y {y0}-{y1}."


def build_parts(page: PageExtraction, root: Path, extra: str = "") -> list[Part]:
    """The message: instructions, then each image with its caption, then the exact text as JSON."""
    if page.images is None:
        raise ValueError(f"page {page.page_number} has no images; run extraction with an output folder")
    imgs = page.images
    files = [imgs.full, *(t.file for t in imgs.tiles), *([imgs.title_block] if imgs.title_block else [])]
    parts: list[Part] = [TextPart(PROMPT + extra)]
    for f in files:
        parts += [TextPart(image_caption(page, f)), ImagePart(Path(f).name, (root / f).read_bytes())]
    text = page.model_dump(mode="json", exclude=_EXCLUDE_FROM_TEXT)
    parts.append(TextPart("EXTRACTED TEXT (JSON):\n" + json.dumps(text, ensure_ascii=False)))
    return parts


def parse(text: str) -> DrawingKnowledge:
    return DrawingKnowledge.model_validate_json(re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text or ""))


def check_against_extraction(k: DrawingKnowledge, page: PageExtraction) -> list[str]:
    """Contract checks the schema cannot express: every extracted dimension returned unchanged."""
    problems = []
    out = {d.id: d for d in k.dimensions}
    for d in page.dimensions:
        got = out.get(d.id or "")
        if got is None:
            problems.append(f"{d.id} ({d.text}) missing")
        elif got.text != d.text:
            problems.append(f"{d.id} text changed: {d.text!r} -> {got.text!r}")
        elif got.source != "pdf_text":
            problems.append(f"{d.id} source should be pdf_text")
    known = {d.id for d in page.dimensions}
    problems += [
        f"{d.id} marked pdf_text but is not an extracted dimension"
        for d in k.dimensions
        if d.source == "pdf_text" and d.id not in known
    ]
    return problems


def understand_page(
    client: LLMClient,
    page: PageExtraction,
    root: Path,
    model: str | None = None,
    thinking: str | None = None,
) -> UnderstandingResult:
    calls: list[LLMResponse] = []
    knowledge, error = None, ""
    for attempt in (1, 2):
        extra = (
            ""
            if attempt == 1
            else f"\n\nIMPORTANT: a previous reply was not valid ({error}). Reply with ONE valid JSON object "
            "that follows the schema exactly."
        )
        resp = client.complete(
            build_parts(page, root, extra),
            role="understand",
            node=NODE,
            model=model,
            thinking=thinking,
            schema=DrawingKnowledge,
        )
        calls.append(resp)
        try:
            knowledge = parse(resp.text)
            break
        except (ValidationError, ValueError) as e:
            error = str(e)[:1500]
    problems = check_against_extraction(knowledge, page) if knowledge else [f"invalid reply: {error[:300]}"]
    return UnderstandingResult(
        page_number=page.page_number,
        model=calls[0].model,
        thinking=calls[0].thinking,
        knowledge=knowledge,
        valid=knowledge is not None,
        attempts=len(calls),
        problems=problems,
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        cost_usd=round(sum(c.cost_usd for c in calls), 6),
        latency_s=round(sum(c.latency_s for c in calls), 2),
        cached=all(c.cached for c in calls),
    )
