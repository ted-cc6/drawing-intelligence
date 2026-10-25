# Drawing Intelligence: project document

*UChicago MS in Applied Data Science capstone · Client: LatentView Analytics · Living document; last updated 2026-10-23.*

## 1. Problem

Before a machined part goes into production, an engineer checks its 2D drawing by hand: conflicting
dimensions, infeasible tolerances, missing specifications, title-block errors, non-standard callouts. This
"last point check" is slow and depends on individual experience; mistakes that slip through cause scrap,
rework and delays.

## 2. Goal

An AI workflow that takes a PDF drawing and, in a few minutes and for about a dollar:

1. **Extracts** every dimension, tolerance, note and title-block field exactly.
2. **Understands** the drawing: views, features, and which dimension describes which feature. Symbols come
   from the PDF itself where possible: GD&T frames from the symbol font in the text layer, datum flags and
   finish marks from vector geometry ([Spike D](spikes/spike_d_symbols.md)).
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
  These, LatentView's *Drawing Check Rulebook* and six engineering books were drafted into **174 rules** in
  `config/rules/` (task R, all `status: draft` until PARI confirms; triage in `docs/rulebook/`).

## 4. Architecture

A **fixed workflow** for the review path plus **one agent** for Q&A. This is not a single agent that
calls every tool, and not a team of agents talking to each other (see [ADR 0001](adr/0001-workflow-plus-qa-agent.md)).

```
                ┌────────────────────── REVIEW WORKFLOW (LangGraph, fixed path) ──────────────────────┐
PDF ─► 1 Intake ─► 2 Understand ─► 3 Review (parallel) ─────────────────────────► 4 Verify ─► 5 Report
       code          1 vision call     checks             code + lookup rules    code         Excel +
       text,         per page          drawing_practice   ┐                      (citations   annotated
       vectors,      ─► drawing        manufacturability  ├ LLM rules,           resolve,     sheet
       symbols       JSON              design_intent      ┘ warnings only        deduped,
       $0                                                                        rule status)
                └─────────────────────────────────────────────────────────────────────────────────────┘
                                                                                              │
Engineer ◄──► Q&A agent: read-only tools over the session's saved results ◄───────────────────┘
```

| Stage | Kind | Why |
|---|---|---|
| 1 Intake | Deterministic code | The PDF text layer is exact. No LLM can improve on it, so none is paid for. Symbols are read here too (Spike D): GD&T frames decoded exactly from the `SolidEdgeANSI1Symbols` font, datum flags and finish marks from vector detectors (`extraction/symbols.py`; 80/80 on the reviewed answer key). |
| 2 Understand | One vision-LLM call per page | Organise and interpret the exact text: views, features, which dimension belongs to which feature, title block. Never re-read numbers from pixels. Spike D: vision misses most symbols (0/32 finish marks, 0/9 datum flags), so anything only vision sees is `source: "vision"` and can only support a warning. |
| 3 `checks` | Code | Every `code` and `lookup` rule (135 of 174): chain sums, duplicates, title-block fields, IS 2102 and PARI tables. Exact, $0, reproducible. |
| 3 LLM reviewers | Reasoning LLM, one text-only call each | `drawing_practice`, `manufacturability`, `design_intent` run the 39 `llm` rules that need judgement. Spike E: high recall but 32–61% precision, so their findings are warnings only (ADR 0008). |
| 4 Verify | Code | Rejects any finding whose cited dimension ID, bbox or rule does not exist. This catches invented findings at no LLM cost. Merges duplicates and sets each rule's status. |
| 5 Report | Code | `review_report.xlsx`: a summary, the checklist in the client's columns (Check Category, Requirement, Pass/Fail, Severity, Comment, Drawing Location, Recommended Correction) with numbered findings then passed rules, and every rule not checked with its reason. `page_N_review.png`: the sheet with each finding boxed and numbered like its row (red fail, orange warning). Locations name the sheet zone (e.g. C4), read from the border markers. |
| Q&A | One agent with tools | Open-ended questions are the one place where an agent choosing its own steps earns its cost. It answers from saved JSON only, so it never pays for images again. |

Reviewers read the structured drawing JSON (text, cheap), not the images. Only stage 2 pays for vision.
The reviewers run in parallel, so they add little wall time.

### Data contracts

Every stage reads and writes typed, versioned Pydantic models (`src/drawing_intelligence/schemas/`):

- `Extraction` (stage 1): per page, the title-block / tolerance-table / body text with bboxes, the cleaned
  dimensions (ids `D1..Dn`), view labels, notes, chain-sum checks, and the image set sent to the LLM.
- `DrawingKnowledge` (stage 2): title block, views, dimensions (every `D` id kept unchanged; image-only ones
  get `V` ids and `source: "vision"`), features, symbols, notes, general tolerances, revisions, uncertain items.
- `Finding` (stages 3–4, `schemas/review.py`): an issue in the client's checklist columns. It has a category,
  requirement, result (`fail` | `warning`), severity, evidence, comment and recommended correction, plus the
  reviewer and source (`code` | `lookup` | `llm`). Each evidence item (`EvidenceRef`) points at a dimension,
  symbol, note, title-block field, quoted text or region, and records where it was read: `pdf_text`, `vector`
  or `vision`. The ID is stable across runs (a hash of rule + evidence).
- `RuleStatus`: the per-rule outcome (`pass` | `fail` | `warning` | `not_applicable` | `not_checked`) for the
  report's Pass/Fail column. `ReviewResult` holds the whole review of one drawing, including the rulebook
  version and which reviewers ran or were skipped. `FindingFeedback` records an engineer's accept or reject.
- `Rule` (`config/rules/*.yaml`, loaded by `review.load_rulebook()`, checked by `di rules`): ID, category,
  requirement, severity, check type (`code` | `lookup` | `llm`), check function and params, applies-to (part
  family, drawing type), source document and section, and status (`draft` | `client_confirmed`).

### Review stage ([ADR 0010](adr/0010-review-stage-design.md))

How the rulebook is run. Reviewers are split by **how** a rule is checked, not by its category.

- **Check functions** (`review/checks/<category>.py`): one pure function per `check` name in the rulebook,
  registered with its params model, so `di rules` validates every rule against it.
  - Signature: `fn(ctx, rule, params) -> list[Finding]`.
  - `ctx` is a read-only `ReviewContext`: the `Extraction`, the per-page `DrawingKnowledge` (or `None`), the
    rulebook and the reference tables.
  - Findings are made with `new_finding(rule, ...)`. An empty list means pass.
  - `raise NotApplicable` or `raise NotCheckable` for the other outcomes. Any other error becomes
    `not_checked`, and the review goes on.
  - `lookup` checks read their tables from `config/reference/*.yaml`.
- **Reviewers:**
  - `checks` runs every `code` and `lookup` rule.
  - `drawing_practice`, `manufacturability` and `design_intent` each make one LLM call over their `llm`
    rules (category → reviewer mapping in `review/reviewers.py`).
- **Graph:**
  - `understand` fans out to the reviewers, which join at `verify`, then `report`.
  - Each reviewer writes `review/<reviewer>.json` and appends its path to `reviewer_outputs`, a list that
    LangGraph adds to rather than overwrites.
  - A reviewer that isn't built, or can't run, is listed in `reviewers_skipped`, and its rules are
    `not_checked`.
- **Verify:**
  - drops findings whose evidence doesn't resolve, with the reason in `review/rejected.json`
  - merges duplicates by finding id
  - gives every rule one status: `fail` > `warning` > `not_applicable` / `not_checked` > `pass`
  - writes `review/review_result.json`, the only input to `report`

A rule whose check isn't built yet is `not_checked`, never `pass`, so the report shows how much of the rulebook
actually ran.

Two inputs the checks rely on:
- **Title-block fields come from stage 1**, read by position from the template's cells
  (`extraction/title_block.py`). Fails therefore rest on exact text. Variant title blocks (about 1 in 5 client
  sheets) are detected by their labels; nothing is read from them.
- **Drawn lengths** (dimension line ÷ value) tell which scales a sheet is drawn at. `conflicting_values` (CN-002)
  and `scale_consistent` (TB-006) use them.

### Hard rules

1. **Never invent.** Every value is traceable to the PDF text, or marked `source: "vision"`. Unknown → `null`.
2. **Evidence or it didn't happen.** Every review finding cites dimension ids, a bbox or a rule id; the
   verifier drops findings whose citations do not resolve.
3. **Client data is session-scoped** (section 6).
4. **Trust is enforced by the schema** ([ADR 0008](adr/0008-review-contracts-enforce-trust.md)): an LLM
   finding is at most a warning, severity comes from the rulebook, and a *fail* needs `pdf_text` or `vector`
   evidence.

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

Development data is different: the sample drawings, the client's full dataset and dev outputs are committed
to the public repo for easy sharing ([ADR 0007](adr/0007-commit-client-data.md)). API keys are never committed.

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
- **Review:** 28 drawings with **seeded errors** in `data/eval/seeded/` (A5a: 22 planted, 2 near-miss, 4
  clean; rebuilt by `di eval seed`), each with a hand-written answer key in rulebook rule ids. Scoring a review
  against them (`di eval review`, A5b) is next; then the engineer feedback log as it grows.

### Results at M1 (2026-10-06)

- **Extraction:** identical to the original notebook on all four samples, in every section
  (`di eval baseline`).
- **Scorecard on the notebook's saved outputs** (`di eval understand --from-baseline`): every model
  returned 81/81 dimensions unchanged with 0 invented numbers. Title block: 100 % for Gemini and
  `gpt-6-astra`, 93–100 % for `qwen3-vl-plus` (the same two misses the notebook found). The new strict
  schema also rejects one `qwen3-vl-plus` output for inventing feature types (e.g. `"distance"`).
- **First live run in the package** (`qwen3-vl-plus`, thinking off, 10K Cam Plate): valid, 21/21 dimensions,
  no symbols reported (the notebook run reported 6, which were not on the drawing), 69 s, $0.011.
- Not yet measured at M1: `qwen3.8-max` and `gpt-6-astra` through the package, thinking on vs off,
  stability over repeated runs. A1 measured the Qwen settings (2026-10-17). Every setting was stable over
  3 runs; `qwen3-vl-plus` with thinking off was as accurate as the others at a fraction of the cost and time,
  so it is now the default ([ADR 0009](adr/0009-understanding-model-default.md)).

### Results of the first review slice (2026-10-23)

`di eval review` on the 28 seeded cases, through the full graph: the `checks` reviewer with 17 check functions
(22 of 135 code/lookup rules) and two reference tables (`config/reference/`: materials, PARI DES-12 plating).

| | first 10 checks | + tolerance, heat treatment | + lookup tables (2026-10-25) |
|---|---|---|---|
| Recall, all 22 planted errors | 10/22 (45%) | 15/22 (68%) | **18/22 (82%)** |
| Recall, planted errors with a built check | 10/10 | 15/15 | 18/18 |
| Precision | 40/40 | 60/60 | 63/63 |
| False alarms on clean and near-miss drawings | 0 | 0 | 0 |

With understanding (`qwen3-vl-plus`, thinking off) the results are identical; none of these checks needs it yet
(CN-002 uses drawn lengths). A run takes ~110 s per drawing, nearly all understanding; the replies are cached in
`data/cache/`, so re-runs are free (re-caching after the prompt was restored to ADR 0009's cost $0.256; the four
clean cases hit A1's cache). Code checks alone take ~1 min for all 28.

| Category | Caught / planted |
|---|---|
| title block | 6/6 |
| consistency | 4/6 (P05, P06 need the `llm` missing-dimension rules) |
| tolerance | 3/3 |
| surface treatment | 5/5 |
| design intent, manufacturability | 0/1 each (LLM reviewers) |

### With the LLM reviewers (2026-10-25)

Understanding (`qwen3-vl-plus`, off) plus the three LLM reviewers (`qwen3.8-max`, thinking off), all 28 cases:

| | code checks only | + LLM reviewers |
|---|---|---|
| Recall, all 22 planted errors | 18/22 | **20/22 (91%)** |
| Recall, planted errors whose rule is checked | 18/18 | 20/20 |
| Precision, all findings | 63/63 | 78/89 (88%) |
| Precision, LLM findings | – | 15/26 (58%) |
| LLM warnings on clean and near-miss drawings (measured, not a gate) | – | 1 |
| False alarms of the code checks | 0 | 0 |
| Cost per drawing | $0 | ~$0.025 (understanding $0.011 + reviewers ~$0.015); cached re-runs $0 |

- Caught by the LLM reviewers: P19 (TL-002, the ⌀16 locating bore lost its fit) and P20 (MC-001, R 0.2 internal
  corner). Not caught: P05 and P06 (missing size and location). Their rules need feature locations, which the
  text-only reviewers don't get, so they are `not_checked` (`params.needs: [geometry]`).
- A first calibration (8 cases) had 25 false alarms in 26 LLM findings. Most were the template's own notes
  ("notes copied from another drawing") and rules about symbols the reviewers cannot see (roughness, GD&T,
  datums). Template boilerplate is now left out, and those rules are held back until stage 1 reads symbols.
- The reviewers also raised WPS-004 on every case with a zinc-plated H7 hole: I.Z.B.P. (8–12 µm) can take up
  the whole 18 µm H7 band. The PARI proxy confirmed it is real, so it was added to the keys as a pre-existing
  issue.
- The remaining LLM false alarms: MF-005 "heat-treatment stage not stated" (5, including Shore hardness on
  plastic parts), TL-002 calling clearance holes functional (2), NM-008 (2), WPS-004 where the fit or plating
  was changed (2).

- The 60 findings are 17 that catch a planted error (P01 and P02 each also raise the other chain rule, which
  their keys accept) and 43 real issues already in the client's drawings (the keys' `pre_existing`: TB-016 on
  every case, RQ-002 on the cylinder rod, LY-005 and MF-011 on the hose clamp, MF-013 on the pipe-clamp block).
- `tests/regression/test_review_eval.py` keeps this in CI: no false alarms, and at least 15 planted errors caught.

**On 200 client drawings (no answer key; an engineer should confirm):**
- TB-006 (scale) fails on 17 of 139 sheets with a readable title block. The examples look real (e.g. 11 dimensions
  drawn at 2:1 on a sheet stating 1:1).
- RQ-002 (inverted limits) fails on 4 of 13 sheets with stacked limits. A first version read the limits in the
  PDF's storage order and failed 13; stage 1 now orders them by where they are printed.
- LY-005 (decimals vs tolerance) failed on 91 of 195 sheets, mostly CAD-default trailing zeros such as `18.00`
  under a general tolerance of ±0.2. Until PARI decides, trailing zeros on untoleranced sizes are not counted
  (rule param `ignore_trailing_zeros_under_general`; an explicit `10.000±0.1` still fails). It still fails on 74
  sheets (313 findings): two-decimal sizes such as `15.21` under ±0.2, which the answer keys count as real
  (`34.97` under ±0.3). PARI should confirm that this is what they want flagged.
- TL-003 (much tighter than general) warns on 15 of 157 sheets, e.g. `40±0.01`. Its ratio (20x) is provisional.
- WPS-002 (treatment suits the material) fails on 3 of the 11 sheets it can compare, all IZBP on alloy steel (EN24,
  20MnCr5). DES-12's material column lists IZBP for mild and carbon steel only, but its text says "for ferrous
  machined parts": PARI should say which holds. Most sheets print `#` for the material, so they are not compared.

### Held-out validation on unseen client drawings (2026-10-25)

The seeded set's precision is optimistic: the checks and the LLM reviewers were tuned on it. `di eval heldout`
reviewed 25 client drawings no development step had looked at (24 drawings and one guideline PDF), and every one of
the 115 findings was labelled (by Claude from the drawings, confirmed by the PARI proxy on 2026-10-25). Details and labels: `data/eval/heldout/2026-10-25/`.

| | correct | incorrect | unsure | precision |
|---|---|---|---|---|
| Code checks and lookups | 58 | 0 | 2 | **100%** |
| LLM reviewers | 14 | 25 | 16 | **36%** (seeded set: 58%) |

- Most LLM noise is NM-008 "notes copied from another drawing" (11 of 12 wrong: PARI's standard and bilingual
  notes) and MF-007 "material suits the function" (4 of 5 wrong). Without them: 55%.
- PARI writes `#` in title-block fields to mean "see the notes" (`# MATERIAL: M.S`). Reading that block would let
  the material and treatment lookups check most of the client set; today they skip it.
- Cost ~$0.036 and ~2 minutes per drawing for the full review.
- **After three fixes** (read the `#` notes block; hold back NM-008; MF-007 only on a stated conflict), the same 24
  drawings: code 58 correct, 0 incorrect, 8 unsure; LLM 17 correct, 13 incorrect, 11 unsure: **57%** (was 36%).
  On the seeded set the re-run `design_intent` reviewer missed P19 (it raised a plating warning on that hole
  instead), so recall is 19/22: the LLM catch of P19 is not stable from run to run (Spike E: ~40% stability).
- **After narrowing WPS-004** to fits and tight bands: LLM 15 correct, 2 incorrect, 11 unsure on the same drawings
  (88% of decided; seeded precision 77/81). These 24 drawings have now guided three rounds of fixes, so the figure
  is optimistic until a fresh unseen set confirms it.
- **Symbols given to the LLM reviewers** (the 8 rules held back for `needs: symbols` released): the 14 new findings
  had none confirmed (0 correct, 3 incorrect, 11 unsure) and LLM precision fell to 57%. These rules need to know
  which faces mate, seal or rotate, which a list of symbols does not say, so they are held back again
  (`needs: [symbols, functional_faces]`); the reviewer messages are back to the 88% run's, cached ($0 to re-run).

## 9. Roadmap

| Milestone | Content | Status |
|---|---|---|
| M0 | Repo, tooling, CI on Windows/macOS/Linux, docs and ADRs | ✅ |
| M1 | Notebooks 01/02 ported and upgraded: typed contracts, multi-page, template config, model registry, telemetry, session data, LangGraph intake → understand, CLI, eval | ✅ |
| M2 | Review contracts and rulebook loader (A2 ✅); default understanding model (A1 ✅, ADR 0009); draft rulebook, 174 rules (R ✅); review-stage design (ADR 0010 ✅, proposed); title-block fields in stage 1 ✅; `checks` reviewer with 39 check functions (A4, in progress: 44 of 135 code/lookup rules built); general tolerance table and stacked limits in stage 1 ✅; verifier (A3 ✅); reference tables and the first lookup checks ✅ (materials, DES-12 plating); next: symbols from text and vectors in stage 1 ✅ (Spike D) with 6 GD&T and datum checks; next: open the `needs: symbols` LLM rules, more lookup tables (DES-11 heat treatment, raw-material sizes) | in progress |
| M3 | LLM reviewers (`drawing_practice`, `manufacturability`, `design_intent`) ✅; seeded-error eval set (drawings and keys: A5a ✅; `di eval review`: A5b ✅); graph fan-out (A6 part 1 ✅) and report (Excel + annotated sheet, A6 ✅); next: held-out validation on real client drawings, labelled by an engineer through the report | in progress |
| M4 | Q&A agent; feedback log | |
| M5 | API + dashboard (model picker, cost and latency) | |

## 10. Open questions

- ~~Who writes the first rulebook entries?~~ The team drafted 174 rules (task R). Open now: who at PARI
  confirms them (`status: client_confirmed`), and the 49 `needs_pari` decisions in `docs/rulebook/`.
- Which model wins each role? Understanding: decided (`qwen3-vl-plus`, thinking off, ADR 0009). Review and
  Q&A: still open, decided by `di eval review` (A5b), not by public benchmarks.
- ~~Should an `llm` rule with no finding be `pass` or `not_checked`?~~ `not_checked` (2026-10-25).
- Feature locations for the LLM reviewers (P05/P06, missing dimensions): view and feature bboxes in the
  understanding output are a prompt and schema change, to measure against ADR 0009 first.
- Confirm `qwen3.8-max` pricing on Alibaba's official page (the registry uses a third-party figure).
