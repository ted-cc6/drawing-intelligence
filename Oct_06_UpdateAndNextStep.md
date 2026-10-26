# Oct 06 update and next steps

> **Superseded by the [Oct 25 update](Oct_25_UpdateAndNextStep.md).** Kept as the original plan; §2 there says
> what happened to every task below.

*For: Mushahid Raza, Zhetao Zhang · From: Binjie Wang · 2026-10-06*

This document covers what was built, how to run it, and who builds what next.

Read [docs/PROJECT.md](../PROJECT.md) for the full design and [docs/adr/](../adr/) for the decisions behind it.
Claude Code reads [CLAUDE.md](../../CLAUDE.md) automatically, so it knows the project rules too.

---

## 1. What has been built

Notebooks `01_pdf_extraction` and `02_vision_llm` from the demo were rebuilt as a Python package. That package
is the start of an **agentic AI workflow** for reviewing engineering drawings.

```
                ┌──────────────── REVIEW WORKFLOW (LangGraph, fixed path) ────────────────┐
PDF ─► 1 Intake ─► 2 Understand ─► 3 Review (parallel reviewers) ─► 4 Verify ─► 5 Report
       code ✅       vision LLM ✅    next phase                       next phase   next phase
                └────────────────────────────────────────────────────────────────────────┘
Engineer ◄─► Q&A agent (later)
```

**Why this shape** ([ADR 0001](../adr/0001-workflow-plus-qa-agent.md)):
- Review always runs the same steps, so it's a **fixed graph**: reproducible, explainable, and only judgement
  steps pay for an LLM.
- Only open-ended Q&A will be a free-roaming agent.
- Extraction is plain code: the PDF text layer is exact and costs nothing.

### Modules

| Module | What it does |
|---|---|
| `schemas/` | Typed data contracts every stage reads and writes: `Extraction` (stage 1) and `DrawingKnowledge` (stage 2). `DrawingKnowledge` is also the **strict JSON schema** sent to the model. |
| `extraction/` | Stage 1. Reads exact text and vector lines from the PDF (every page), cleans split dimensions, finds reference dimensions, classifies text, gives dimensions IDs `D1…Dn`, matches dimension lines, checks chain sums, renders images for the model. Template regions are in `config/templates/wipro_pari.yaml`. |
| `llm/` | **One client for OpenAI and Qwen** (Qwen through its OpenAI-compatible API). It handles strict JSON output, each model's thinking options, the response cache, and exact token, cost and latency accounting. Models, prices and thinking options are in **`config/models.yaml`** ([ADR 0004](../adr/0004-model-registry.md)). |
| `understanding/` | Stage 2. The prompt (`understanding/prompts/understand.md`), the images and exact text, one call per page, one retry if the reply doesn't match the schema, and a check that every `D` id came back unchanged. |
| `graph/` | LangGraph workflow: intake → understand, with each session's checkpoints in its own SQLite file. |
| `storage/` | Session workspaces, deleted after each run unless `DI_RETENTION=keep` ([ADR 0003](../adr/0003-session-scoped-data.md)); response cache; **telemetry** (cost and latency per call, no drawing content). |
| `eval/` | `baseline`: diff against the notebook's outputs. `scorecard`: notebook 02's criteria 1–4 and 7. |
| `viz/` | Annotated images for humans. |
| `cli.py` | The `di` command. |

### Results so far
- **Extraction is identical to the notebook** on all four samples, in every section.
- **The ported scorecard reproduces notebook 02's findings:** every model returned 81/81 dimensions unchanged
  with 0 invented numbers; the title block was 100 % for Gemini and `gpt-6-astra`, with two misses for
  `qwen3-vl-plus`.
- **The new strict schema catches more:** it flags an old Qwen answer that made up feature types (`"distance"`).
- **First live run in the package** (`qwen3-vl-plus` on the Cam Plate): valid, 21/21 dimensions, 69 s, $0.011.
- **77 tests:** synthetic PDFs and a fake model, plus regression tests on the real samples. CI runs on Windows,
  macOS and Linux.

### Data is in the repo
Everything under `data/` is committed ([ADR 0007](../adr/0007-commit-client-data.md)), so `git clone`
gives you all of it:

| Folder | Contents |
|---|---|
| `data/raw/` | the four sample drawings |
| `data/client_set/` | the client's full dataset: ~1,170 drawings, **`Check List.docx`**, **`WP Specific Guidelines/`**, the template |
| `data/baseline/` | notebook 01/02 outputs (regression tests and `--from-baseline` use them) |
| `data/labels/` | answer keys (`title_block_truth.json` is still a **draft**; `symbol_counts.json` is **not counted yet**) |
| `data/cache/` | saved model replies, which make identical requests free |

**API keys are never in git.** Get them from Binjie privately.

---

## 2. Setup (Windows, macOS, Linux)

1. Install uv once: `winget install astral-sh.uv` on Windows, or `brew install uv` on macOS.
2. Clone and install:
   ```bash
   git clone https://github.com/ted-cc6/drawing-intelligence.git
   cd drawing-intelligence
   uv sync                        # Python 3.13 + exact locked dependencies in .venv
   ```
3. Create your `.env`:
   - `Copy-Item .env.example .env` (PowerShell) or `cp .env.example .env` (macOS/Linux)
   - paste in `OPENAI_API_KEY` and `QWEN_API_KEY` from Binjie
   - set **`DI_RETENTION=keep`**, so your dev runs are cached and kept
4. **VS Code:** open the folder and accept the recommended extensions (Python, Ruff). The interpreter is `.venv`.
5. **Optional:** `uv run pre-commit install`, so checks run on every commit.

---

## 3. How to run each module

| Command | What it does | Cost |
|---|---|---|
| `uv run pytest` | All 77 tests: synthetic PDFs, fake model, and the real samples against the notebook baseline | $0 |
| `uv run pytest -m regression` | Only the real-sample regression tests | $0 |
| `uv run ruff check . ; uv run ruff format --check . ; uv run pyright` | Lint, format and type checks (CI runs the same) | $0 |
| `uv run di models` | Registered models, prices, thinking options, whether your keys are set | $0 |
| `uv run di extract "data/raw/10K_CAM PLATE.pdf"` | Stage 1 only: counts, chain-sum table, warnings | $0 |
| `uv run di extract "data/raw/10K_CAM PLATE.pdf" --export data/exports` | Same, plus annotated images | $0 |
| `uv run di run "data/raw/10K_CAM PLATE.pdf" --model qwen3-vl-plus --thinking off` | Intake → understand. **Real API call**, unless the reply is in the cache. | ~$0.01 (Qwen-VL) |
| `uv run di eval baseline` | Extraction against the notebook's outputs, section by section | $0 |
| `uv run di eval understand --from-baseline` | Re-scores the notebook's **saved** answers from 30 Sep | $0 |
| `uv run di eval understand --model qwen3.8-max` | Live scorecard on the 4 samples; shows an estimate and **asks before calling** | ~$0.50 (estimate) |
| `uv run di telemetry` | Average cost and latency per model, thinking option and node | $0 |

**Cost and latency numbers** always come from token counts × the prices in `config/models.yaml`. A reply
served from the cache shows its original cost, but telemetry records $0 billed for it.

---

## 4. Team rules

- **Branches:** one per task (`feat/a4-consistency-reviewer`, …), branched from `main`.
- **Pull requests:** into `main`. CI must be green on all three OSes and Binjie approves. **Squash merge.**
- **Before asking for review:** `uv run pytest`, ruff and pyright all pass locally.
- **Models during development:**
  - Use **Qwen** (`qwen3-vl-plus`, `qwen3.8-max`).
  - **Never call `gpt-6-astra` without asking Binjie.** It costs about 50× more per drawing than `qwen3-vl-plus`.
  - Unit tests use fake models; tests that make paid calls must be marked `@pytest.mark.live`.
- **Claude Code is welcome.** `CLAUDE.md` gives it the rules. You are responsible for what it writes, so
  review its diff like anyone else's.
- **Merge conflicts in `data/telemetry.db` or `data/sessions/`:** these change on every machine. They're only
  history, so keep either side: `git checkout --theirs data/telemetry.db`.
- **Never edit `data/baseline/` or `data/labels/`** unless that is your task (A1 verifies the labels).
- **Decisions:** anything a new teammate would find surprising gets a short ADR in `docs/adr/`.

---

## 5. Next phase: who builds what

The client's rulebook (what to check on a drawing) **has not arrived yet**. So this phase builds everything
around it: data contracts, a code-only reviewer, a verifier, an evaluation set and the report. When the rules
arrive they slot in as data.

### Order of work

```
Day 1-2:  Binjie   A2 contracts (PR, reviewed by Mushahid and Zhetao)
          Zhetao   A1 model evaluation        (does not need A2)
          Mushahid A5a planted-error drawings (does not need A2)
After A2 is merged, in parallel:
          Mushahid A4 consistency reviewer → A3 verifier → R draft rulebook
          Zhetao   A5b di eval review
          Binjie   A6 graph fan-out + report; reviews every PR
```

### Definition of done (every task)
- code with **unit tests on synthetic data**
- a `di` command where it makes sense
- **CI green** on Windows, macOS and Linux
- `docs/PROJECT.md` updated if the design changes
- an ADR for any decision

---

### A2 · Review data contracts, Binjie (first; blocks A3, A4, A5b, A6)

**Goal:** the shared types that every reviewer, the verifier, the eval and the report use.

**Where:** `src/drawing_intelligence/schemas/review.py`

**Proposed shape (final fields decided in the PR):**
- **`Finding`**, built on the client's checklist columns (`data/client_set/Check List.docx`):
  - `id`
  - `category`: title block, material, tolerance, GD&T, datum, thread/weld, surface finish / coating / heat
    treatment, inspection, consistency
  - `requirement`
  - `result`: pass | fail | warning
  - `severity`: provisional levels until the client confirms
  - `evidence`: page, dimension IDs, bbox, quoted text, `rule_id`
  - `comment`, `recommended_correction`
  - `reviewer`, `source`: code | llm
- **`Rule`**, one per entry in `config/rules/*.yaml`:
  - `id`, `category`, `requirement`, `severity`
  - `check_type`: code | lookup | llm
  - `applies_to`, `params`
  - `source`: document and section
  - `status`: draft | client_confirmed

**Done when:** schemas, a rulebook loader with validation, tests, and **both teammates have reviewed and
approved the PR**.

---

### A1 · Choosing the understanding model, Zhetao (starts now)

**Goal:** choose the default model for stage 2 from evidence, not price.

**Steps:**
1. **Verify the labels.** Check every field in `data/labels/title_block_truth.json` against the PDFs, fix
   anything wrong, and set `_verified: true`. Count the symbols for `data/labels/symbol_counts.json`; ask
   Mushahid to check the engineering symbols.
2. **Add stability (criterion 6):**
   - Add `--runs N` to `di eval understand`, and report whether the title block and dimension count are
     identical across runs.
   - ⚠ **The cache returns the same reply for the same request**, so runs 2 and 3 would be cache hits. Add a
     way to bypass the cache for repeated runs (e.g. put the run number in the cache key, or a `--no-cache`
     flag).
3. **Round 1** (one run per setting): `qwen3.8-max` and `qwen3-vl-plus`, each with thinking `off` and `on`,
   on the 4 samples. That's 16 calls, about $1–2. **Show Binjie the results before round 2.**
4. **Round 2:** 3 runs per setting, for stability.
5. **Reference without spending money:** `gpt-6-astra` results come from
   `di eval understand --from-baseline`.
6. **Budget cap: $5 in total.** Check `di telemetry` as you go.

**Done when:**
- labels are verified
- `--runs` and stability scoring are in the code, with tests
- **ADR 0008** names the default understanding model and thinking setting, with the scorecard numbers
- `config/models.yaml` `defaults.understand` is updated

---

### A5a · Planted-error drawings, Mushahid (starts now)

**Goal:** an evaluation set of drawings with **known mistakes**. The client has no drawings with labelled
errors, so we make our own.

**Steps:**
1. Copy the four samples and plant realistic errors, at least 15 across categories:
   - a chain that doesn't add up
   - two different values for the same feature
   - an empty or wrong title-block field (material, surface treatment)
   - an impossible or contradictory tolerance
   - a heat-treatment note that contradicts the material
   - a missing dimension
2. Make them with a **script** so the set can be rebuilt, e.g. PyMuPDF to redact and re-insert text.
   **Where:** `src/drawing_intelligence/eval/seed.py`, outputs in `data/eval/seeded/<case>/`.
3. Write an **answer key** per case: `expected_findings.json` with category, location (page, dimension IDs or
   bbox) and a short description. Write the key before any reviewer exists, and don't change it to fit what a
   reviewer finds.

**Done when:** the script, ≥ 15 cases with answer keys, and a short README in `data/eval/seeded/` listing the
cases.

---

### A4 · Consistency reviewer, Mushahid (after A2)

**Goal:** the first real reviewer. **Code only, no LLM, $0 per drawing.** Its checks are true for any drawing,
whatever the client's rules turn out to be.

**Where:** `src/drawing_intelligence/review/consistency.py`, with its rules in `config/rules/consistency.yaml`
(`check_type: code`).

**Checks to build (input `Extraction` + `DrawingKnowledge`, output `Finding`s):**
- chain-sum mismatches (already computed in `chain_checks`; turn them into findings)
- the same feature dimensioned twice with different values
- dimensions with no matched dimension line (warning)
- empty or placeholder title-block fields
- tolerances outside the general tolerance table (`general_tolerances`), flagged for review
- reference dimensions that contradict the dimensions they summarise

**Done when:** each check has unit tests on synthetic sheets (see `tests/conftest.py` for how to draw one), and
it catches the matching planted errors from A5a.

### A3 · Verifier, Mushahid (after A4)

**Goal:** no finding reaches the report unless its evidence exists.

**Where:** `src/drawing_intelligence/review/verify.py`

**Checks:**
- every cited dimension ID exists on that page
- every bbox lies within the sheet
- every `rule_id` exists in the rulebook

Findings that fail are **dropped, with a reason** that is kept for debugging. Duplicates (same rule, same
evidence) are merged.

**Done when:** tests cover each rejection reason and duplicate merging.

### R · Draft rulebook, Mushahid (after A3)

**Goal:** give the client something to **correct** rather than write from scratch.

**Sources:**
- `data/client_set/Check List.docx`
- `data/client_set/WP Specific Guidelines/`: material selection, plating process selection, raw-material
  sizes, US–India material equivalents

**Output:** `config/rules/*.yaml` in the A2 `Rule` format. Every rule has `status: draft` and a `source`
pointing to the document and section. Binjie sends it to LatentView.

---

### A5b · `di eval review`, Zhetao (after A2 and the first A5a cases)

**Goal:** measure how good the review is.

**Where:** `src/drawing_intelligence/eval/review_eval.py` and a `di eval review` command.

**Steps:**
1. Run the review on every planted-error case and match findings to the answer key. Define the matching rule
   (same category plus overlapping evidence) and write it in the docstring.
2. Report:
   - **recall**: planted errors caught
   - **precision**: findings that are real
   - both per category and per reviewer
   - cost and latency, from telemetry
3. Run on the **unmodified** samples too: every finding there is a false alarm or a real issue, and a human
   should check them.

**Done when:** the command, tests with a fake reviewer, and a first results table (consistency reviewer only)
in `docs/PROJECT.md`.

---

### A6 · Graph fan-out and report, Binjie (after A2)

**Goal:** a complete review run from PDF to report.

**Steps:**
1. Add LangGraph nodes after `understand`:
   - fan-out to the reviewers in parallel
   - **verify** (A3)
   - **report**
   Reviewers that don't exist yet are skipped.
2. **Report:**
   - an **Excel sheet in the client's checklist columns**: Check Category, Requirement, Pass/Fail, Severity,
     Comment, Drawing Location, Recommended Correction
   - an **annotated sheet image** with each finding marked
3. A CLI command, e.g. `di review <pdf> --export DIR`.

**Done when:** an end-to-end run on the 4 samples produces the Excel report and image, with tests using a fake
model.

---

## 6. Backlog (no owner yet; pick one up if you finish early)

- **A7 · Q&A agent:** read-only tools over a session's JSON (`get_title_block`, `find_dimensions`,
  `get_findings`, …); answers must cite dimension IDs.
- **A8 · Hardening**, from the code review:
  - `llm/client.py` imports from a private OpenAI SDK module (`openai.lib._pydantic`)
  - a `Session` closed without a status is recorded as `"running"`
  - `DI_RETENTION=keep` sessions are never swept, so `data/sessions/` keeps growing
  - `di eval understand --from-baseline` re-extracts each PDF once per provider
  - prompt injection: PDF text goes into the prompt as-is
  - missing tests: `remap_text`, bad template coordinates (`_resolve`), slow or refused API replies
  - a **smoke test on `data/client_set/`**: mostly A2-size, some multi-page; catch crashes and title-block crop
    problems
- **Standards, manufacturability and design-intent reviewers:** once the client confirms the rules.
- **API + dashboard:** model picker per role, cost and latency display ([PROJECT.md §7](../PROJECT.md)). Not
  this phase.

Questions → Binjie.
