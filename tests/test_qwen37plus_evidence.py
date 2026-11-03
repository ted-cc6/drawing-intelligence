"""Checks for published evidence; no API credentials or network calls."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).resolve().parents[1] / "spikes/qwen37plus/verify_results.py"
    spec = importlib.util.spec_from_file_location("plus_evidence_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_published_run_is_complete_and_unlabelled(verifier):
    summary = verifier.verify()
    assert summary["successful_drawings"] == 24
    assert sum(v for k, v in summary["by_source"].items() if k.startswith("llm:")) == 32
    assert summary["human_validation_status"] == "pending"


def test_changed_evidence_is_rejected(verifier):
    with pytest.raises(ValueError, match="Published evidence changed"):
        verifier.validate_file(b"changed", verifier.digest(b"original"), "run_state.json")


def test_bundled_report_preserves_original_json_bytes(verifier, tmp_path):
    name = "full/reports/0001/drawing/drawing_practice.json"
    original = '{\n  "findings": []\n}\n'
    bundled = {name: original}
    data = verifier.read_evidence(tmp_path, name, bundled)
    verifier.validate_file(data, verifier.digest(original.encode("utf-8")), name)
    assert data == original.encode("utf-8")


def test_modified_bundled_report_is_rejected(verifier, tmp_path):
    name = "full/reports/0001/drawing/drawing_practice.json"
    original = '{"findings":[]}'
    bundled = {name: '{"findings":[{"changed":true}]}'}
    with pytest.raises(ValueError, match="Published evidence changed"):
        verifier.validate_file(
            verifier.read_evidence(tmp_path, name, bundled),
            verifier.digest(original.encode("utf-8")),
            name,
        )
