"""Stability scoring across repeated di eval understand runs (A1, criterion 6).

A result is "stable" for a drawing+model+thinking setting if every repeated run
produced the same title block and the same dimension count. This module only
compares already-produced run outputs; it does not call any model itself.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _title_block_signature(drawing_json: dict[str, Any]) -> tuple:
    """A hashable signature of the title-block fields, order-independent."""
    tb = drawing_json.get("title_block", {}) or {}
    return tuple(sorted((str(k), str(v)) for k, v in tb.items()))


def _dimension_count(drawing_json: dict[str, Any]) -> int:
    return len(drawing_json.get("dimensions", []) or [])


def score_stability(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Score stability across repeated runs of the same drawing/model/thinking setting.

    Parameters
    ----------
    runs: list of parsed DrawingKnowledge-shaped dicts, one per run (same drawing,
        same model, same thinking setting, ideally with the cache bypassed).

    Returns
    -------
    dict with:
        n_runs: number of runs compared
        title_block_stable: True if every run had the same title block
        dimension_count_stable: True if every run had the same dimension count
        title_block_variants: how many distinct title-block signatures were seen
        dimension_counts: the distinct counts seen, with how often each occurred
    """
    if not runs:
        raise ValueError("score_stability requires at least one run")

    tb_sigs = Counter(_title_block_signature(r) for r in runs)
    dim_counts = Counter(_dimension_count(r) for r in runs)

    return {
        "n_runs": len(runs),
        "title_block_stable": len(tb_sigs) == 1,
        "dimension_count_stable": len(dim_counts) == 1,
        "title_block_variants": len(tb_sigs),
        "dimension_counts": dict(dim_counts),
    }
