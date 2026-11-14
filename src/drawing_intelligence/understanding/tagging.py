"""Stage 2, second call: label the dimensions the split checks need (2026-11-13).

The code checks for fits on internal or external features (WST-206), keyways (MC-007), retaining-ring grooves
(MC-008) and thread undercuts (WST-242) compare dimensions with standard tables, but stage 1 cannot tell which
dimension is a keyway's width or an undercut's diameter, and the understanding links few dimensions to
features. One call per page shows the vision model the page's images (the same ones the understanding gets)
and its dimensions, and asks which play those roles; the checks do the arithmetic. Text alone is not enough:
a keyway's "6" is only a keyway on the section view. A tag that names a dimension the page does not have, or
misquotes it, is dropped.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from drawing_intelligence.llm import ImagePart, LLMClient, Part, TextPart
from drawing_intelligence.schemas import DimensionTag, DrawingKnowledge, PageExtraction, TagResult
from drawing_intelligence.understanding.understand import image_caption

NODE = "understand:tag"
PROMPT = resources.files(__package__).joinpath("prompts/tag.md").read_text(encoding="utf-8")

# What the tagger sees: the dimensions, features, views and notes, without positions and bookkeeping.
_VIEW: dict[str, Any] = {
    "dimensions": {"__all__": {"bbox", "source", "is_reference"}},
    "symbols": True,
    "uncertain": True,
    "general_tolerances": True,
    "revisions": True,
}


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[DimensionTag]


def build_parts(page: PageExtraction, root: Path, knowledge: DrawingKnowledge) -> list[Part]:
    """Instructions, the page's images with their captions, then the dimensions as JSON."""
    parts: list[Part] = [TextPart(PROMPT)]
    if page.images is not None:
        imgs = page.images
        for f in [imgs.full, *(t.file for t in imgs.tiles)]:
            parts += [TextPart(image_caption(page, f)), ImagePart(Path(f).name, (root / f).read_bytes())]
    drawing = json.dumps(knowledge.model_dump(mode="json", exclude=_VIEW), ensure_ascii=False)
    return [*parts, TextPart("DRAWING:\n" + drawing)]


def _norm(text: str) -> str:
    return "".join(text.split())


def tag_page(
    client: LLMClient,
    page: PageExtraction,
    root: Path,
    knowledge: DrawingKnowledge,
    model: str | None = None,
    thinking: str | None = None,
) -> TagResult:
    resp = client.complete(
        build_parts(page, root, knowledge),
        role="understand",
        node=NODE,
        model=model,
        thinking=thinking,
        schema=_Answer,
    )
    texts = {d.id: d.text for d in knowledge.dimensions}
    tags: list[DimensionTag] = []
    dropped, valid = 0, True
    try:
        raw = json.loads(resp.text or "{}").get("tags", [])
    except json.JSONDecodeError:
        raw, valid = [], False
    for item in raw:
        try:
            tag = DimensionTag.model_validate(item)
        except ValidationError:
            dropped += 1
            continue
        if tag.dimension_id not in texts or _norm(tag.quote) != _norm(texts[tag.dimension_id]):
            dropped += 1  # a dimension the page does not have, or a misquote
            continue
        tags.append(tag)
    return TagResult(
        model=resp.model,
        thinking=resp.thinking,
        tags=tags,
        dropped=dropped,
        valid=valid,
        cost_usd=resp.cost_usd,
        latency_s=resp.latency_s,
        cached=resp.cached,
    )
