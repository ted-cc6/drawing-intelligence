"""Native held-out audit/resume checks. Synthetic PDFs and fake completions; no billed requests."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from drawing_intelligence import cli
from drawing_intelligence.eval import heldout
from drawing_intelligence.graph import run_workflow as actual_workflow
from drawing_intelligence.llm import RawCompletion
from tests.test_workflow import SMALL, FakeModel


@pytest.fixture
def batch(settings, make_pdf, tmp_path, monkeypatch):
    config = tmp_path / "config"
    shutil.copytree(Path("config"), config)
    settings = settings.model_copy(update={"config_dir": config})
    client = settings.data_path / "client_set"
    client.mkdir(parents=True)
    drawings = []
    for name in ("one.pdf", "two.pdf"):
        target = client / name
        shutil.copyfile(make_pdf(name=name), target)
        drawings.append(target)
    fake = FakeModel()

    def workflow(pdf, run_settings, **kwargs):
        return actual_workflow(pdf, run_settings, completion_fn=fake, imaging=SMALL, **kwargs)

    monkeypatch.setattr("drawing_intelligence.graph.run_workflow", workflow)
    return settings, drawings, tmp_path / "out", fake


def run(batch, **kwargs):
    settings, drawings, out, _ = batch
    return heldout.run_heldout(
        settings,
        drawings,
        out,
        approved_budget_usd=3,
        approval_note="Synthetic approval: no real API calls",
        exclusions_note="Synthetic team exclusions",
        **kwargs,
    )


def state(batch):
    return json.loads((batch[2] / "run_state.json").read_text())


def test_native_run_resumes_without_buying_or_regenerating_successes(batch):
    runs = run(batch)
    initial = state(batch)
    calls = len(batch[3].calls)
    assert len(runs) == 2 and initial["complete"]
    assert initial["estimated_billed_usd"] > 0
    assert all(r["calls"] and r["status"] == "ok" for r in initial["attempts"])
    run(batch)
    assert len(batch[3].calls) == calls
    assert state(batch)["rows"] == initial["rows"]
    assert state(batch)["attempts"] == initial["attempts"]


@pytest.mark.parametrize("change", ["drawing", "registry", "exclusions", "duplicate", "outside_client"])
def test_freeze_rejects_changed_or_unsafe_inputs_before_any_calls(batch, tmp_path, change):
    settings, drawings, out, fake = batch
    heldout.freeze_heldout(settings, drawings, out, exclusions_note="confirmed")
    note = "confirmed"
    if change == "drawing":
        drawings[0].write_bytes(drawings[0].read_bytes() + b"\nchanged")
    elif change == "registry":
        path = settings.config_path / "models.yaml"
        data = yaml.safe_load(path.read_text())
        data["defaults"]["review"] = "qwen3-vl-plus"
        path.write_text(yaml.safe_dump(data))
    elif change == "exclusions":
        note = "a different confirmation"
    elif change == "duplicate":
        drawings[1].write_bytes(drawings[0].read_bytes())
    else:
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"not a client drawing")
        drawings[0] = outside
    with pytest.raises(ValueError):
        heldout.freeze_heldout(settings, drawings, out, exclusions_note=note)
    assert fake.calls == []


@pytest.mark.parametrize(
    "budget,note", [(None, "approved"), (0, "approved"), (float("nan"), "approved"), (1, "")]
)
def test_paid_run_needs_a_real_approval_record_before_calls(batch, budget, note):
    settings, drawings, out, fake = batch
    with pytest.raises(ValueError, match="approval"):
        heldout.run_heldout(
            settings,
            drawings,
            out,
            approved_budget_usd=budget,
            approval_note=note,
            exclusions_note="confirmed",
        )
    assert fake.calls == []


def test_budget_stops_between_drawings_and_preserves_the_first_cost(batch):
    settings, drawings, out, _ = batch
    heldout.run_heldout(
        settings,
        drawings,
        out,
        approved_budget_usd=0.001,
        approval_note="Synthetic soft cap",
        exclusions_note="confirmed",
    )
    saved = state(batch)
    assert len(saved["attempts"]) == 1 and not saved["complete"]
    assert saved["estimated_billed_usd"] > 0.001  # a soft cap, never advertised as a billing hard cap


def test_server_retry_is_explicit_preserves_failures_and_keeps_prior_charges(batch, monkeypatch):
    class InternalServerError(RuntimeError):
        pass

    class FailOnce(FakeModel):
        failed = False

        def __call__(self, kwargs, api_key, base_url, timeout):
            if (
                kwargs.get("response_format", {}).get("json_schema", {}).get("name") == "Review"
                and not self.failed
            ):
                self.failed = True
                raise InternalServerError("synthetic server error")
            return super().__call__(kwargs, api_key, base_url, timeout)

    _settings, _drawings, out, _ = batch
    fake = FailOnce()
    monkeypatch.setattr(
        "drawing_intelligence.graph.run_workflow",
        lambda pdf, s, **kw: actual_workflow(pdf, s, completion_fn=fake, imaging=SMALL, **kw),
    )
    run(batch)
    before = state(batch)
    assert before["attempts"][0]["errors"] == ["InternalServerError"]
    assert before["attempts"][0]["status"] == "failed"
    with pytest.raises(ValueError, match="retry note"):
        run(batch)
    run(batch, retry_note="Synthetic authorization for the provider outage only")
    after = state(batch)
    assert after["complete"] and len(after["attempts"]) == 3
    assert after["attempts"][0] == before["attempts"][0]
    assert after["estimated_billed_usd"] >= before["estimated_billed_usd"]
    assert (out / "retry_audit/0001/state_before_retry.json").exists()
    assert any(c["cached"] for attempt in after["attempts"][1:] for c in attempt["calls"])


@pytest.mark.parametrize("reply", ["[]", "not JSON", '{"findings":[{"invented":"item"}]}'])
def test_bad_reviewer_replies_are_failures_and_cannot_be_infrastructure_retried(batch, monkeypatch, reply):
    class BadReview(FakeModel):
        def __call__(self, kwargs, api_key, base_url, timeout):
            if kwargs.get("response_format", {}).get("json_schema", {}).get("name") == "Review":
                return RawCompletion(reply, 100, 10)
            return super().__call__(kwargs, api_key, base_url, timeout)

    fake = BadReview()
    monkeypatch.setattr(
        "drawing_intelligence.graph.run_workflow",
        lambda pdf, s, **kw: actual_workflow(pdf, s, completion_fn=fake, imaging=SMALL, **kw),
    )
    run(batch)
    assert not state(batch)["complete"] and state(batch)["attempts"][0]["status"] == "failed"
    with pytest.raises(ValueError, match="schema/quality"):
        run(batch, retry_note="Cannot use a retry to get a nicer answer")


def test_prepare_cli_never_calls_models(batch, monkeypatch, tmp_path):
    settings, drawings, out, fake = batch
    names = tmp_path / "drawings.txt"
    names.write_text("\n".join(p.name for p in drawings))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "heldout",
            "--out",
            str(out),
            "--drawings",
            str(names),
            "--prepare-only",
            "--exclusions-note",
            "confirmed",
        ],
    )
    assert result.exit_code == 0, result.output
    assert fake.calls == [] and (out / "manifest.json").exists()


def test_interruption_keeps_paid_calls_before_an_authorized_retry(batch, monkeypatch):
    class InterruptOnce(FakeModel):
        interrupted = False

        def __call__(self, kwargs, api_key, base_url, timeout):
            if (
                kwargs.get("response_format", {}).get("json_schema", {}).get("name") == "Review"
                and not self.interrupted
            ):
                self.interrupted = True
                raise KeyboardInterrupt()
            return super().__call__(kwargs, api_key, base_url, timeout)

    fake = InterruptOnce()
    monkeypatch.setattr(
        "drawing_intelligence.graph.run_workflow",
        lambda pdf, s, **kw: actual_workflow(pdf, s, completion_fn=fake, imaging=SMALL, **kw),
    )
    with pytest.raises(KeyboardInterrupt):
        run(batch)
    before = state(batch)
    assert before["attempts"][0]["status"] == "started" and before["estimated_billed_usd"] > 0
    prior_calls = before["attempts"][0]["calls"]
    run(batch, retry_note="Synthetic authorization after stopped process")
    after = state(batch)
    assert after["complete"] and after["estimated_billed_usd"] >= before["estimated_billed_usd"]
    assert after["attempts"][0]["calls"] == prior_calls


def score_fixture(tmp_path):
    rows = [
        {
            "finding_key": key,
            "drawing": "drawing.pdf",
            "checked_by": producer,
            "comment": "issue",
            "label": "",
            "label_reason": "",
            "labelled_by": "",
        }
        for key, producer in (("one", "code"), ("two", "llm:design_intent"))
    ]
    manifest = {
        "n": 1,
        "models": {"review": "fixture-model"},
        "team_exclusions_note": "fixture",
        "drawings": [{"path": "drawing.pdf"}],
    }
    heldout._save(tmp_path / "manifest.json", manifest)
    heldout._save(
        tmp_path / "run_state.json",
        {
            "complete": True,
            "attempts": [{"drawing": "drawing.pdf", "status": "ok"}],
            "rows": rows,
            "manifest_sha256": heldout._file_hash(tmp_path / "manifest.json"),
            "rows_sha256": heldout._hash(rows),
            "estimated_billed_usd": 0,
        },
    )
    write_rows(tmp_path / "findings.csv", rows)
    labels = [
        {
            **r,
            "label": "correct" if r["checked_by"] == "code" else "unsure",
            "label_reason": "synthetic test judgment",
            "labelled_by": "synthetic human",
        }
        for r in rows
    ]
    return labels


def write_rows(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_score_separates_ai_and_code_and_zero_decided_is_undefined(tmp_path):
    labels = score_fixture(tmp_path)
    path = tmp_path / "labels.csv"
    write_rows(path, labels)
    result = heldout.score_heldout(tmp_path, path)
    assert result["status"] == "PROVISIONAL"
    assert result["groups"]["code_lookup"]["precision_decided"] == 1
    assert result["groups"]["ai_reviewers"]["precision_decided"] is None
    assert not (tmp_path / "metrics.json").exists()


@pytest.mark.parametrize(
    "change", ["edited_prediction", "duplicate", "missing", "blank_reason", "ai_attribution"]
)
def test_scoring_refuses_changed_rows_and_unreviewed_labels(tmp_path, change):
    labels = score_fixture(tmp_path)
    if change == "edited_prediction":
        labels[0]["comment"] = "changed"
    elif change == "duplicate":
        labels[1] = labels[0]
    elif change == "missing":
        labels.pop()
    elif change == "blank_reason":
        labels[0]["label_reason"] = ""
    else:
        labels[0]["labelled_by"] = "Codex (AI-assisted draft)"
    path = tmp_path / "labels.csv"
    write_rows(path, labels)
    with pytest.raises(ValueError):
        heldout.score_heldout(
            tmp_path, path, engineer_confirmation="fixture", label_review_confirmation="fixture"
        )


def test_final_score_requires_both_actual_confirmations(tmp_path):
    path = tmp_path / "labels.csv"
    write_rows(path, score_fixture(tmp_path))
    assert heldout.score_heldout(tmp_path, path, engineer_confirmation="fixture")["status"] == "PROVISIONAL"
    assert (
        heldout.score_heldout(
            tmp_path, path, engineer_confirmation="fixture", label_review_confirmation="fixture"
        )["status"]
        == "final"
    )
