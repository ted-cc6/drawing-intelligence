"""Symbols read by stage 1 against the reviewed answer key (Spike D: 10 drawings, 13 pages, 80 symbols)."""

from __future__ import annotations

import json
import math

import pytest

from drawing_intelligence.extraction import extract_pdf
from drawing_intelligence.settings import PROJECT_ROOT, get_settings

pytestmark = pytest.mark.regression

KEY = get_settings().labels_dir / "symbol_answer_key.json"
DRAWINGS = json.loads(KEY.read_text(encoding="utf-8"))["drawings"] if KEY.exists() else {}


def _centre(b) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_every_symbol_found_and_nothing_else(name):
    entry = DRAWINGS[name]
    pdf = PROJECT_ROOT / entry["pdf"]
    if not pdf.exists():
        pytest.skip(f"{pdf} not in this checkout")
    for page in extract_pdf(pdf).pages:
        truth = list(entry["pages"][str(page.page_number)])
        unmatched = []
        for s in page.symbols:
            hit = next(
                (
                    t
                    for t in truth
                    if t["type"] == s.type and math.dist(_centre(t["bbox"]), _centre(s.bbox)) < 30
                ),
                None,
            )
            if hit is None:
                unmatched.append(s.text)
            else:
                truth.remove(hit)
                if s.type == "gdt":
                    assert hit["value"].split()[0] == s.characteristic
        assert unmatched == [], f"page {page.page_number}: not in the key"
        assert truth == [], f"page {page.page_number}: missed"
