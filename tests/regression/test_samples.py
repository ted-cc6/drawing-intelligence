"""Real sample drawings vs the original notebook's outputs. Local only: needs client data in data/."""

from __future__ import annotations

from pathlib import Path

import pytest

from drawing_intelligence.eval.baseline import diff_page, load_baseline
from drawing_intelligence.extraction import extract_pdf
from drawing_intelligence.settings import get_settings

pytestmark = pytest.mark.regression

_S = get_settings()
SAMPLES = sorted(_S.raw_dir.glob("*.pdf")) if _S.raw_dir.exists() else []
WITH_BASELINE = [p for p in SAMPLES if load_baseline(_S.baseline_dir, p.stem)]


@pytest.mark.skipif(not WITH_BASELINE, reason="no sample drawings with a baseline in data/")
@pytest.mark.parametrize("pdf", WITH_BASELINE, ids=lambda p: p.stem)
def test_extraction_matches_notebook_baseline(pdf: Path):
    baseline = load_baseline(_S.baseline_dir, pdf.stem)
    assert baseline is not None
    diffs = diff_page(baseline, extract_pdf(pdf).pages[0])
    changed = {d.section: (d.only_baseline, d.only_new) for d in diffs if not d.identical}
    assert not changed, f"differs from the notebook baseline: {changed}"
