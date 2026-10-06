# Drawing Intelligence: project document

*UChicago MS in Applied Data Science capstone · LatentView Analytics · client: PARI Robotics.
Living document; last updated 2026-10-06.*

## 1. Problem

Before a machined part goes into production, an engineer checks its 2D drawing by hand: conflicting
dimensions, infeasible tolerances, missing specifications, title-block errors, non-standard callouts. This
"last point check" is slow and depends on individual experience; mistakes that slip through cause scrap,
rework and delays.

## 2. Goal

An AI workflow that takes a PDF drawing and, in a few minutes and for about a dollar:

1. **Extracts** every dimension, tolerance, note and title-block field exactly.
2. **Understands** the drawing: views, features, which dimension describes which feature, and the symbols
   the PDF text cannot see (GD&T frames, surface-finish marks, weld symbols).
3. **Reviews** it against engineering rules and judgement, and flags issues with severity, evidence and a
   recommended correction.
4. **Answers** an engineer's questions about the drawing, citing evidence.
5. **Reports** the review in a format an engineer can act on.

Success means an engineer trusts the review enough to use it as a first pass, because every finding points
at evidence on the drawing.

## 3. Inputs

- **Drawings:** native vector PDFs (with a text layer) on the Wipro PARI template (FR-DES-006-01). Today:
  four sample drawings. Future drawings come in the same format. The client's larger set (~1,170 drawings
  of prismatic and round parts) is mostly A2 and sometimes multi-page; extraction is built to handle both
  (template regions anchored to sheet edges, every page processed).
- **Review knowledge (for the review stage):** the client's *Check List* (title block, material naming,
  tolerance standards, GD&T, datum schemes, thread/weld callouts, surface finish / coating / heat
  treatment, inspection requirements, common rejection conditions) and the *WP Specific Guidelines*
  (material selection, plating process selection, raw-material sizes, US–India material equivalents).

## 4. Architecture

A **fixed workflow** for the review path plus **one agent** for Q&A. This is not a single agent that
calls every tool, and not a team of agents talking to each other (see [ADR 0001](adr/0001-workflow-plus-qa-agent.md)).

```
                ┌────────────────────── REVIEW WORKFLOW (LangGraph, fixed path) ──────────────────────┐
PDF ─► 1 Intake ─► 2 Understand ─► 3 Review (parallel) ─────────────────────────► 4 Verify ─► 5 Report
       code          1 vision call     a. Consistency          code                 code         findings
       $0            per page          b. Standards            rulebook + small LLM (citations   + evidence
                     ─► drawing        c. Manufacturability    reasoning LLM         checked,
                        JSON           d. Design intent        reasoning LLM         deduped)
                └─────────────────────────────────────────────────────────────────────────────────────┘
                                                                                              │
Engineer ◄──► Q&A agent: read-only tools over the session's saved results ◄───────────────────┘
```

| Stage | Kind | Why |
|---|---|---|
| 1 Intake | Deterministic code | The PDF text layer is exact. No LLM can improve on it, so none is paid for. |
| 2 Understand | One vision-LLM call per page | Organise and interpret the exact text (views, features, title block) and add only what text cannot see (symbols). Never re-read numbers from pixels. |
| 3a Consistency | Code | Chain sums and duplicate or missing dimensions have exact answers. |
| 3b Standards | Rulebook lookups + small LLM | IS 2102 and PARI rules are table lookups; the LLM only interprets notation. |
| 3c Manufacturability | Reasoning LLM | Needs machining judgement. |
| 3d Design intent | Reasoning LLM | Needs the whole part: material, heat treatment, fits, features. |
| 4 Verify | Code | Rejects any finding whose cited dimension ID, bbox or rule does not exist. This catches invented findings at no LLM cost. |
| 5 Report | Template + small LLM | Engineering review report. |
| Q&A | One agent with tools | Open-ended questions are the one place where an agent choosing its own steps earns its cost. It answers from saved JSON only, so it never pays for images again. |

Reviewers read the structured drawing JSON (text, cheap), not the images. Only stage 2 pays for vision.
The reviewers run in parallel, so they add little wall time.

### Data contracts

Every stage reads and writes typed, versioned Pydantic models (`src/drawing_intelligence/schemas/`):

- `Extraction` (stage 1): per page, the title-block / tolerance-table / body text with bboxes, the cleaned
  dimensions (ids `D1..Dn`), view labels, notes, chain-sum checks, and the image set sent to the LLM.
- `DrawingKnowledge` (stage 2): title block, views, dimensions (every `D` id kept unchanged; image-only ones
  get `V` ids and `source: "vision"`), features, symbols, notes, general tolerances, revisions, uncertain items.
- `Finding` (stage 3–4, planned): category, requirement, severity, evidence (dimension ids / bbox / rule id),
  recommended correction. These are the columns the client's checklist asks for.

### Hard rules

1. **Never invent.** Every value is traceable to the PDF text, or marked `source: "vision"`. Unknown → `null`.
2. **Evidence or it didn't happen.** Every review finding cites dimension ids, a bbox or a rule id; the
   verifier drops findings whose citations do not resolve.
3. **Client data is session-scoped** (section 6).

## 5. Models, cost and latency

- **Providers:** OpenAI and Alibaba Qwen, both called through the `openai` SDK (Qwen via its
  OpenAI-compatible endpoint) in our own thin `llm/` module ([ADR 0002](adr/0002-openai-sdk-direct.md)).
  LangGraph only orchestrates.
- **Model registry** ([`config/models.yaml`](../config/models.yaml), [ADR 0004](adr/0004-model-registry.md)):
  each model's provider, prices (with `verified_on` and source), capabilities, allowed roles, and its own
  thinking options. Today: `gpt-6-astra`, `qwen3.8-max`, `qwen3-vl-plus`.
- **Thinking is a per-role, per-run setting.** Thinking tokens were most of the cost in the notebook
  experiments. OpenAI's `gpt-6-astra` offers `low` / `medium` / `high` / `xhigh` (it cannot be switched off).
  Qwen models offer `off` / `on`.
- **Every LLM call is recorded** in the persistent telemetry database: session, node, provider, model,
  thinking level, input/output tokens, cost, latency, cache hit, status. **No drawing content.**
- **Budget:** a full review should take a few minutes and cost about $1 per drawing. Stage 2 alone measured
  ~80–160 s and $0.01–$0.58 per drawing in the notebook experiments, depending on the model.

## 6. Data retention and privacy ([ADR 0003](adr/0003-session-scoped-data.md))

| Data | Where | Lifetime |
|---|---|---|
| PDF, images, `extraction.json`, drawing JSON, findings, Q&A history, LangGraph checkpoints, LLM cache | the session workspace `data/sessions/<id>/` (its own SQLite file) | **deleted when the session ends**; leftovers from crashes are swept at the next start |
| Telemetry (session id, node, model, tokens, cost, latency, status) | `data/telemetry.db` | persistent; no file names, drawing numbers or text |
| Engineer feedback (planned): rule id, finding category, severity, accepted/rejected, model | `data/telemetry.db` | persistent; no drawing content |

`DI_RETENTION=ephemeral` is the default. `DI_RETENTION=keep` is for development only: it keeps workspaces
and a response cache so repeated runs on the samples do not pay twice. OpenAI requests are sent with
`store=false`. Provider-side retention for abuse monitoring depends on each provider's account policy and is
outside this code's control.

SQLite fits a local tool or a single server. A hosted multi-user deployment would move telemetry to Postgres
behind the same `storage/` interface.

## 7. Future dashboard (not built yet)

A web front end over the same package, via a thin API (e.g. FastAPI):

- **Upload** a drawing → runs the workflow in a fresh session → shows the annotated sheet, the review
  findings (filterable by severity and category, each linked to its location on the sheet) and a Q&A panel.
- **Model picker per role** (understand, review, Q&A), populated from `config/models.yaml`, with each
  model's **thinking options** as a second dropdown. This is the same choice as the CLI's `--model` /
  `--thinking`.
- **Cost and latency, live and historical:**
  - per run: cost and wall time per node and in total, tokens in/out, cache hits
  - per model: average cost, latency and quality score from `di eval`, so users can see the trade-off
    before picking
- **Feedback buttons** on each finding (accept / reject), written to the feedback log.
- **End session** button (and an idle timeout) that deletes the session workspace.

Everything the dashboard needs already exists in the package API and the telemetry database; the dashboard
adds no new logic.

## 8. Evaluation

No labelled error drawings exist yet, so evaluation is built from what is available:

- **Baseline diff** (`di eval baseline`): compares new extraction outputs with the original notebooks'
  outputs and lists every difference, so each change is explained instead of forbidden.
- **Understanding scorecard** (`di eval understand`), ported from the notebook:
  1. valid JSON that matches the schema
  2. title-block accuracy against `labels/title_block_truth.json`
  3. every extracted dimension returned unchanged
  4. no invented numbers
  7. time and cost per drawing
- **Review (planned):** drawings with **seeded errors** (known mistakes planted in copies of the samples),
  then the engineer feedback log as it grows.

### Results at M1 (2026-10-06)

- **Extraction:** identical to the original notebook on all four samples, in every section
  (`di eval baseline`).
- **Scorecard on the notebook's saved outputs** (`di eval understand --from-baseline`): every model
  returned 81/81 dimensions unchanged with 0 invented numbers. Title block: 100 % for Gemini and
  `gpt-6-astra`, 93–100 % for `qwen3-vl-plus` (the same two misses the notebook found). The new strict
  schema also rejects one `qwen3-vl-plus` output for inventing feature types (e.g. `"distance"`).
- **First live run in the package** (`qwen3-vl-plus`, thinking off, 10K Cam Plate): valid, 21/21 dimensions,
  no symbols reported (the notebook run reported 6, which were not on the drawing), 69 s, $0.011.
- Not yet measured: `qwen3.8-max` and `gpt-6-astra` through the package, thinking on vs off, stability
  over repeated runs.

## 9. Roadmap

| Milestone | Content | Status |
|---|---|---|
| M0 | Repo, tooling, CI on Windows/macOS/Linux, docs and ADRs | ✅ |
| M1 | Notebooks 01/02 ported and upgraded: typed contracts, multi-page, template config, model registry, telemetry, session data, LangGraph intake → understand, CLI, eval | ✅ |
| M2 | Rulebook from the client checklist and guidelines; consistency + standards reviewers; verifier | next |
| M3 | Manufacturability + design-intent reviewers; seeded-error eval set; report | |
| M4 | Q&A agent; feedback log | |
| M5 | API + dashboard (model picker, cost and latency) | |

## 10. Open questions

- Who writes the first rulebook entries: PARI engineers, or the team from IS 2102 and machining handbooks?
- Which model wins each role? Decided by `di eval` on the samples, not by public benchmarks.
- Confirm `qwen3.8-max` pricing on Alibaba's official page (the registry uses a third-party figure).
