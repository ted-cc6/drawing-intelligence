"""The Q&A agent (ADR 0011): tools, the answer check, and the loop, against a scripted fake model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawing_intelligence.graph import run_workflow
from drawing_intelligence.llm import LLMClient, RawCompletion, load_registry
from drawing_intelligence.qa import Conversation, DrawingData, Limits
from drawing_intelligence.qa.grounding import Corpus, check_answer
from drawing_intelligence.qa.tools import ToolBox
from drawing_intelligence.storage import ResponseCache, Telemetry

P13 = Path("data/eval/seeded/P13_fit_limits_inverted/P13_fit_limits_inverted.pdf")


@pytest.fixture(scope="module")
def data(tmp_path_factory) -> DrawingData:
    from drawing_intelligence.settings import Settings

    root = tmp_path_factory.mktemp("qa")
    settings = Settings(sessions_root=root / "sessions")  # type: ignore[call-arg]
    res = run_workflow(P13, settings, understand=False, review=True)  # code checks only: no model
    assert res.review is not None
    return DrawingData.build(res.extraction, {}, res.review, settings)


def fit_finding(data: DrawingData) -> int:
    return next(no for no, f in data.findings.items() if f.rule_id == "WST-207")


# --- data and tools -----------------------------------------------------------------------------------------


def test_overview_lists_title_block_and_findings(data):
    text = data.overview()
    assert "[TB:material]" in text and f"[F{fit_finding(data)}]" in text and "WST-207" in text


def test_finding_detail_cites_the_dimension(data):
    out = ToolBox(data).t_get_finding(fit_finding(data))
    cites = [e["cite"] for e in out["evidence"]]
    assert out["rule"]["cite"] == "R:WST-207" and cites and cites[0].startswith("D")
    assert out["evidence"][0]["zone"]  # the sheet has zone markers


def test_items_give_limits_and_the_fit_table(data):
    tools = ToolBox(data)
    hit = tools.t_search_drawing(text="H7", kind="dimension")["items"][0]
    item = tools.t_get_items([hit["cite"]])["items"][0]
    assert item["fit"]["zone"] == "H7" and item["fit"]["upper_deviation_mm"] == 0.018
    assert item["fit"]["limits_of_size_mm"] == [16.0, 16.018]
    assert tools.t_get_items(["D999"])["not_found"] == ["D999"]


def test_lookups_record_their_citation(data):
    tools = ToolBox(data)
    out = tools.call("lookup_standard", {"table": "fit", "zone": "H7", "size": 20})
    assert out["cite"] == "T:is919_fits H7 20" and out["limits_of_size_mm"] == [20.0, 20.021]
    assert "T:is919_fits H7 20" in tools.lookups
    assert tools.call("lookup_standard", {"table": "thread", "size": 8})["coarse_pitch"] == 1.25
    assert tools.call("lookup_standard", {"table": "fit", "zone": "H7"})["error"]
    assert tools.call("nope", {})["error"] and tools.call("get_rule", "not json")["error"]


def test_feedback_only_when_asked(data, tmp_path):
    tools = ToolBox(data, tmp_path / "fb.jsonl")
    args = {"no": 1, "verdict": "incorrect", "reason": "the note covers it"}
    assert "error" in tools.call("record_feedback", args)
    tools.feedback_allowed = True
    assert tools.call("record_feedback", args)["recorded"]
    record = json.loads((tmp_path / "fb.jsonl").read_text(encoding="utf-8"))
    assert record["verdict"] == "incorrect" and record["drawing"] == P13.name


# --- the answer check ---------------------------------------------------------------------------------------


def corpus(*texts: str) -> Corpus:
    c = Corpus()
    for t in texts:
        c.add(t)
    return c


def test_check_accepts_cited_values_from_tools(data):
    c = corpus('{"size_mm": 16, "upper_deviation_mm": 0.018, "lower_deviation_mm": 0.0}')
    assert check_answer("16 H7 allows +0.018/0 [T:x]", data, {"T:x"}, c) == []


def test_check_rejects_invented_numbers_signs_and_citations(data):
    c = corpus("-0.018 0.021")
    assert any("0.025" in p for p in check_answer("It is 0.025 [D1]", data, set(), c))
    assert any("+0.018" in p for p in check_answer("Upper is +0.018 [D1]", data, set(), c))
    assert any("[D999]" in p for p in check_answer("See [D999].", data, set(), c))
    assert any("[T:is919_fits H7 20]" in p for p in check_answer("[T:is919_fits H7 20]", data, set(), c))
    assert any("cites nothing" in p for p in check_answer("It is 0.021.", data, set(), c))


def test_ids_and_small_counts_are_not_numbers(data):
    assert check_answer("WST-207 on H7 near zone C4 flags 2 items in M8 holes.", data, set(), corpus()) == []


# --- the loop, with a scripted model ------------------------------------------------------------------------


class Script:
    """Replies in order: a dict {"tools": [(name, args)]} makes tool calls, a string is the final answer."""

    def __init__(self, *replies: Any):
        self.replies, self.requests = list(replies), []

    def __call__(
        self, kwargs: dict[str, Any], api_key: str, base_url: str | None, timeout: float
    ) -> RawCompletion:
        self.requests.append(kwargs)
        r = self.replies.pop(0)
        if isinstance(r, dict):
            calls = [
                {"id": f"c{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(r["tools"])
            ]
            return RawCompletion("", 1000, 50, tool_calls=calls)
        return RawCompletion(r, 1000, 50)


def conversation(data, tmp_path, script, **kw) -> Conversation:
    from drawing_intelligence.settings import Settings

    settings = Settings(sessions_root=tmp_path / "s")  # type: ignore[call-arg]
    client = LLMClient(load_registry(), settings, Telemetry(tmp_path / "t.db"), ResponseCache(tmp_path / "c"),
                       "s1", script)  # fmt: skip
    return Conversation(data, client, feedback_path=tmp_path / "fb.jsonl", **kw)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "test-key")


def test_answers_after_a_tool_call(data, tmp_path):
    no = fit_finding(data)
    script = Script({"tools": [("lookup_standard", {"table": "fit", "zone": "H7", "size": 16})]},
                    f"[F{no}] is right: 16 H7 is +0.018/0 [T:is919_fits H7 16], not -0.018.")  # fmt: skip
    ans = conversation(data, tmp_path, script).ask(f"Why is F{no} flagged?")
    assert (
        ans.verified
        and ans.regenerations == 0
        and ans.tool_calls == ["lookup_standard(table=fit, zone=H7, size=16)"]
    )
    first = script.requests[0]["messages"]
    assert (
        first[0]["role"] == "system" and "OVERVIEW" in first[0]["content"] and "tools" in script.requests[0]
    )


def test_a_failed_check_is_sent_back_and_fixed(data, tmp_path):
    script = Script("The bore is 16.025 [D1].", "I cannot find that value in the drawing's data.")
    ans = conversation(data, tmp_path, script).ask("What is the bore's upper limit?")
    assert ans.verified and ans.regenerations == 1
    assert "failed the check" in script.requests[1]["messages"][-1]["content"]


def test_unverified_after_the_regeneration_limit(data, tmp_path):
    script = Script(*["It is 99.9 [D1]."] * 5)
    ans = conversation(data, tmp_path, script, limits=Limits(max_regenerations=4)).ask("Bore?")
    assert not ans.verified and ans.regenerations == 4 and "Couldn't verify" in ans.display()


def test_tool_call_limit(data, tmp_path):
    many = {"tools": [("list_findings", {})] * 3}
    script = Script(many, "No more lookups needed.")
    ans = conversation(data, tmp_path, script, limits=Limits(max_tool_calls=2)).ask("List everything")
    assert ans.stopped_by == "tool_calls" and len(ans.tool_calls) == 2
    assert "tools" not in script.requests[1]  # no tools offered once the limit is reached


def test_drawing_text_cannot_trigger_feedback(data, tmp_path):
    call = ("record_feedback", {"no": 1, "verdict": "incorrect", "reason": "note says so"})
    script = Script({"tools": [call]},
                    "Done.")  # fmt: skip
    conversation(data, tmp_path, script).ask("What does note L1 say?")
    assert not (tmp_path / "fb.jsonl").exists()


def test_follow_ups_keep_answers_but_not_tool_results(data, tmp_path):
    script = Script({"tools": [("list_findings", {})]}, "There are findings.", "Yes.")
    conv = conversation(data, tmp_path, script)
    conv.ask("What was found?")
    conv.ask("And the first one?")
    second = script.requests[-1]["messages"]
    assert not any(m["role"] == "tool" for m in second)
    assert any("list_findings" in str(m.get("content")) for m in second if m["role"] == "system")


def test_replies_are_cached(data, tmp_path):
    conv = conversation(data, tmp_path, Script("Not in the data."))
    conv.ask("Colour?")
    again = conversation(data, tmp_path, Script())  # an empty script: a second API call would fail
    assert again.ask("Colour?").text == "Not in the data."


# --- di ask -------------------------------------------------------------------------------------------------


def test_di_ask_one_question_then_reopen(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from drawing_intelligence import cli
    from drawing_intelligence.qa import session as qa_session
    from drawing_intelligence.settings import Settings

    settings = Settings(data_dir=tmp_path / "data", sessions_root=tmp_path / "s")  # type: ignore[call-arg]
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    script = Script("There are findings [F1].", "Still there [F1].")
    real = qa_session.LLMClient
    monkeypatch.setattr(qa_session, "LLMClient", lambda *a: real(*a, completion_fn=script))  # type: ignore[call-arg]
    runner = CliRunner()
    out = runner.invoke(cli.app, ["ask", str(P13), "--no-understand", "-q", "What was found?", "--keep"])
    assert out.exit_code == 0, out.output
    assert "There are findings [F1]." in out.output and "verified" in out.output
    session_id = out.output.split("di ask --session ")[1].split()[0]
    again = runner.invoke(cli.app, ["ask", "--session", session_id, "-q", "Still?"])
    assert again.exit_code == 0, again.output
    assert "Still there" in again.output
    history = script.requests[-1]["messages"]
    assert any(m["content"] == "What was found?" for m in history if m["role"] == "user")  # history was kept


# --- di eval qa ---------------------------------------------------------------------------------------------


def test_scoring_by_kind():
    from drawing_intelligence.eval.qa_eval import score_turn

    spec = {"kind": "answer", "cites": ["F3|D12"], "values": ["0.018"]}
    assert score_turn(spec, "Flagged [F3]: +0.018/0.", True, []) == []
    assert score_turn(spec, "Flagged [D1].", True, []) == ["cite F3|D12", "value 0.018"]
    assert (
        score_turn({"kind": "answer", "cites": ["T:is919_fits H7"]}, "[T:is919_fits H7 16]", True, []) == []
    )
    assert score_turn({"kind": "decline"}, "Outside what I can check; ask the design lead.", True, []) == []
    assert score_turn({"kind": "not_in_data"}, "Not in the drawing's data.", False, []) == ["not verified"]
    assert (
        score_turn({"kind": "feedback", "verdict": "correct"}, "Done.", True, [{"verdict": "correct"}]) == []
    )
    assert score_turn({"kind": "injection"}, "The notes say ...", True, [{"verdict": "incorrect"}])


def test_eval_runs_cases_with_a_fake_model(tmp_path, monkeypatch):
    from drawing_intelligence.eval import qa_eval
    from drawing_intelligence.settings import Settings

    settings = Settings(data_dir=tmp_path / "data", sessions_root=tmp_path / "s")  # type: ignore[call-arg]
    monkeypatch.setattr(qa_eval, "review_drawing", lambda pdf, s: (_data_for(pdf, s), 0.0))
    script = Script("Outside what I can check; please ask your design lead.", "Not in the drawing's data.")
    res = qa_eval.run_qa_eval(settings, only=["p13-advice", "p13-roughness"], completion_fn=script)
    assert [t.passed for t in res.turns] == [True, True]
    assert res.summary()["declines_and_guards_passed"] == "2/2" and res.summary()["meets_bar"]


def _data_for(pdf: Path, settings) -> DrawingData:
    res = run_workflow(pdf, settings, understand=False, review=True)
    assert res.review is not None
    return DrawingData.build(res.extraction, {}, res.review, settings)
