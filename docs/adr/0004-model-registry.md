# 0004 One model registry file drives model choice, prices and thinking

**Status:** accepted · 2026-10-06

## Context
The future dashboard must let a user pick a model per role and see cost and latency. Prices change, and
models differ in their thinking controls: `gpt-6-astra` accepts `reasoning_effort`
low/medium/high/xhigh and cannot switch reasoning off; Qwen models take `enable_thinking` on or off.

## Decision
`config/models.yaml` lists providers and models. Each model entry holds:
- prices, with `verified_on` and a source URL
- capabilities
- allowed roles
- the request parameters for each of its named thinking options

A `defaults` section names the model for each role. The CLI (`--model`, `--thinking`) and the future
dashboard offer exactly what the registry lists. `di models` warns about prices older than 60 days.

## Consequences
- Adding or switching a model is a config change, not a code change.
- Cost numbers are only as good as the hand-entered prices, so the staleness warning matters.
- Registered today: `gpt-6-astra`, `qwen3.8-max`, `qwen3-vl-plus`.
