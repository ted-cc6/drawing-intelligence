"""Shared setup for Spike E (LLM judgement). Routes every write into out/ - never into data/.

The package's LLMClient takes an explicit Telemetry and ResponseCache, so here they point at out/
(git-ignored): no session is opened, data/telemetry.db and data/cache/ are never touched. Import this from
the other spike scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from drawing_intelligence.llm import LLMClient, load_registry
from drawing_intelligence.settings import get_settings
from drawing_intelligence.storage import ResponseCache, Telemetry

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CASES = HERE / "cases"
RESULTS = HERE / "results"
BASES = OUT / "bases"  # generated/copied DrawingKnowledge JSONs + their images

REVIEWER_MODEL = "qwen3.8-max"
SESSION_ID = "spike_e"


def build_client() -> LLMClient:
    """An LLMClient whose telemetry and cache live in out/, so no run writes into data/."""
    settings = get_settings()
    telemetry = Telemetry(OUT / "telemetry.db")
    cache = ResponseCache(OUT / "cache")
    return LLMClient(load_registry(), settings, telemetry, cache, SESSION_ID)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        obj.model_dump_json(indent=1)
        if isinstance(obj, BaseModel)
        else json.dumps(obj, indent=1, ensure_ascii=False)
    )
    path.write_text(text, encoding="utf-8")
