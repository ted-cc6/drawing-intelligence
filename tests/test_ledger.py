"""The web demo's in-memory ledger (api/ledger.py): run history across visitors and feedback analytics."""

from typing import Any

from drawing_intelligence.api.ledger import UPLOAD_LABEL, Ledger


def _run(ledger: Ledger, **overrides: Any) -> None:
    row: dict[str, Any] = {
        "session_id": "s1",
        "visitor": "v-a",
        "drawing": "P13",
        "mode": "Demo (cached)",
        "status": "done",
        "findings": 4,
        "fails": 3,
        "seconds": 2.9,
        "cost_usd": 0.0,
        "model": "qwen3-vl-plus",
        "cached": True,
    }
    ledger.record_run(**(row | overrides))


def _fb(ledger: Ledger, **overrides: Any) -> None:
    row: dict[str, Any] = {
        "session_id": "s1",
        "visitor": "v-a",
        "finding_id": "f1",
        "rule_id": "RQ-002",
        "requirement": "Tolerance limits are valid",
        "category": "tolerance",
        "source": "code",
        "reviewer": "checks",
        "result": "fail",
        "decision": "accept",
    }
    ledger.record_feedback(**(row | overrides))


def test_runs_newest_first_with_visitor_labels():
    ledger = Ledger()
    _run(ledger, session_id="s1", visitor="v-a")
    _run(ledger, session_id="s2", visitor="v-b", drawing="C01")
    _run(ledger, session_id="s3", visitor="v-a")
    h = ledger.history("v-b")
    # session ids are the only key to another visitor's open session: never handed out
    assert all("session_id" not in r for r in h["runs"])
    assert [r["no"] for r in h["runs"]] == [3, 2, 1]
    assert [r["visitor"] for r in h["runs"]] == ["Visitor 1", "Visitor 2", "Visitor 1"]
    assert [r["you"] for r in h["runs"]] == [False, True, False]
    assert h["visitors"] == 2 and h["since"] == ledger.since


def test_visitors_are_numbered_when_first_seen_not_when_their_review_ends():
    ledger = Ledger()
    ledger.visit("v-slow")  # opened an upload first; its review ends later
    _run(ledger, session_id="s1", visitor="v-fast")
    _run(ledger, session_id="s2", visitor="v-slow")
    assert [r["visitor"] for r in ledger.history(None)["runs"]] == ["Visitor 1", "Visitor 2"]


def test_a_request_without_a_visitor():
    ledger = Ledger()
    _run(ledger, visitor=None)
    (row,) = ledger.history(None)["runs"]
    assert row["visitor"] == "Visitor ?" and row["you"] is False


def test_qa_cost_lands_on_its_run():
    ledger = Ledger()
    _run(ledger)
    ledger.add_qa_cost("s1", 0.004)
    ledger.add_qa_cost("s1", 0.004)
    ledger.add_qa_cost("nope", 1.0)
    (row,) = ledger.history("v-a")["runs"]
    assert row["qa_cost_usd"] == 0.008


def test_model_summary_averages_live_done_runs_only():
    ledger = Ledger()
    _run(ledger, session_id="s1")
    _run(ledger, session_id="s2", mode="Live upload", cached=False, seconds=60.0, cost_usd=0.03)
    _run(ledger, session_id="s3", mode="Live upload", cached=False, status="error", seconds=5.0, cost_usd=0.0)
    _run(ledger, session_id="s4", model="other-model")
    models = {m["model"]: m for m in ledger.history(None)["models"]}
    q = models["qwen3-vl-plus"]
    assert (q["runs"], q["live_runs"]) == (3, 2)
    assert q["avg_live_seconds"] == 60.0 and q["avg_live_cost_usd"] == 0.03 and q["total_cost_usd"] == 0.03
    assert models["other-model"]["avg_live_seconds"] is None


def test_a_changed_decision_counts_once():
    ledger = Ledger()
    _fb(ledger, decision="accept")
    _fb(ledger, decision="reject")
    s = ledger.feedback_summary()
    assert (s["decisions"], s["accepted"], s["rejected"]) == (1, 0, 1)


def test_feedback_summary_groups_and_sorts():
    ledger = Ledger()
    _fb(ledger, finding_id="a1", rule_id="A", decision="reject")
    _fb(ledger, finding_id="a2", rule_id="A", decision="reject")
    _fb(ledger, finding_id="b1", rule_id="B", decision="reject", source="llm", reviewer="design_intent")
    _fb(ledger, finding_id="b2", rule_id="B", decision="accept", source="llm", reviewer="design_intent")
    _fb(ledger, finding_id="b3", rule_id="B", decision="accept", source="llm", reviewer="design_intent")
    _fb(ledger, finding_id="c1", rule_id="C", decision="accept")
    s = ledger.feedback_summary()
    assert [r["rule_id"] for r in s["by_rule"]] == ["A", "B", "C"]
    b = s["by_rule"][1]
    assert (b["decisions"], b["accepted"], b["rejected"], b["rate"]) == (3, 2, 1, 0.667)
    assert sum(x["decisions"] for x in s["by_source"]) == s["decisions"] == 6
    assert sum(x["decisions"] for x in s["by_reviewer"]) == 6
    assert s["since"] == ledger.since


def test_a_finding_without_a_rule():
    ledger = Ledger()
    _fb(ledger, rule_id=None, requirement="Ø16 looks odd", source="llm")
    s = ledger.feedback_summary()
    assert s["decisions"] == 1 and s["by_rule"] == []
    assert any(x["source"] == "llm" for x in s["by_source"])
    assert "Ø16 looks odd" not in repr(ledger.__dict__)


def test_upload_rows_carry_no_file_name():
    ledger = Ledger()
    _run(ledger, drawing=UPLOAD_LABEL, mode="Live upload", cached=False)
    (row,) = ledger.history(None)["runs"]
    assert UPLOAD_LABEL == "Uploaded PDF" and row["drawing"] == "Uploaded PDF"
