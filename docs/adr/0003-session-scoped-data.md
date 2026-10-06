# 0003 Client data lives only for one session

**Status:** accepted · 2026-10-06

## Context
The workflow must drop all client information when a client's session ends. Several pieces of the earlier
design stored client content: the response cache, LangGraph checkpoints, and the planned feedback log.

## Decision
- A **session** is one upload or one `di run`. Everything it produces lives in `data/sessions/<id>/`,
  including its own SQLite file for checkpoints and cache. That folder is **deleted when the session ends**.
  Leftover folders from crashed sessions are swept at the next start.
- A **persistent telemetry database** keeps only session id, node, provider, model, thinking level, tokens,
  cost, latency, cache hit and status. It holds no file names, drawing numbers or text.
- The **feedback log** (planned) keeps rule id, finding category, severity, accepted/rejected and model,
  with no drawing content.
- `DI_RETENTION=ephemeral` is the default. `keep` is for development: it keeps workspaces and a
  cross-session response cache.
- OpenAI calls are sent with `store=false`.

## Consequences
- Production runs never reuse a previous session's LLM answers, so a repeated drawing is paid for again.
- Provider-side retention (e.g. abuse monitoring) depends on the providers' account policies; the code
  cannot control it.
- Feedback stays useful for spotting which rules and models produce false alarms, but it cannot be replayed
  against the original drawings.
