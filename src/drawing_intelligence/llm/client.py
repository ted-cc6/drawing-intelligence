"""One client for every registered model (OpenAI and Qwen via its OpenAI-compatible API), ADR 0002.

It owns what the workflow needs to control: strict JSON-schema output, the per-model thinking options, the
response cache, exact token/cost/latency accounting and the content-free telemetry row for every call.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema  # the SDK's own strict-schema converter
from pydantic import BaseModel

from drawing_intelligence.llm.registry import ModelSpec, Registry, Role
from drawing_intelligence.settings import Settings
from drawing_intelligence.storage import CallRecord, ResponseCache, Telemetry


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    name: str
    png: bytes


Part = TextPart | ImagePart


@dataclass
class LLMResponse:
    text: str
    model: str
    thinking: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float  # cost of the original call, also when served from the cache
    latency_s: float  # latency of the original call, also when served from the cache
    cached: bool


@dataclass
class RawCompletion:
    text: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0


# (request kwargs, api_key, base_url, timeout) -> completion. Swappable so tests never hit an API.
CompletionFn = Callable[[dict[str, Any], str, str | None, float], RawCompletion]


class MissingKeyError(RuntimeError):
    pass


def openai_completion(
    kwargs: dict[str, Any], api_key: str, base_url: str | None, timeout: float
) -> RawCompletion:
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2)
    r = client.chat.completions.create(**kwargs)
    u = r.usage
    details = getattr(u, "completion_tokens_details", None) if u else None
    return RawCompletion(
        text=r.choices[0].message.content or "",
        input_tokens=u.prompt_tokens if u else 0,
        output_tokens=u.completion_tokens if u else 0,
        reasoning_tokens=(getattr(details, "reasoning_tokens", 0) or 0) if details else 0,
    )


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = (
            _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
        )
    return out


def response_format(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": schema.__name__, "strict": True, "schema": to_strict_json_schema(schema)},
    }


class LLMClient:
    def __init__(
        self,
        registry: Registry,
        settings: Settings,
        telemetry: Telemetry,
        cache: ResponseCache | None,
        session_id: str,
        completion_fn: CompletionFn = openai_completion,
    ):
        self.registry = registry
        self.settings = settings
        self.telemetry = telemetry
        self.cache = cache
        self.session_id = session_id
        self.completion_fn = completion_fn

    def build_request(
        self, spec: ModelSpec, parts: list[Part], schema: type[BaseModel] | None, thinking: str
    ) -> dict[str, Any]:
        provider = self.registry.provider(spec)
        content: list[dict[str, Any]] = []
        for p in parts:
            if isinstance(p, ImagePart):
                img: dict[str, Any] = {"url": "data:image/png;base64," + base64.b64encode(p.png).decode()}
                if provider.image_detail:
                    img["detail"] = provider.image_detail
                content.append({"type": "image_url", "image_url": img})
            else:
                content.append({"type": "text", "text": p.text})
        req: dict[str, Any] = {
            "model": spec.name,
            "messages": [{"role": "user", "content": content}],
            provider.max_tokens_param: spec.max_output_tokens,
        }
        if spec.temperature is not None:
            req["temperature"] = spec.temperature
        if schema is not None:
            req["response_format"] = response_format(schema)
        for extra in (provider.request, spec.request, spec.thinking.options[thinking]):
            req = _merge(req, extra)
        return req

    @staticmethod
    def cache_key(req: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def complete(
        self,
        parts: list[Part],
        *,
        role: Role,
        node: str,
        model: str | None = None,
        thinking: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        spec = self.registry.model(model, role)
        level = spec.thinking_level(thinking)
        provider = self.registry.provider(spec)
        req = self.build_request(spec, parts, schema, level)
        key = self.cache_key(req)

        hit = self.cache.get(key) if self.cache else None
        if hit is not None:
            resp = LLMResponse(**{**hit, "cached": True})
            self._record(spec, node, resp, billed=0.0, status="ok")
            return resp

        api_key = self.settings.api_key(provider.api_key_env)
        if not api_key:
            raise MissingKeyError(f"{provider.api_key_env} is not set in .env (needed for {spec.name})")

        t0 = time.perf_counter()
        try:
            raw = self.completion_fn(req, api_key, provider.base_url, self.settings.api_timeout_s)
        except Exception as e:
            err = LLMResponse("", spec.name, level, 0, 0, 0, 0.0, round(time.perf_counter() - t0, 2), False)
            self._record(spec, node, err, billed=0.0, status="error", error_type=type(e).__name__)
            raise
        resp = LLMResponse(
            text=raw.text,
            model=spec.name,
            thinking=level,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            reasoning_tokens=raw.reasoning_tokens,
            cost_usd=round(spec.cost(raw.input_tokens, raw.output_tokens), 6),
            latency_s=round(time.perf_counter() - t0, 2),
            cached=False,
        )
        if self.cache:
            self.cache.put(key, {k: v for k, v in resp.__dict__.items() if k != "cached"})
        self._record(spec, node, resp, billed=resp.cost_usd, status="ok")
        return resp

    def _record(
        self,
        spec: ModelSpec,
        node: str,
        r: LLMResponse,
        *,
        billed: float,
        status: str,
        error_type: str | None = None,
    ) -> None:
        self.telemetry.record_call(
            CallRecord(
                session_id=self.session_id,
                node=node,
                provider=spec.provider,
                model=spec.name,
                thinking=r.thinking,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                reasoning_tokens=r.reasoning_tokens,
                cost_usd=billed,
                latency_s=0.0 if r.cached else r.latency_s,
                cached=r.cached,
                status=status,
                error_type=error_type,
            )
        )
