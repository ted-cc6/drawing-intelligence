"""Diff a new extraction against the original notebook's saved `extraction.json` (ADR 0005).

Differences are reported for a human to explain, not treated as failures.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from drawing_intelligence.schemas import PageExtraction

ITEM_SECTIONS = ("dimensions", "view_labels", "notes", "other_numeric")
LINE_SECTIONS = ("title_block_text", "tolerance_table_text", "body_text")


@dataclass
class SectionDiff:
    section: str
    n_baseline: int
    n_new: int
    only_baseline: list[str] = field(default_factory=list)
    only_new: list[str] = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return not self.only_baseline and not self.only_new


def _key(item: dict[str, Any], with_ref: bool) -> str:
    bbox = ", ".join(f"{float(v):.1f}" for v in item["bbox"])
    ref = " (ref)" if with_ref and item.get("is_reference") else ""
    return f"{item['text']}{ref} @ [{bbox}]"


def _diff(section: str, old: list[str], new: list[str]) -> SectionDiff:
    a, b = Counter(old), Counter(new)
    return SectionDiff(section, len(old), len(new), sorted((a - b).elements()), sorted((b - a).elements()))


def diff_page(baseline: dict[str, Any], page: PageExtraction) -> list[SectionDiff]:
    new = page.model_dump(mode="json")
    out = [
        _diff(s, [_key(i, True) for i in baseline.get(s, [])], [_key(i, True) for i in new[s]])
        for s in ITEM_SECTIONS
    ]
    out += [
        _diff(s, [_key(i, False) for i in baseline.get(s, [])], [_key(i, False) for i in new[s]])
        for s in LINE_SECTIONS
    ]
    out.append(
        _diff(
            "chain_checks",
            [_chain(c) for c in baseline.get("chain_checks", [])],
            [_chain(c) for c in new["chain_checks"]],
        )
    )
    return out


def _chain(c: dict[str, Any]) -> str:
    return f"{' + '.join(c['chain_texts'])} = {c['chain_sum']} vs {c['overall_text']} ({c['match']})"


def load_baseline(baseline_dir: Path, drawing: str) -> dict[str, Any] | None:
    path = baseline_dir / "extraction" / drawing / "extraction.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
