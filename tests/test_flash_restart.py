"""No network: frozen selection and reporting edge cases."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from drawing_intelligence.eval import flash_restart as fresh


def test_precision_is_not_recall_and_unsure_is_visible():
    result = fresh.metrics([{"label": x} for x in ["correct", "incorrect", "unsure", "unsure"]])
    assert result["precision_decided"] == 0.5
    assert result["conservative_all_unsure_wrong"] == 0.25
    assert result["optimistic_all_unsure_right"] == 0.75
    assert fresh.metrics([])["precision_decided"] is None
    assert fresh.metrics([{"label": "unsure"}])["precision_decided"] is None
    assert fresh.wilson(0, 0) is None


def fixture_predictions(tmp_path):
    row = dict.fromkeys(fresh.COLUMNS, "")
    row.update(
        finding_key="sha:F1",
        drawing="one.pdf",
        pdf_sha256="sha",
        finding_id="F1",
        rule="XX-001",
        checked_by="llm:design_intent",
        comment="a warning",
    )
    state = {
        "complete": True,
        "billed_usd": 0.04,
        "runs": [{"path": "one.pdf", "status": "ok"}, {"path": "zero_findings.pdf", "status": "ok"}],
        "rows": [row],
    }
    fresh.dump(
        tmp_path / "manifest.json",
        {
            "n": 2,
            "snapshot": {"commit": "fixture"},
            "team_exclusions_note": "team confirmed, test date",
            "drawings": [{"path": "one.pdf"}, {"path": "zero_findings.pdf"}],
        },
    )
    state["manifest_sha256"] = fresh.digest(tmp_path / "manifest.json")
    state["rows_sha256"] = fresh.object_digest(state["rows"])
    fresh.dump(tmp_path / "run_state.json", state)
    labelled = {**row, "label": "correct", "label_reason": "drawing confirms it", "labelled_by": "Engineer"}
    return labelled


def label_file(tmp_path, row):
    path = tmp_path / "labels.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fresh.COLUMNS)
        w.writeheader()
        w.writerow(row)
    return path


def test_scoring_requires_independent_confirmation_for_final(tmp_path):
    row = fixture_predictions(tmp_path)
    labels = label_file(tmp_path, row)
    report = fresh.score(tmp_path, labels)
    assert report["status"] == "PROVISIONAL"
    assert report["completed_drawings"] == 2
    assert report["groups"]["ai_reviewers"]["precision_decided"] == 1
    assert fresh.score(tmp_path, labels, confirmation="PARI proxy, date")["status"] == "final"


def test_label_tampering_and_blank_labels_rejected(tmp_path):
    row = fixture_predictions(tmp_path)
    for change in [{"comment": "changed"}, {"label": ""}, {"label": "pass"}, {"labelled_by": ""}]:
        with pytest.raises(ValueError):
            fresh.score(tmp_path, label_file(tmp_path, {**row, **change}))


def test_failed_reviews_never_become_final_or_enter_precision(tmp_path):
    row = fixture_predictions(tmp_path)
    p = tmp_path / "run_state.json"
    state = json.loads(p.read_text())
    state["complete"] = False
    state["runs"][0]["status"] = "failed"
    fresh.dump(p, state)
    result = fresh.score(tmp_path, label_file(tmp_path, row), confirmation="Engineer")
    assert result["status"] == "PROVISIONAL"
    assert result["excluded_failed_rows"] == 1
    assert result["groups"]["ai_reviewers"]["precision_decided"] is None


def test_freeze_excludes_old_sets_and_content_duplicates(tmp_path, monkeypatch):
    client = tmp_path / "data/client_set/parts"
    client.mkdir(parents=True)
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "spikes").mkdir()
    old = tmp_path / "data/eval/heldout/old"
    old.mkdir(parents=True)
    for i in range(20):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((20, 30), f"Unique drawing {i}")
            doc.save(client / f"P{i}.pdf")
    (client / "renamed.pdf").write_bytes((client / "P2.pdf").read_bytes())
    (old / "drawings.txt").write_text("parts/P2.pdf\n")
    (old / "findings.csv").write_text("drawing,label\nP3,correct\n")
    monkeypatch.setattr(fresh, "development_sample", lambda _: {client / "P1.pdf"})
    monkeypatch.setattr(fresh, "snapshot", lambda _: {"test": "frozen"})
    monkeypatch.setattr(fresh, "endpoint_url", lambda *a: "https://example.test/v1")
    monkeypatch.setattr(fresh.subprocess, "run", lambda *a, **kw: None)
    args = {"n": 10, "seed": 7, "team_exclusions_note": "team, test date"}
    manifest = fresh.freeze(tmp_path, tmp_path / "output/manifest.json", **args)
    assert manifest["models"]["review"] == "qwen3.8-flash"
    assert manifest["budget_policy"]["new_run_soft_cap_usd"] == 2.5
    selected = {Path(r["path"]).name for r in manifest["drawings"]}
    assert not selected & {"P1.pdf", "P2.pdf", "P3.pdf", "renamed.pdf"}
    assert fresh.freeze(tmp_path, tmp_path / "output/manifest.json", **args) == manifest
    assert (
        fresh.freeze(tmp_path, tmp_path / "other/manifest.json", **args)["drawings"] == manifest["drawings"]
    )
    with pytest.raises(ValueError, match="protocol changed"):
        fresh.freeze(tmp_path, tmp_path / "output/manifest.json", **{**args, "seed": 8})


def test_changed_snapshot_cannot_reuse_freeze(tmp_path, monkeypatch):
    p = tmp_path / "manifest.json"
    fresh.dump(p, {"snapshot": {"commit": "old"}})
    monkeypatch.setattr(fresh, "snapshot", lambda _: {"commit": "new"})
    monkeypatch.setattr(fresh, "endpoint_url", lambda *a: "https://example.test/v1")
    with pytest.raises(ValueError, match="snapshot changed"):
        fresh.freeze(tmp_path, p, team_exclusions_note="team, test date")


def test_infrastructure_retry_preserves_audit_and_rejects_quality_reruns(tmp_path):
    fixture_predictions(tmp_path)
    state_file = tmp_path / "run_state.json"
    state = json.loads(state_file.read_text())
    state["runs"][0].update(status="failed", errors=["PermissionDeniedError"])
    fresh.dump(state_file, state)
    assert fresh.authorize_infrastructure_retry(tmp_path, "Model access enabled by team owner") == 1
    changed = json.loads(state_file.read_text())
    assert len(changed["runs"]) == 1 and changed["rows"] == []
    assert list((tmp_path / "failed_attempts").glob("*/state_before_retry.json"))
    assert changed["infrastructure_retry_audit"]
    state["runs"][0]["errors"] = ["understanding absent or invalid"]
    fresh.dump(state_file, state)
    with pytest.raises(ValueError, match="non-infrastructure"):
        fresh.authorize_infrastructure_retry(tmp_path, "Try a nicer output")


def test_score_recomputes_completion_instead_of_trusting_boolean(tmp_path):
    row = fixture_predictions(tmp_path)
    path = tmp_path / "run_state.json"
    state = json.loads(path.read_text())
    state["runs"].pop()  # complete=True is now stale; one planned drawing never ran.
    fresh.dump(path, state)
    result = fresh.score(tmp_path, label_file(tmp_path, row), confirmation="Engineer")
    assert result["status"] == "PROVISIONAL"


def test_manifest_and_prediction_integrity(tmp_path):
    row = fixture_predictions(tmp_path)
    path = tmp_path / "run_state.json"
    state = json.loads(path.read_text())
    state["rows"][0]["comment"] = "edited original"
    fresh.dump(path, state)
    with pytest.raises(ValueError, match="prediction rows changed"):
        fresh.score(tmp_path, label_file(tmp_path, row))
    fixture_predictions(tmp_path)
    fresh.dump(tmp_path / "manifest.json", {"n": 99})
    with pytest.raises(ValueError, match="manifest changed"):
        fresh.score(tmp_path, label_file(tmp_path, row))


def test_duplicate_ledger_drawings_rejected(tmp_path):
    row = fixture_predictions(tmp_path)
    path = tmp_path / "run_state.json"
    state = json.loads(path.read_text())
    state["runs"].append(state["runs"][0])
    fresh.dump(path, state)
    with pytest.raises(ValueError, match="duplicate or unexpected"):
        fresh.score(tmp_path, label_file(tmp_path, row))


@pytest.mark.parametrize(
    "url",
    ["http://example.test/v1", "https://user:secret@example.test/v1", "https://example.test/v1?token=secret"],
)
def test_endpoint_rejects_credentials_and_insecure_urls(tmp_path, url):
    config = tmp_path / "config"
    config.mkdir()
    (config / "models.yaml").write_text('providers: {qwen: {base_url: "https://example.test/v1"}}')
    with pytest.raises(ValueError, match="HTTPS"):
        fresh.endpoint_url(tmp_path, url)


def fake_runtime(tmp_path, monkeypatch, *, fail=False, invalid_json=False):
    from drawing_intelligence import graph
    from drawing_intelligence.storage.telemetry import CallRecord, Telemetry

    root = tmp_path / "repo"
    config = root / "config"
    config.mkdir(parents=True)
    (config / "models.yaml").write_text('providers: {qwen: {base_url: "https://example.test/v1"}}')
    client = root / "data/client_set"
    client.mkdir(parents=True)
    entries = []
    for name in ["one.pdf", "two.pdf"]:
        pdf = client / name
        pdf.write_bytes(name.encode())
        entries.append({"path": name, "sha256": fresh.digest(pdf)})
    out = root / "evaluation"
    fresh.dump(
        out / "manifest.json",
        {
            "n": 2,
            "snapshot": {"commit": "fixture"},
            "team_exclusions_note": "team, test date",
            "drawings": entries,
            "qwen_base_url": "https://example.test/v1",
        },
    )
    monkeypatch.setattr(fresh, "snapshot", lambda _: {"commit": "fixture"})
    monkeypatch.setenv("QWEN_API_KEY", "test-only-fake-key")
    calls = []

    def workflow(pdf, settings, **kwargs):
        calls.append(pdf.name)
        if fail:
            raise ConnectionError("test error text must not be exported")
        ledger = Telemetry(settings.telemetry_db)
        ledger.record_call(
            CallRecord(
                "fake-session", "review:test", "qwen", "qwen3.8-flash", "off", 1, 1, 0, 1.0, 0, False, "ok"
            )
        )
        dest = kwargs["export_dir"] / pdf.stem
        for name in ["drawing_practice", "manufacturability", "design_intent"]:
            fresh.dump(dest / f"{name}.json", {"reviewer": name})
        if invalid_json:
            fresh.dump(settings.cache_dir / "fake.json", {"model": "qwen3.8-flash", "text": "not JSON"})
        return SimpleNamespace(
            session_id="fake-session",
            extraction=SimpleNamespace(n_pages=1),
            understanding=[SimpleNamespace(valid=True)],
            exported_to=dest,
            review=SimpleNamespace(findings=[]),
            rejected=[],
        )

    monkeypatch.setattr(graph, "run_workflow", workflow)
    return root, out, calls


def test_paid_gate_and_soft_budget_resume_without_repeating_completed_drawings(tmp_path, monkeypatch):
    root, out, calls = fake_runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="approval"):
        fresh.run_once(root, out, approved_soft_budget_usd=1, approval_note="")
    assert calls == []
    first = fresh.run_once(root, out, approved_soft_budget_usd=0.5, approval_note="Binjie, test date")
    assert not first["complete"] and calls == ["one.pdf"]
    assert first["estimated_billed_usd"] == 1.0  # One drawing can exceed the soft threshold.
    second = fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="Binjie, raised budget")
    assert second["complete"] and calls == ["one.pdf", "two.pdf"]
    fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="Binjie, test date")
    assert calls == ["one.pdf", "two.pdf"]


def test_failed_attempt_cannot_be_silently_skipped_on_resume(tmp_path, monkeypatch):
    root, out, calls = fake_runtime(tmp_path, monkeypatch, fail=True)
    state = fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="Binjie, test date")
    assert not state["complete"] and state["runs"][0]["errors"] == ["ConnectionError"]
    assert "test error text" not in (out / "run_state.json").read_text()
    with pytest.raises(ValueError, match="unresolved"):
        fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="Binjie, test date")
    assert calls == ["one.pdf"]
    assert fresh.authorize_infrastructure_retry(out, "network repaired, approved by team") == 1


def test_malformed_ai_reply_is_a_failure_not_successful_silence(tmp_path, monkeypatch):
    root, out, _ = fake_runtime(tmp_path, monkeypatch, invalid_json=True)
    state = fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="Binjie, test date")
    assert not state["complete"]
    assert "invalid reviewer JSON" in state["runs"][0]["errors"]
    with pytest.raises(ValueError, match="non-infrastructure"):
        fresh.authorize_infrastructure_retry(out, "retry for a different answer")


def test_missing_cost_ledger_blocks_a_paid_resume(tmp_path, monkeypatch):
    root, out, calls = fake_runtime(tmp_path, monkeypatch)
    fresh.run_once(root, out, approved_soft_budget_usd=0.5, approval_note="Binjie, test date")
    (out / "runtime_data/telemetry.db").unlink()
    with pytest.raises(ValueError, match="cost ledger missing"):
        fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="Binjie, test date")
    assert calls == ["one.pdf"]


def test_fresh_flash_start_does_not_require_old_checkpoint(tmp_path, monkeypatch):
    root, out, calls = fake_runtime(tmp_path, monkeypatch)
    state = fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="User authorized restart")
    assert state["complete"] and calls == ["one.pdf", "two.pdf"]
    assert not (root / "max").exists()


def test_restart_budget_cannot_exceed_remaining_allowance(tmp_path, monkeypatch):
    root, out, calls = fake_runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match=r"2\.50"):
        fresh.run_once(root, out, approved_soft_budget_usd=3, approval_note="User authorized restart")
    assert not calls


def test_flash_registration_and_actual_workflow_with_fake_completions(tmp_path, monkeypatch, make_pdf):
    import importlib.util
    import shutil

    from drawing_intelligence import graph
    from drawing_intelligence.graph.workflow import run_workflow
    from drawing_intelligence.llm import load_registry

    root, out, _ = fake_runtime(tmp_path, monkeypatch)
    repo = Path(__file__).resolve().parents[1]
    shutil.copytree(repo / "config", root / "config", dirs_exist_ok=True)
    pdf = root / "data/client_set/one.pdf"
    shutil.copyfile(make_pdf(), pdf)
    manifest = json.loads((out / "manifest.json").read_text())
    manifest.update(n=1, drawings=[{"path": "one.pdf", "sha256": fresh.digest(pdf)}])
    fresh.dump(out / "manifest.json", manifest)
    spec = importlib.util.spec_from_file_location("fake_model_helpers", repo / "tests/test_workflow.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    fake = helper.FakeModel()

    def offline(*args, **kwargs):
        assert kwargs["review_model"] == "qwen3.8-flash"
        return run_workflow(*args, **kwargs, completion_fn=fake, imaging=helper.SMALL)

    monkeypatch.setattr(graph, "run_workflow", offline)
    state = fresh.run_once(root, out, approved_soft_budget_usd=2.5, approval_note="User authorized restart")
    assert state["complete"] and len(fake.calls) == 4
    assert [c["model"] for c in fake.calls].count("qwen3.8-flash") == 3
    registry = load_registry(out / "runtime_config/models.yaml")
    assert registry.model("qwen3.8-flash", "review").price.input_per_mtok == 0.15
