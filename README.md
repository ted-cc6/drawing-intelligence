# Drawing Intelligence

**From engineering drawings to reviewed, production-ready insights.**

Before a part goes into production, an engineer checks its 2D drawing by hand for conflicting dimensions,
infeasible tolerances, missing specifications and title-block errors. This "last point check" is slow and
depends on individual experience. Drawing Intelligence automates it with an agentic AI workflow:

```
PDF ─► Intake (code) ─► Understand (vision LLM) ─► Review (specialist reviewers) ─► Verify ─► Report
                                                                                    ▲
                              Engineer ◄─► Q&A agent (answers from the saved results)┘
```

| Stage | What it does | Status |
|---|---|---|
| Intake | Exact text, dimensions, chain-sum checks and images from the PDF's own text layer and vectors | ✅ built |
| Understand | One vision-LLM call turns images + exact text into a typed drawing JSON | ✅ built |
| Review | Consistency (code), standards, manufacturability, design-intent reviewers | planned |
| Verify & report | Rejects findings with fake citations; engineering review report | planned |
| Q&A | An agent that answers questions about a drawing, citing evidence | planned |

See [docs/PROJECT.md](docs/PROJECT.md) for the full design and roadmap, and [docs/adr/](docs/adr/) for the
decisions behind it.

## Quick start (Windows, macOS, Linux)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/ted-cc6/drawing-intelligence.git
cd drawing-intelligence
uv sync                       # creates .venv with Python 3.13 and all dependencies
cp .env.example .env          # then put your OPENAI_API_KEY and QWEN_API_KEY in .env
uv run di --help
```

The four sample drawings are in `data/raw/` and the client's full set in `data/client_set/`. Then:

```bash
uv run di models                                        # registered models, prices, thinking options
uv run di extract data/raw/my_drawing.pdf               # step 1 only, no API cost
uv run di run data/raw/my_drawing.pdf --model qwen3-vl-plus --thinking off
uv run di run data/raw/my_drawing.pdf --export data/exports   # keep outputs + annotated images
uv run di eval baseline                                 # compare extraction with the notebook baseline
uv run di eval understand --from-baseline               # score the notebook's saved LLM outputs (free)
uv run di eval understand --model qwen3.8-max           # score a model on data/raw (asks before paying)
uv run di telemetry                                     # average cost and latency per model
```

By default every run is **ephemeral**: the drawing, images and results are deleted when the run ends and only
anonymous cost/latency telemetry is kept. Set `DI_RETENTION=keep` in `.env` while developing to keep outputs
and the response cache in `data/`.

## Development

```bash
uv run pytest                 # unit tests (synthetic PDFs, no client data, no API calls)
uv run pytest -m regression   # also run against the real sample drawings in data/, if present
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pre-commit install     # run the checks on every commit
```

Sample and client data are committed in `data/` ([ADR 0007](docs/adr/0007-commit-client-data.md)). API keys never are: `.env` is git-ignored.

## About

A University of Chicago MS in Applied Data Science capstone project, in partnership with LatentView Analytics.
Team: Binjie Wang, Mushahid Raza, Zhetao Zhang.
