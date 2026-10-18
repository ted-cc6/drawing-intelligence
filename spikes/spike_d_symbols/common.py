"""Shared setup for Spike D (symbol recognition). Every write goes into out/ - never into data/.

The LLMClient gets its own Telemetry and ResponseCache in out/ (git-ignored), so no session is opened and
data/telemetry.db and data/cache/ are never touched. Import this from the other spike scripts.
"""

from __future__ import annotations

from pathlib import Path

from drawing_intelligence.llm import LLMClient, load_registry
from drawing_intelligence.settings import get_settings
from drawing_intelligence.storage import ResponseCache, Telemetry

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "out"
RESULTS = HERE / "results"

MODEL = "qwen3-vl-plus"
SESSION_ID = "spike_d"

_PRISMATIC = REPO / "data" / "client_set" / "Generic Prismatic Parts"
_ROUND = REPO / "data" / "client_set" / "Generic Round Parts (Pins, Shafts)"

# The 10 drawings agreed for the spike: 4 samples (no GD&T: phantom controls), 3 prismatic, 3 round.
DRAWINGS: dict[str, Path] = {
    "10K_CAM PLATE": REPO / "data/raw/10K_CAM PLATE.pdf",
    "10K_CYLINDER ROD MTG_02": REPO / "data/raw/10K_CYLINDER ROD MTG_02.pdf",
    "20_INCH HOSE PIPE CLAMP_PU_01": REPO / "data/raw/20_INCH HOSE PIPE CLAMP_PU_01.pdf",
    "31K_PIPE CLAMP BLK_02": REPO / "data/raw/31K_PIPE CLAMP BLK_02.pdf",
    "P23Y5B096056002": _PRISMATIC / "P23Y5B096056002.PDF",
    "10K_DUNNAGE DOOR LM BLK MTG PLT_01": _PRISMATIC / "10K_DUNNAGE DOOR LM BLK MTG PLT_01.pdf",
    "P23Y5B076198001": _PRISMATIC / "P23Y5B076198001.PDF",
    "P23Y5B071019001": _ROUND / "P23Y5B071019001.PDF",
    "PRF83A106004002": _ROUND / "PRF83A106004002.pdf",
    "PRT84S103156003": _ROUND / "PRT84S103156003.PDF",
}

SYMBOL_TYPES = ("gdt", "datum", "surface_finish", "weld")


def build_client() -> LLMClient:
    """An LLMClient whose telemetry and cache live in out/, so no run writes into data/."""
    return LLMClient(
        load_registry(),
        get_settings(),
        Telemetry(OUT / "telemetry.db"),
        ResponseCache(OUT / "cache"),
        SESSION_ID,
    )
