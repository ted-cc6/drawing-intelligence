import json

import pytest
from typer.testing import CliRunner

from drawing_intelligence import cli
from drawing_intelligence.eval.baseline import diff_page
from drawing_intelligence.eval.scorecard import Targets, invented_numbers, score
from drawing_intelligence.extraction import extract_pdf
from tests.test_workflow import knowledge_from_request

runner = CliRunner()


def _knowledge(page):
    req = {"messages": [{"content": [{"text": "EXTRACTED TEXT (JSON):\n" + page.model_dump_json()}]}]}
    return knowledge_from_request(req)


def test_perfect_answer_scores_full_marks(make_pdf):
    page = extract_pdf(make_pdf()).pages[0]
    sc = score("d", "fake", _knowledge(page), page, seconds=10, cost_usd=0.01, truth=None)
    assert sc.valid and sc.dims_found == sc.dims_total and not sc.invented
    assert sc.passed(Targets()) == {
        "1 valid": True,
        "2 title block": None,
        "3 dims complete": True,
        "4 invented": True,
        "7 time": True,
        "7 cost": True,
    }


def test_invented_number_is_flagged_but_vision_items_are_not(make_pdf):
    page = extract_pdf(make_pdf()).pages[0]
    k = _knowledge(page)
    k["drawing"]["weight"] = "9.87 kg"  # not on the drawing
    k["dimensions"].append(dict(k["dimensions"][0], id="V1", text="777", source="vision"))
    assert invented_numbers(k, page.model_dump(mode="json")) == [("drawing.weight", "9.87")]


def test_title_block_against_labels(make_pdf):
    page = extract_pdf(make_pdf()).pages[0]
    k = _knowledge(page)
    k["drawing"]["number"] = "P24TEST000001"
    truth = dict.fromkeys(k["drawing"]) | {"number": "P24-TEST-000001", "material": "EN8"}
    sc = score("d", "fake", k, page, seconds=1, cost_usd=0, truth=truth)
    assert sc.title_block_misses == [("material", "EN8", None)]  # punctuation-insensitive on the number


def test_baseline_diff_reports_changes(make_pdf):
    page = extract_pdf(make_pdf()).pages[0]
    base = json.loads(page.model_dump_json())
    base["dimensions"] = base["dimensions"][1:]
    (dims,) = [d for d in diff_page(base, page) if d.section == "dimensions"]
    assert not dims.identical and len(dims.only_new) == 1 and not dims.only_baseline


@pytest.fixture
def cli_settings(settings, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


def test_cli_models(cli_settings):
    r = runner.invoke(cli.app, ["models"])
    assert r.exit_code == 0 and "gpt-6-astra" in r.output and "qwen3.8-max" in r.output


def test_cli_extract_is_ephemeral(cli_settings, make_pdf):
    r = runner.invoke(cli.app, ["extract", str(make_pdf())])
    assert r.exit_code == 0, r.output
    assert "dimensions" in r.output and "deleted" in r.output
    assert not any(cli_settings.sessions_dir.iterdir())


def test_cli_unknown_thinking_option(cli_settings, make_pdf):
    r = runner.invoke(cli.app, ["run", str(make_pdf()), "--model", "gpt-6-astra", "--thinking", "off"])
    assert r.exit_code != 0 and "no thinking option" in str(r.exception)


def test_cli_review_without_understanding(cli_settings, make_pdf):
    r = runner.invoke(cli.app, ["review", str(make_pdf(overall="405")), "--no-understand"])
    assert r.exit_code == 0, r.output
    assert "CN-001" in r.output and "rules:" in r.output and "not checked" in r.output


def test_cli_rules_shows_built_checks(cli_settings):
    r = runner.invoke(cli.app, ["rules"])
    assert r.exit_code == 0, r.output
    text = " ".join(r.output.split())  # rich wraps to the terminal width
    assert "have a built check" in text and "not built yet" in text
