# 0006 uv, ruff, pyright, pytest, pre-commit, CI on three OSes

**Status:** accepted · 2026-10-06 · client-data parts superseded by [ADR 0007](0007-commit-client-data.md)

## Context
There are three developers; the main one works in VS Code on Windows. The workflow must run on any OS,
especially macOS. The repo is public; client data must never be committed.

## Decision
- **uv** with `pyproject.toml` and a committed `uv.lock`; Python ≥ 3.13; `pathlib` everywhere.
- **ruff** (lint and format), **pyright** (types), **pytest** (tests), **pre-commit** (runs them and
  blocks PDF, image, DWG and database files).
- **GitHub Actions** on Ubuntu, Windows and macOS. CI runs unit tests on **synthetic PDFs that the tests
  generate**, so no client data is needed. Tests against the real samples are marked `regression` and run
  locally only. Tests that make billed API calls are marked `live` and never run in CI.
- `.gitattributes` forces LF line endings on every OS.

## Consequences
- The same commands work on every machine: `uv sync`, `uv run pytest`, `uv run di ...`.
- CI never sees a real drawing, so regressions on real drawings are caught only when someone runs
  `pytest -m regression` locally. Do this before merging extraction changes.
