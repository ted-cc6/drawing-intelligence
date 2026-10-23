"""The review on the committed planted-error drawings: a gate against regressions (runs in CI, $0).

Code checks only (`understand=False`): no API key and no model call, and none of the built checks needs the
understanding step yet. Raise the floor by hand whenever a new check catches more.
"""

from __future__ import annotations

import pytest

from drawing_intelligence.eval.review_eval import run_review_eval, summarize
from drawing_intelligence.settings import get_settings

pytestmark = pytest.mark.regression

SEEDED = get_settings().data_path / "eval" / "seeded"
RECALL_FLOOR = 10  # planted errors caught on 2026-10-23: P01-P04, P07-P12


@pytest.mark.skipif(not SEEDED.is_dir(), reason="no seeded cases in data/eval/seeded")
def test_review_catches_planted_errors_without_false_alarms():
    scores = run_review_eval(get_settings(), SEEDED, understand=False)
    s = summarize(scores)
    alarms = [f"{case}: {f.rule_id} {f.comment}" for case, f in s.false_alarms_on_quiet]
    assert alarms == [], "false alarms on clean or near-miss drawings"
    assert s.caught >= RECALL_FLOOR
    assert s.caught_covered == s.covered, "a built check missed the planted error it covers"
    assert s.correct == s.findings, "a finding on a planted case is neither the error nor in its key"
