from datetime import date
from typing import Any

import pytest
from pydantic import BaseModel

from drawing_intelligence.llm import (
    ImagePart,
    LLMClient,
    MissingKeyError,
    RawCompletion,
    TextPart,
    load_registry,
)
from drawing_intelligence.schemas import DrawingKnowledge
from drawing_intelligence.storage import ResponseCache, Telemetry


class Answer(BaseModel):
    answer: int


class FakeCompletion:
    def __init__(self, text: str = '{"answer": 5}', fail: Exception | None = None):
        self.text, self.fail, self.calls = text, fail, []

    def __call__(
        self, kwargs: dict[str, Any], api_key: str, base_url: str | None, timeout: float
    ) -> RawCompletion:
        self.calls.append({"kwargs": kwargs, "api_key": api_key, "base_url": base_url})
        if self.fail:
            raise self.fail
        return RawCompletion(self.text, input_tokens=1_000_000, output_tokens=100_000, reasoning_tokens=10)


@pytest.fixture
def registry():
    return load_registry()


def _client(registry, settings, tmp_path, fake, cache=True):
    tel = Telemetry(tmp_path / "t.db")
    return LLMClient(
        registry, settings, tel, ResponseCache(tmp_path / "c") if cache else None, "s1", fake
    ), tel


def test_registry_is_consistent(registry):
    assert {"gpt-6-astra", "qwen3.8-max", "qwen3-vl-plus"} <= set(registry.models)
    for role in ("understand", "review", "qa"):
        assert registry.model(None, role)  # every role has a valid default
    astra = registry.models["gpt-6-astra"]
    assert astra.thinking.default in astra.thinking.options
    assert astra.price.age_days(date(2026, 10, 1)) == 1


def test_registry_rejects_bad_choices(registry):
    with pytest.raises(ValueError, match="unknown model"):
        registry.model("gpt-0", "understand")
    with pytest.raises(ValueError, match="not allowed"):
        registry.model("qwen3-vl-plus", "review")
    with pytest.raises(ValueError, match="no thinking option"):
        registry.models["gpt-6-astra"].thinking_level("off")


def test_openai_request(registry, settings, tmp_path):
    client, _ = _client(registry, settings, tmp_path, FakeCompletion())
    spec = registry.models["gpt-6-astra"]
    req = client.build_request(spec, [TextPart("hi"), ImagePart("a.png", b"\x89PNG")], Answer, "high")
    assert req["store"] is False  # OpenAI must not store requests
    assert req["reasoning_effort"] == "high"
    assert req["max_completion_tokens"] == spec.max_output_tokens
    assert "temperature" not in req
    assert req["response_format"]["json_schema"]["strict"] is True
    img = req["messages"][0]["content"][1]["image_url"]
    assert img["url"].startswith("data:image/png;base64,") and img["detail"] == "high"


def test_qwen_request_merges_extra_body(registry, settings, tmp_path):
    client, _ = _client(registry, settings, tmp_path, FakeCompletion())
    req = client.build_request(registry.models["qwen3-vl-plus"], [TextPart("hi")], None, "on")
    assert req["extra_body"] == {"vl_high_resolution_images": True, "enable_thinking": True}
    assert req["max_tokens"] == 16000 and req["temperature"] == 0
    assert "store" not in req and "response_format" not in req


def test_strict_schema_for_drawing_knowledge():
    # every object in the schema must be closed and fully required, or strict mode rejects it
    from drawing_intelligence.llm.client import response_format

    schema = response_format(DrawingKnowledge)["json_schema"]["schema"]
    objs = [schema, *schema.get("$defs", {}).values()]
    for o in objs:
        if o.get("type") == "object":
            assert o["additionalProperties"] is False
            assert set(o["required"]) == set(o["properties"])


def test_complete_records_cost_and_caches(registry, settings, tmp_path):
    fake = FakeCompletion()
    client, tel = _client(registry, settings, tmp_path, fake)
    r1 = client.complete(
        [TextPart("q")], role="understand", node="understand", model="qwen3-vl-plus", schema=Answer
    )
    assert r1.cost_usd == pytest.approx(0.143 + 0.1434)
    assert fake.calls[0]["api_key"] == "qwen-fake" and "dashscope" in fake.calls[0]["base_url"]
    r2 = client.complete(
        [TextPart("q")], role="understand", node="understand", model="qwen3-vl-plus", schema=Answer
    )
    assert r2.cached and len(fake.calls) == 1 and r2.text == r1.text
    rows = tel.calls("s1")
    assert [r["cached"] for r in rows] == [0, 1]
    assert rows[1]["cost_usd"] == 0  # a cache hit costs nothing
    assert set(rows[0]) >= {"model", "thinking", "input_tokens", "latency_s"}


def test_telemetry_never_stores_content(registry, settings, tmp_path):
    client, tel = _client(registry, settings, tmp_path, FakeCompletion(text='{"secret": "P24BSA064533"}'))
    client.complete([TextPart("DRAWING P24BSA064533")], role="understand", node="understand")
    dump = repr(tel.calls())
    assert "P24BSA064533" not in dump


def test_errors_are_recorded_without_message(registry, settings, tmp_path):
    client, tel = _client(
        registry, settings, tmp_path, FakeCompletion(fail=TimeoutError("drawing P24 timed out"))
    )
    with pytest.raises(TimeoutError):
        client.complete([TextPart("q")], role="understand", node="understand")
    (row,) = tel.calls()
    assert row["status"] == "error" and row["error_type"] == "TimeoutError"
    assert "P24" not in repr(row)


def test_missing_key(registry, settings, tmp_path):
    settings.qwen_api_key = None
    client, _ = _client(registry, settings, tmp_path, FakeCompletion(), cache=False)
    with pytest.raises(MissingKeyError, match="QWEN_API_KEY"):
        client.complete([TextPart("q")], role="understand", node="understand", model="qwen3-vl-plus")
