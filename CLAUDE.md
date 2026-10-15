# CLAUDE.md: context for Claude Code

Read this fully before changing anything. The design is in [docs/PROJECT.md](docs/PROJECT.md); the decisions
behind it are in [docs/adr/](docs/adr/). Do not re-open a decision recorded in an ADR without asking.

## What this is
Drawing Intelligence: an agentic AI "last point check" for 2D engineering drawings (UChicago capstone with
client LatentView Analytics). Pipeline:
- A fixed LangGraph workflow: intake (code) → understand (vision LLM) → specialist reviewers → verifier →
  report.
- One Q&A agent over the saved results.

Built so far: intake and understand. The original notebooks live in `D:\Capstone\demo` (read-only reference;
do not edit them).

## Layout
```
src/drawing_intelligence/
  settings.py          env + .env settings (DI_* variables, API keys as SecretStr)
  schemas/             Pydantic data contracts: Extraction, DrawingKnowledge, review (Finding, RuleStatus,
                       ReviewResult, FindingFeedback) - versioned
  extraction/          stage 1 - text layer, token cleanup, classification, geometry/chain checks, images
  llm/                 model registry + one OpenAI-SDK client for OpenAI and Qwen (cost, latency, cache)
  understanding/       stage 2 - prompt, message building, call + validate + retry
  review/              stage 3 - rulebook (Rule, load_rulebook, new_finding); reviewers come next
  graph/               LangGraph state and graph (intake -> understand)
  storage/             session workspaces (ephemeral), telemetry DB, response cache
  eval/                baseline diff, understanding scorecard
  viz/                 annotated images for humans (never needed by the pipeline)
  cli.py               the `di` command
config/models.yaml     model registry: prices, capabilities, roles, thinking options, role defaults
config/templates/      drawing-template regions and glyph remaps
config/rules/          the rulebook, one YAML list of rules per file (see its README)
data/                  committed (ADR 0007): raw PDFs, client_set, baseline, labels, cache, telemetry.db
```

## Hard rules
1. **Client data is committed; secrets are not** (ADR 0007). Everything in `data/` is in git, including the
   client's full dataset in `data/client_set/`, and the repo is public. Never rewrite files in `data/baseline/`
   or `data/labels/` without being asked.
2. **Never print, log or commit an API key.** Keys come from `.env` via `settings.py` as `SecretStr`. Only
   `OPENAI_API_KEY` and `QWEN_API_KEY` belong in `.env`.
3. **Never invent data.** LLM outputs must be traceable to the PDF text or marked `source: "vision"`;
   unknown → `null`.
4. **At runtime, client data is session-scoped** (ADR 0003): anything a session produces goes in its
   workspace, which is deleted at the end unless `DI_RETENTION=keep`. Telemetry rows never contain drawing content.
5. **Models are chosen through `config/models.yaml`**, never hard-coded. New models and prices go there.
6. **Cross-platform:** `pathlib` only, no shell-specific code. CI runs on Windows, macOS and Linux.
7. **Don't waste API calls.** Unit tests use fake LLM clients. Tests that cost money are marked `live`; run
   them only when asked. Use Qwen models during development; never call `gpt-6-astra` without Binjie's OK.

## Commands
```
uv sync                         # install
uv run pytest                   # unit tests (synthetic PDFs, fake LLM)
uv run pytest -m regression     # real sample drawings in data/raw (also run in CI)
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run di --help
```
Run all checks and tests before saying a change is done.

## How to work with the team
- Propose a short plan before larger changes; build in small steps and small commits.
- Branch from `main` (`feat/...`, `fix/...`). The humans push and open PRs.
- Explain what changed and why in plain language.
- Keep `docs/PROJECT.md` up to date when the design or roadmap changes. Add an ADR for a new decision.
