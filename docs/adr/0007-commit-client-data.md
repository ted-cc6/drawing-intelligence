# 0007 Commit the client data to the repository

**Status:** accepted · 2026-10-06 · supersedes the "client data never committed" parts of
[ADR 0006](0006-tooling.md) and `CLAUDE.md`

## Context
Three people now build in parallel. Each needs the sample drawings, the notebook baseline and the labels to
run the regression tests and evaluations. Sharing a separate zip is extra friction and goes out of date.
LatentView has agreed that the repository can be public. The team puts ease of sharing ahead of keeping the
data private.

## Decision
- Everything under `data/` is committed:
  - `raw/`: the four sample PDFs
  - `baseline/`: the notebook outputs
  - `labels/`
  - `cache/`: model replies, so identical requests are free for everyone
  - `exports/`, `sessions/`, `telemetry.db`
  - `client_set/`: the client's full dataset (about 1,170 drawings, the Check List, the WP Guidelines and
    the template; 125 MB, no file over 50 MB, so no Git LFS)
- **API keys are never committed.** `.env` stays git-ignored, a pre-commit hook blocks `.env` files, and keys
  are shared privately between teammates.
- CI now also runs the regression tests on the committed samples, on all three OSes.
- Runtime behaviour does not change. [ADR 0003](0003-session-scoped-data.md) still applies to real client
  sessions: `DI_RETENTION=ephemeral` is the default and deletes a session's workspace when it ends.

## Consequences
- `git clone` gives a teammate everything needed to run every command except live model calls.
- Anyone on the internet can download the client's drawings and guidelines.
- The repo grows with every committed run (`sessions/`, `cache/`, `telemetry.db`). Prune `data/sessions/`
  now and then, and add Git LFS if the repo gets large.
- `telemetry.db` and `sessions/` change on every machine, so they will sometimes conflict in pull requests.
  Telemetry is only cost and latency history: resolve by keeping either version
  (`git checkout --theirs data/telemetry.db`).
