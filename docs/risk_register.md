# Risk Register

- **Project:** Drawing Intelligence — agentic review of 2D engineering drawings
- **Status:** Living document — review at the end of every phase
- **Created:** 2026-10-13 (Phase 0)
- **Last updated:** 2026-10-13

---

## 1. How to Read This Register

Each risk is written as **cause → event → impact**: *Because [cause], [event] may happen, which would [impact].*
Jobs (`J…`), stories (`US-…`), metrics (`M…`), decisions (`D…`), open items (`O…`) and spikes refer to
[`01_discovery.md`](01_discovery.md).

| Field | Meaning |
|---|---|
| **Likelihood (L)** | 1 = rare, 2 = unlikely, 3 = possible, 4 = likely, 5 = almost certain or already observed |
| **Impact (I)** | 1 = negligible, 2 = minor, 3 = one job degraded, 4 = several jobs or a success metric at risk, 5 = project failure, a client confidentiality breach or a wrong part released |
| **Score** | L × I. ≥ 15 = high, 8–14 = medium, ≤ 7 = low |
| **Strategy** | Avoid (change the design so the risk disappears), Reduce (lower likelihood or impact), Transfer (hand it to someone else), Accept (live with it) |
| **Trigger** | The early warning sign that the risk is turning into an issue |
| **Contingency** | Plan B if the risk occurs |
| **Status** | Open, Mitigated, Occurred, Closed |

Risks were identified with a pre-mortem ("at the final presentation, PARI says they won't use it — why?") and
checked against these categories: users and requirements, external dependency, data, AI quality, security and
confidentiality, scope and schedule, cost.

---

## 2. Summary (sorted by score)

| ID | Risk | Category | L | I | Score | Strategy | Phase | Status |
|---|---|---|---|---|---|---|---|---|
| R1 | Requirements come from a proxy, not from PARI | Users & requirements | 4 | 4 | **16** | Reduce | 0, 1 | Open |
| R2 | The client rulebook arrives late or never | External dependency | 4 | 4 | **16** | Reduce | 1–3 | Open |
| R3 | Too many false alarms; checkers stop reading | AI quality | 4 | 4 | **16** | Reduce | 2–4 | Open |
| R4 | Wrong findings with valid citations pass the verifier | AI quality | 4 | 4 | **16** | Reduce | 2–4 | Open |
| R9 | Client drawings in a public repository | Security & confidentiality | 3 | 5 | **15** | Reduce | 0 | Open |
| R5 | Vision model invents or misses symbols | AI quality | 5 | 3 | 15 | Avoid | 1–3 | Mitigation chosen |
| R7 | Round-part features are handled worse than prismatic ones | Data / AI quality | 3 | 4 | 12 | Reduce | 1–3 | Open |
| R8 | Planted errors are unrealistic, so metrics overstate quality | Data | 4 | 3 | 12 | Reduce | 2 | Open |
| R19 | Title-block variants and placeholder values cause wrong or noisy title-block findings | Data / AI quality | 4 | 3 | 12 | Reduce | 1–2 | Open |
| R13 | Findings change from run to run | AI quality | 4 | 3 | 12 | Reduce + Accept | 2–4 | Open |
| R14 | Scope exceeds the capstone timeline | Scope & schedule | 4 | 3 | 12 | Reduce | all | Open |
| R10 | Providers retain or process drawings outside PARI's rules | Security & confidentiality | 2 | 5 | 10 | Reduce | 1 | Open |
| R11 | Cost per drawing exceeds $1 | Cost | 3 | 3 | 9 | Reduce | 2–4 | Open |
| R16 | Q&A agent answers beyond the stored results | AI quality | 3 | 3 | 9 | Reduce | 4 | Open |
| R6 | Template variations break extraction | Data | 2 | 4 | 8 | Reduce | 1 | Open |
| R17 | Development runs delete or change committed data | Data | 4 | 2 | 8 | Reduce | all | Occurred |
| R18 | Qwen endpoint is no longer supported for the US region | External dependency | 4 | 2 | 8 | Reduce | 1 | Open |
| R12 | Text inside a drawing changes review behaviour | Security | 2 | 3 | 6 | Avoid + Reduce | 2–4 | Open |
| R15 | Model prices change or a model is retired | External dependency | 3 | 2 | 6 | Reduce | all | Open |

---

## 3. Risk Details

### R1 · Requirements come from a proxy, not from PARI

- **Risk:** Because no PARI checker has been interviewed and Binjie acts as the PARI proxy (D11), the jobs,
  severity scale and metric targets may not match how PARI really checks drawings, which would produce a tool
  that passes its own tests but that PARI does not use.
- **Category:** Users & requirements · **L** 4 · **I** 4 · **Score** 16
- **Strategy:** Reduce
- **Mitigation:** Confidence tags on every job (§1.2 of the discovery document); Spike A; ask LatentView for one
  `[30]`-minute session with a PARI checker, or for written comments on the discovery document.
- **Trigger:** By the end of Phase 1, no PARI or LatentView feedback on the discovery document.
- **Contingency:** Treat every [A]-tagged job as *Could* in MoSCoW; focus on J2, J3, J7, J8 and J10, which rest on
  the client's own documents or on exact checks.
- **Phase:** 0, 1 · **Status:** Open

### R2 · The client rulebook arrives late or never

- **Risk:** Because the client's rules for what to check have not arrived, the standards reviewer (J4) may have
  nothing confirmed to check against, which would leave a whole category *not checked* and lower M1.
- **Evidence:** The Oct 06 update records that the rulebook has not arrived; `Check List.docx` lists only the
  categories and report columns, not the rules.
- **Category:** External dependency · **L** 4 · **I** 4 · **Score** 16
- **Strategy:** Reduce
- **Mitigation:** Spike B: the team drafts rules from `Check List.docx` and the WP guidelines with
  `status: draft` and a source for each, and sends them to PARI to correct rather than write (O3).
- **Trigger:** No PARI corrections to the draft rulebook `[2]` weeks after it is sent.
- **Contingency:** Ship with draft rules clearly marked in the report (US-13.2); evaluate standards findings only
  against planted errors that follow the draft rules.
- **Phase:** 1–3 · **Status:** Open

### R3 · Too many false alarms; checkers stop reading

- **Risk:** Because LLM reviewers tend to over-report and checkers have little time, a review with many false
  alarms may be ignored after a few uses, which would defeat J1 and M5 even if recall is high.
- **Category:** AI quality · **L** 4 · **I** 4 · **Score** 16
- **Strategy:** Reduce
- **Evidence (Spike E, 2026-10-13):** thinking-off qwen3.8-max raised ~3.2 findings per drawing; deduplicated
  precision 32% (strict) – 61% (lenient). Biggest false themes: "tolerance too tight" with no rule (6),
  material/treatment speculation (5), standard M6/M8 clearance holes called non-standard (2). The offline
  trigger (precision < 70%) is already met.
- **Mitigation:** M2 with a cap of `[3]` false alarms per clean drawing; run every change on the unmodified
  samples; severity levels so minor items don't bury critical ones; per-rule acceptance rates (US-11.2) to
  switch off noisy rules.
- **Trigger:** Offline precision below `[70]`%, or more than `[3]` findings on any unmodified sample judged false.
- **Contingency:** Report only Critical and Major by default; show LLM findings as *warnings to confirm*;
  suppress noisy rules per-rule (US-11.2); move numeric checks to code so the LLM raises fewer findings.
- **Phase:** 2–4 · **Status:** Open

### R4 · Wrong findings with valid citations pass the verifier

- **Risk:** Because the verifier checks only that cited evidence exists, not that the reasoning is right, an LLM
  reviewer may cite a real dimension for a problem that isn't there, which would reach the checker as a
  credible-looking false finding and damage trust.
- **Category:** AI quality · **L** 4 · **I** 4 · **Score** 16
- **Strategy:** Reduce
- **Evidence (Spike E, 2026-10-13):** only 12/102 off findings cited a missing id, so citations are mostly
  valid — but the reasoning is often wrong (standard clearance holes flagged, a benign title-block/note heat-
  treatment inconsistency rated **Critical**). A citation-only verifier would pass these. Precision 32% (strict)
  – 61% (lenient): the < 60% trigger is met on the strict count and borderline on the lenient one.
- **Mitigation:** Use code and lookups wherever an exact answer exists (J2, most of J3–J4); require LLM findings
  to quote the rule and explain the reasoning; measure precision per reviewer; consider a second-opinion check on
  Critical findings from LLM reviewers; **severity comes from the rulebook, not the model** (D18, O2).
- **Trigger:** LLM reviewer precision below `[60]`% in Spike E or the first eval.
- **Contingency:** LLM-reviewer findings are *warnings to confirm*, never *fail* — now the **default** (D16),
  not a fallback, until precision meets target.
- **Phase:** 2–4 · **Status:** Open

### R9 · Client drawings in a public repository

- **Risk:** Because ADR 0007 commits the client's full dataset (about 1,170 drawings, checklist and guidelines)
  to a public GitHub repository, PARI's drawings are visible to anyone, which may breach the client's
  confidentiality expectations or an NDA and end the engagement.
- **Evidence:** CLAUDE.md: "the repo is public"; `data/client_set/` is committed.
- **Category:** Security & confidentiality · **L** 3 · **I** 5 · **Score** 15
- **Strategy:** Reduce
- **Mitigation:** Confirm in writing with LatentView that the drawings may be public; if not, make the repo
  private, or move client data out of git, and purge it from history.
- **Trigger:** No written permission by `[2026-10-20]`, or any confidentiality clause in the capstone agreement.
- **Contingency:** Make the repo private immediately, rewrite history to remove `data/client_set/`, and
  distribute data through a private channel; record the change in a new ADR superseding 0007.
- **Phase:** 0 · **Status:** Open

### R10 · Providers retain or process drawings outside PARI's rules

- **Risk:** Because review sends drawing images and text to OpenAI and Alibaba Qwen, the providers may retain
  that data or process it in regions PARI does not allow, which would breach confidentiality even though our own
  storage is session-scoped.
- **Evidence (Spike G, 2026-10-13):** neither provider trains on API data. OpenAI keeps abuse-monitoring logs
  for up to 30 days unless Zero Data Retention is approved. Alibaba stores request data in the region called (US,
  Virginia) and can keep inference in the US with a US-scope workspace, but publishes no retention period.
  Likelihood lowered from 3 to 2.
- **Category:** Security & confidentiality · **L** 2 · **I** 5 · **Score** 10
- **Strategy:** Reduce
- **Mitigation:** Spike G (retention and region per provider and endpoint); `store=false` on OpenAI; raise O4 with
  LatentView before any pilot.
- **Trigger:** PARI or LatentView restricts one of the providers.
- **Contingency:** Restrict the registry roles to permitted providers; if neither is permitted, evaluate a
  self-hosted vision model (cost and quality impact to be measured).
- **Phase:** 1 · **Status:** Open

### R18 · Qwen endpoint is no longer supported for the US region

- **Risk:** Because `config/models.yaml` calls `dashscope-us.aliyuncs.com`, which Alibaba's regions page now lists
  as *Not supported* for US (Virginia), Qwen calls may stop working or lose new features, and we cannot show
  which deployment scope (US or Global) they run in. That would break development runs and weaken the answer to
  O4.
- **Evidence:** Alibaba regions page, updated 2026-10-13: a migration notice for US (Virginia) and workspace
  endpoints `{WorkspaceId}.us-east-1.maas.aliyuncs.com`; the DashScope domain gets no new features after
  2026-09-30. Calls still worked during M1 (2026-10-06).
- **Category:** External dependency · **L** 4 · **I** 2 · **Score** 8
- **Strategy:** Reduce
- **Mitigation:** Create a US-scope workspace, check that the models we use are available in it, switch
  `base_url` in `config/models.yaml`, re-run `di eval understand`, and record the change in an ADR.
- **Trigger:** Any Qwen call fails with an endpoint or region error, or the client asks where inference runs.
- **Contingency:** Use OpenAI for the affected role while migrating, with Binjie's approval and within budget.
- **Phase:** 1 · **Status:** Open

### R5 · Vision model invents or misses symbols

- **Risk:** Because GD&T frames, surface-finish and weld symbols exist only in the image, the vision model may
  report symbols that are not there or miss ones that are, which would cause false or missed findings in J4.
- **Evidence:** In the notebook experiments one model reported 6 symbols on the Cam Plate that are not on the
  drawing; the first package run reported none.
- **Evidence:** Spike D (2026-10-15), 10 drawings / 13 pages, qwen3-vl-plus thinking off: **0/32** finish marks,
  **0/9** datum flags, **16/39** GD&T frames found (characteristic right on 5/16); phantoms 2/18 (11%, datum
  letters filed as GD&T). Every matched frame came from the text layer (identical bbox), not the image. GD&T is
  exact from the `SolidEdgeANSI1Symbols` text; datum flags and finish marks are found by vector detectors.
  Re-scored L 4 → 5 (misses are near certain), strategy Reduce → Avoid.
- **Category:** AI quality · **L** 5 · **I** 3 · **Score** 15
- **Strategy:** Avoid — do not take symbols from vision
- **Mitigation:** Spike D; mark every symbol `source: vision`; complete `data/labels/symbol_counts.json`;
  consider extracting symbols from PDF vector paths where possible.
- **Trigger:** Phantom-symbol rate above `[10]`% in Spike D.
- **Contingency:** Report symbol-based findings as *warnings to confirm* only.
- **Decision (Spike D):** decode the glyph font and parse GD&T frames in stage 1; detect datum flags and finish
  marks from vectors; vision-only symbols are *warnings to confirm*.
- **Phase:** 1–3 · **Status:** Mitigation chosen

### R6 · Template variations break extraction

- **Risk:** Because the client set spans A0–A4 sheets, multi-page files and modified copies, template regions
  tuned on four A3 samples may crop the title block wrongly or crash, which would block J1 on part of the set.
- **Evidence:** 2026-10-13: `05015NB02996_modified_0A1.pdf` (round part) extracted without error — 18
  dimensions, 54 title-block lines. Only one file outside the samples has been tried.
- **Category:** Data · **L** 2 · **I** 4 · **Score** 8
- **Strategy:** Reduce
- **Mitigation:** Spike C over all 1,171 drawings; a smoke test in CI on a sample of each sheet size.
- **Evidence:** Spike C (2026-10-13): all 1,171 client drawings + 4 samples extracted with **0 exceptions**;
  0 files without a text layer; 1 file (0.1%) found no dimensions (a 90°-rotated sheet). Edge-anchored template
  regions crop the title block correctly A4→A0. Far below the 2% trigger, so likelihood lowered from 3 to 2.
  Caveat: ~17% of sheets use a variant title block and material is the placeholder `#` on 86% — these do not
  break extraction but drive the new risk R19.
- **Remaining action:** CI smoke test on one sheet of each size (A4–A0) + the rotated file as a known-hard case.
- **Trigger:** Crash or crop-failure rate above `[2]`% in Spike C.
- **Contingency:** Reject affected sheet sizes clearly (US-1.2) until template regions are fixed.
- **Phase:** 1 · **Status:** Open

### R7 · Round-part features are handled worse than prismatic ones

- **Risk:** Because the four development samples are all plates, blocks and clamps, extraction and prompts may not handle
  diameters, threads, chamfers, centre holes and fits well, which would lower M1 for the 532 round parts now in
  scope (D13).
- **Category:** Data / AI quality · **L** 3 · **I** 4 · **Score** 12
- **Strategy:** Reduce
- **Mitigation:** Add `[2]` round parts to `data/raw/` with labels; include round parts in the planted-error set;
  report M1 per part family (US-1.4 AC3).
- **Evidence:** Spike C (2026-10-13): stage-1 extraction is **cleared** for round parts — 0 crashes across 532
  round and 639 prismatic drawings; the 3 imperfect round files trace to template/orientation, not round
  geometry. Stage-2 reviewer quality on diameters, threads, chamfers and fits is **still open**, which keeps
  this at 12.
- **Trigger:** Round-part recall more than `[5]` points below prismatic.
- **Contingency:** Add round-part-specific guidance to the understanding prompt and rules for round features.
- **Phase:** 1–3 · **Status:** Open

### R19 · Title-block variants and placeholder values cause wrong or noisy title-block findings

- **Risk:** Because ~17% of sheets use an older/variant title block with different label wording, and the
  MATERIAL (and SURFACE TREATMENT, MACHINING) cell is the placeholder `#` on 86% of sheets, a stage-2
  title-block reviewer keyed to the standard 16 labels may map fields to the wrong cells or report a `#`
  material as missing or invalid, which would produce wrong or noisy title-block findings and false alarms
  (R3, M2).
- **Evidence (Spike C, 2026-10-13):** 203/1,171 files read 9–13 of 16 standard labels; material is a real value
  on only 13.4% (`#` on 1,016 files); scale truncated to `1 :` on 35; number garbage (`B`, `T+S`) on 2 variant
  blocks.
- **Also (Spike E, 2026-10-13):** the judgement reviewer's most frequent *real* extra finding was a title-block
  heat-treatment field (`---`) vs a note that specifies the treatment — a consistency issue it reports as
  design_intent and over-rates. Argues for a dedicated title-block/consistency check rather than the LLM (O9).
- **Category:** Data / AI quality · **L** 4 · **I** 3 · **Score** 12
- **Strategy:** Reduce
- **Mitigation:** Ask PARI what `#` means and where material is defined (O8). Give stage 2 the variant label set
  or read labels by position; treat `#`/`-`/`NA` as "not filled", never as a value, and do not raise a
  placeholder material as a fail until PARI confirms its meaning.
- **Trigger:** Stage-2 title-block field accuracy below `[target]` on the variant templates, or `#` materials
  raised as findings.
- **Contingency:** Restrict title-block findings to fields with a real value; show variant-block fields as
  *to confirm*.
- **Phase:** 1–2 · **Status:** Open

### R8 · Planted errors are unrealistic, so metrics overstate quality

- **Risk:** Because no drawings with labelled real errors exist, the evaluation set is built from errors the team
  plants, which may be easier to catch than real ones and make M1 look better than real-world performance.
- **Category:** Data · **L** 4 · **I** 3 · **Score** 12
- **Strategy:** Reduce
- **Mitigation:** Spike F (proxy rates realism); answer keys written before any reviewer exists; ask PARI for
  examples of past rejection reasons (*Common rejection conditions*); compare with online acceptance (M2).
- **Trigger:** Online acceptance rate far below offline precision.
- **Contingency:** Rebuild the set around rejection reasons PARI provides.
- **Phase:** 2 · **Status:** Open

### R13 · Findings change from run to run

- **Risk:** Because LLM outputs vary between runs, the same drawing may get different findings each time, which
  would confuse the checker and make metrics noisy.
- **Category:** AI quality · **L** 4 · **I** 3 · **Score** 12
- **Strategy:** Reduce + Accept (some variance is accepted, D5)
- **Evidence (Spike E, 2026-10-13):** run-to-run stability 40% on thinking-off (2 runs/case) — the same drawing
  yields different findings each run. Supports running reviewers twice and reporting only findings that agree.
- **Mitigation:** Code checks for everything exact; run each eval case `[3]` times; measure stability in task A1;
  low temperature or thinking settings chosen by eval.
- **Trigger:** A Critical finding appears in fewer than `[2]` of `[3]` runs on the same drawing.
- **Contingency:** Run LLM reviewers `[2]` times and report only findings that agree, if cost allows (M4).
- **Phase:** 2–4 · **Status:** Open

### R14 · Scope exceeds the capstone timeline

- **Risk:** Because v1 includes four reviewer types, two part families, Q&A, feedback and evaluation, the team may
  not finish all of them, which would leave the most visible jobs half-built at the final presentation.
- **Category:** Scope & schedule · **L** 4 · **I** 3 · **Score** 12
- **Strategy:** Reduce
- **Mitigation:** MoSCoW prioritisation after Spike A; build in the order J2 → J10 → J8 → J3/J4 → J5/J6 → J9;
  dashboard already a non-goal (NG11).
- **Trigger:** A milestone in PROJECT.md §9 slips by more than `[1]` week.
- **Contingency:** Drop J5/J6 to *not checked* and present a complete review for J2–J4.
- **Phase:** all · **Status:** Open

### R11 · Cost per drawing exceeds $1

- **Risk:** Because reasoning models and thinking tokens dominate cost, a full review with three LLM reviewers may
  exceed the $`[1]` budget, especially with `gpt-6-astra`.
- **Evidence:** Understanding alone costs $0.011 (`qwen3-vl-plus`, thinking off); `gpt-6-astra` costs about 50×
  more per drawing; notebook runs reached $0.58 for understanding alone.
- **Category:** Cost · **L** 3 · **I** 3 · **Score** 9
- **Strategy:** Reduce
- **Mitigation:** Reviewers read JSON, not images; per-role model choice by eval; estimate and confirm before
  expensive runs (US-14.3); response cache in development.
- **Trigger:** Mean cost above $`[0.75]` on the sample set.
- **Contingency:** Use smaller models for low-impact reviewers; turn thinking off where eval shows no loss.
- **Phase:** 2–4 · **Status:** Open

### R16 · Q&A agent answers beyond the stored results

- **Risk:** Because an agent with general knowledge may answer from memory, it may state facts that are not on the
  drawing, which would break M3 and M6.
- **Category:** AI quality · **L** 3 · **I** 3 · **Score** 9
- **Strategy:** Reduce
- **Mitigation:** Read-only tools over the session JSON only; every answer must cite; `[10]` not-answerable
  questions in the eval (M6).
- **Trigger:** Any not-answerable question answered as fact.
- **Contingency:** Require at least one resolved citation before an answer is shown; otherwise reply "not on the
  drawing".
- **Phase:** 4 · **Status:** Open

### R17 · Development runs delete or change committed data

- **Risk:** Because `data/sessions/` and `data/telemetry.db` are committed (ADR 0007) and the CLI sweeps leftover
  sessions and writes telemetry on every run, a developer's run may delete or change committed files, which would
  cause noisy diffs, merge conflicts or lost dev outputs.
- **Evidence:** 2026-10-13: one `di extract` run with `DI_RETENTION=ephemeral` deleted the three committed session
  folders as crash leftovers, and runs modified `data/telemetry.db`; both were restored from git.
- **Category:** Data · **L** 4 · **I** 2 · **Score** 8
- **Strategy:** Reduce
- **Mitigation:** Stop committing `data/sessions/` and `data/telemetry.db` (git-ignore them), or point the CLI at
  a separate dev data directory.
- **Trigger:** `git status` shows changes under `data/sessions/` or `data/telemetry.db` after a run.
- **Contingency:** `git checkout -- data/sessions data/telemetry.db`.
- **Phase:** all · **Status:** Occurred

### R12 · Text inside a drawing changes review behaviour

- **Risk:** Because drawing notes are sent to the model as text, a note written like an instruction may change how
  a reviewer behaves, which would suppress or invent findings.
- **Category:** Security · **L** 2 · **I** 3 · **Score** 6
- **Strategy:** Avoid + Reduce
- **Mitigation:** Drawing text is delimited and labelled as data in every prompt; reviewers have no write tools;
  red-team drawings in the eval (US-10.3, M3).
- **Trigger:** Any red-team drawing changes review output.
- **Contingency:** Strip instruction-like notes into a quarantined field shown to the checker.
- **Phase:** 2–4 · **Status:** Open

### R15 · Model prices change or a model is retired

- **Risk:** Because the registry relies on current prices and model names (and `qwen3.8-max` pricing comes from a
  third-party page), cost figures may be wrong or a model may disappear, which would break M4 reporting or runs.
- **Category:** External dependency · **L** 3 · **I** 2 · **Score** 6
- **Strategy:** Reduce
- **Mitigation:** `verified_on` and source for every price in `config/models.yaml`; confirm `qwen3.8-max` pricing
  on Alibaba's official page; role defaults can switch model without code changes.
- **Trigger:** A provider announces a price change or deprecation.
- **Contingency:** Re-run `di eval` and switch the role default.
- **Phase:** all · **Status:** Open

---

## 4. Assumptions to Validate

Unvalidated assumptions are risks in disguise. Each is checked by a Phase 1 spike (see `01_discovery.md` §10).

| ID | Assumption | Related risks | Validated by |
|---|---|---|---|
| A1 | PARI's last point check follows the categories in `Check List.docx` | R1 | Spike A |
| A2 | Checkers will use an AI first pass if every finding cites evidence on the sheet | R1, R3 | Spike A, online M2 |
| A3 | The client's checklist and WP guidelines contain enough detail to write checkable rules | R2 | Spike B |
| A4 | All client drawings are vector PDFs with a text layer on template FR-DES-006-01 | R6, R7, R19 | Spike C — **partly validated** (2026-10-13): vector + text layer on 100%; but ~17% use a variant title block and key fields are not all populated (material `#` on 86%), so "single template FR-DES-006-01" is **false**. |
| A5 | PARI allows drawings to be sent to at least one of the registered providers | R10 | Spike G, O4 |

---

## 5. Review Log

| Date | Phase | Change |
|---|---|---|
| 2026-10-13 | 0 | Initial register: 17 risks, 5 assumptions. |
| 2026-10-13 | 1 | Spike G results: R10 lowered from 15 to 10 with new evidence; added R18 (Qwen US endpoint no longer supported). |
| 2026-10-13 | 1 | Spike C results: 0 crashes over 1,175 files. R6 lowered 12→8; R7 kept at 12 (extraction cleared, stage-2 open); added R19 (title-block variants + `#` placeholder, 12); A4 partly validated. Added O8. |
| 2026-10-13 | 1 | Spike E results: off recall 100%, precision 32–61%, stability 40%, thinking-on ~6.5× cost. R3/R4/R13 confirmed (scores unchanged) with evidence; R19 note added. LLM findings → warnings-to-confirm; numeric checks → code; severity → rulebook. |
