# 0002 Call OpenAI and Qwen through the `openai` SDK in our own `llm/` module

**Status:** accepted · 2026-10-06

## Context
The providers are OpenAI and Alibaba Qwen. Qwen offers an OpenAI-compatible endpoint. On 2026-10-06 both
providers accepted the same strict `json_schema` response format, with and without thinking. The dashboard
needs exact token, cost and latency numbers per call. Qwen needs provider-specific parameters
(`enable_thinking`, `vl_high_resolution_images`), and OpenAI calls must not be stored (`store=false`).

## Decision
- One thin `llm/` module on the `openai` SDK, configured per provider from the model registry (base URL,
  key, request parameters).
- It owns caching, retries, strict-schema output, telemetry and the retention-related request flags.
- LangGraph orchestrates; it does not wrap the model calls. We do not use LangChain chat-model wrappers.

## Consequences
- Exact control over cost accounting, retention flags and provider quirks, in about 200 lines we own.
- Adding a non-OpenAI-compatible provider later means writing one adapter behind the same interface.
- We give up LangChain's ready-made integrations (e.g. callbacks, LangSmith auto-tracing). Our telemetry
  database covers what the dashboard needs.
