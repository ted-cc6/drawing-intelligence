"""The understanding scorecard, ported from notebook 02 (criteria 1, 2, 3, 4 and 7).

Works on plain dicts so it can score both new results and the notebook's saved outputs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from drawing_intelligence.schemas import DrawingKnowledge, PageExtraction

TITLE_FIELDS = list(DrawingKnowledge.model_fields["drawing"].annotation.model_fields)  # type: ignore[union-attr]
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Keys whose values are positions, ids or bookkeeping, not drawing values.
_SKIP = {"id", "bbox", "view_id", "feature_id", "dimension_ids", "tile", "source", "is_reference"}
_SKIP_PDF = {
    "bbox",
    "images",
    "pixel_box",
    "matched_lines",
    "page_size_pts",
    "scale_pts_per_mm",
    "page_number",
}


@dataclass
class Targets:
    title_block: float = 0.90
    dims_complete: float = 0.95
    max_seconds: float = 60.0
    max_cost_usd: float = 0.10


@dataclass
class Score:
    drawing: str
    source: str
    valid: bool
    title_block: float | None  # None = no labels for this drawing
    dims_found: int
    dims_total: int
    invented: list[tuple[str, str]] = field(default_factory=list)
    symbols: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0
    title_block_misses: list[tuple[str, Any, Any]] = field(default_factory=list)

    @property
    def dims_ratio(self) -> float:
        return self.dims_found / max(1, self.dims_total)

    def passed(self, t: Targets) -> dict[str, bool | None]:
        return {
            "1 valid": self.valid,
            "2 title block": None if self.title_block is None else self.title_block >= t.title_block,
            "3 dims complete": self.dims_ratio >= t.dims_complete,
            "4 invented": not self.invented,
            "7 time": self.seconds < t.max_seconds,
            "7 cost": self.cost_usd <= t.max_cost_usd,
        }


def _norm(v: Any) -> str:
    return re.sub(r"[^0-9a-z]", "", str(v).lower()) if v is not None else ""


def _to_num(s: str) -> float:
    return float(s.replace(",", "."))


def pdf_numbers(page: dict[str, Any]) -> set[float]:
    """Every number in the PDF text layer of the page."""
    nums: set[float] = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k not in _SKIP_PDF:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            nums.update(_to_num(m) for m in NUM_RE.findall(x))
        elif isinstance(x, int | float) and not isinstance(x, bool):
            nums.add(float(x))

    walk(page)
    return nums


def invented_numbers(knowledge: dict[str, Any], page: dict[str, Any]) -> list[tuple[str, str]]:
    """Numbers in the output not found in the PDF text (ignoring `source: vision` items, ids, positions)."""
    known, found = pdf_numbers(page), []

    def walk(x: Any, where: str) -> None:
        if isinstance(x, dict):
            if x.get("source") == "vision":
                return
            for k, v in x.items():
                if k not in _SKIP:
                    walk(v, f"{where}.{k}")
        elif isinstance(x, list):
            for v in x:
                walk(v, where)
        elif isinstance(x, str):
            found.extend((where, m) for m in NUM_RE.findall(x) if _to_num(m) not in known)
        elif isinstance(x, int | float) and not isinstance(x, bool) and float(x) not in known:
            found.append((where, str(x)))

    for sec in ("drawing", "views", "dimensions", "features", "notes", "general_tolerances", "revisions"):
        walk(knowledge.get(sec), sec)
    return found


def score(
    drawing: str,
    source: str,
    knowledge: dict[str, Any] | None,
    page: PageExtraction,
    *,
    seconds: float,
    cost_usd: float,
    truth: dict[str, Any] | None,
) -> Score:
    want = [d.text for d in page.dimensions]
    if knowledge is None:
        return Score(drawing, source, False, None, 0, len(want), seconds=seconds, cost_usd=cost_usd)
    try:
        DrawingKnowledge.model_validate(knowledge)
        valid = True
    except ValidationError:
        valid = False
    tb, misses = None, []
    if truth:
        got = knowledge.get("drawing") or {}
        misses = [
            (f, truth.get(f), got.get(f)) for f in TITLE_FIELDS if _norm(got.get(f)) != _norm(truth.get(f))
        ]
        tb = 1 - len(misses) / len(TITLE_FIELDS)
    out = [
        d.get("text")
        for d in knowledge.get("dimensions", [])
        if isinstance(d, dict) and d.get("source") != "vision"
    ]
    hit = 0
    for t in want:
        if t in out:
            out.remove(t)
            hit += 1
    return Score(
        drawing=drawing,
        source=source,
        valid=valid,
        title_block=tb,
        dims_found=hit,
        dims_total=len(want),
        invented=invented_numbers(knowledge, page.model_dump(mode="json")),
        symbols=len(knowledge.get("symbols") or []),
        seconds=seconds,
        cost_usd=cost_usd,
        title_block_misses=misses,
    )


def load_labels(labels_dir: Path) -> dict[str, Any]:
    path = labels_dir / "title_block_truth.json"
    if not path.exists():
        return {}
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
