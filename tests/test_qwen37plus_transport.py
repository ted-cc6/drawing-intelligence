"""Regression coverage for the trial's content-list adapter bug and bounded retries."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def transport(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "spikes/qwen37plus/transport.py"
    spec = importlib.util.spec_from_file_location("plus_transport_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("MAX_RECOVERY_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("MAX_RECOVERY_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("MAX_RECOVERY_WAITS", "0,0")
    monkeypatch.setenv("MAX_FALLBACK_BASE_URL", "")
    return module


def test_content_list_is_forwarded_without_mutation(transport, monkeypatch):
    request = {
        "model": "qwen3.7-plus",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Drawing evidence"}]}],
    }
    received = []

    def complete(kwargs, *args):
        received.append(kwargs)
        return transport.RawCompletion(text='{"findings":[]}', input_tokens=10, output_tokens=4)

    monkeypatch.setattr(transport, "_stream_once", complete)
    result = transport._resilient_completion_serial(request, "fake-key", "https://example.test", 1)
    assert result.text == '{"findings":[]}'
    assert received[0]["messages"] == request["messages"]
    assert received[0]["stream"] is True
    assert "stream" not in request


def test_retries_are_bounded_and_keep_request_parameters(transport, monkeypatch):
    request = {"model": "qwen3.7-plus", "temperature": 0, "messages": []}
    calls = []

    def fail(kwargs, *args):
        calls.append(kwargs)
        raise ConnectionError("Synthetic interrupted connection")

    monkeypatch.setattr(transport, "_stream_once", fail)
    with pytest.raises(ConnectionError):
        transport._resilient_completion_serial(request, "fake-key", "https://example.test", 1)
    assert len(calls) == 3
    assert all(call == calls[0] for call in calls)
    assert "stream" not in request
