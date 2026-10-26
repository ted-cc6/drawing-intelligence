# Oct 25 update and next steps

*For: Mushahid Raza, Zhetao Zhang · From: Binjie Wang · 2026-10-25*

This replaces the [Oct 06 update](Oct_06_UpdateAndNextStep.md), which stays as the original plan. It covers what
happened to every task in that plan, what the system is now, how well it works, **how we got to today's numbers
and why the design looks the way it does**, what is left, and who builds what next.

The full design is in [docs/PROJECT.md](docs/PROJECT.md); the decisions are in [docs/adr/](docs/adr/) (new since
Oct 06: [0008](docs/adr/0008-review-contracts-enforce-trust.md), [0009](docs/adr/0009-understanding-model-default.md),
[0010](docs/adr/0010-review-stage-design.md), [0011](docs/adr/0011-qa-agent.md)).

**Contents**
1. [Summary](#1-summary)
2. [Every task in the Oct 06 plan: what happened](#2-every-task-in-the-oct-06-plan-what-happened)
3. [What the system is now](#3-what-the-system-is-now)
4. [Results](#4-results)
5. [How we got here](#5-how-we-got-here)
   - 5.1 [Why code checks come first](#51-why-code-checks-come-first)
   - 5.2 [Building the code checks](#52-building-the-code-checks)
   - 5.3 [Raising the AI reviewers' accuracy](#53-raising-the-ai-reviewers-accuracy)
   - 5.4 [How code checks and AI reviewers work together](#54-how-code-checks-and-ai-reviewers-work-together)
   - 5.5 [Symbols: from the image to the PDF itself](#55-symbols-from-the-image-to-the-pdf-itself)
   - 5.6 [Reference tables from a scanned book](#56-reference-tables-from-a-scanned-book)
   - 5.7 [How we measure](#57-how-we-measure)
   - 5.8 [The Q&A agent](#58-the-qa-agent)
6. [What is left, and who builds what](#6-what-is-left-and-who-builds-what)
7. [Setup, commands, data, team rules](#7-setup-commands-data-team-rules)

---

## 1. Summary

The whole review now runs end to end: `di review drawing.pdf --export out/` reads a drawing, checks it against
the rulebook with code and with AI reviewers, drops anything it cannot prove, and writes an Excel checklist in
PARI's columns plus an annotated sheet. About 2 minutes and $0.04 per drawing; re-runs are free from the cache.
`di ask drawing.pdf` then answers questions about the reviewed drawing, with every answer checked by code.

| Headline | Number | Where measured |
|---|---|---|
| Code checks built | 49 of 135 code/lookup rules (44 functions) | `di rules` |
| Planted errors caught where a check exists | 18/18, **0 false alarms** | `di eval review --no-understand` |
| Planted errors caught, code + AI | 20/22 (19–20: one AI catch is not stable) | [PROJECT.md §8](docs/PROJECT.md) |
| Code findings on 24 unseen client drawings | **63 correct, 0 incorrect**, 9 unsure | [heldout README](data/eval/heldout/2026-10-25/README.md) |
| AI findings on the same drawings | 36% → **88%** precision after three rounds of fixes (optimistic, see 5.3) | same |
| Q&A agent | 40/41 answers right, 41/41 verified | [qa results](data/eval/qa/results/README.md) |
| Tests | 404 (were 77) | `uv run pytest` |

The biggest lessons, each explained in §5: **the LLM finds problems but cannot be trusted to judge them**, so
exact rules are code and the LLM only warns; **every number we report was measured on drawings nobody tuned
on, or says that it was not**; and **reading every finding by hand found problems the scores missed, every
time**.

---

## 2. Every task in the Oct 06 plan: what happened

| Task | Assigned to | Built by | Status | What changed from the plan |
|---|---|---|---|---|
| A2 Review contracts | Binjie | Binjie | ✅ | Became [ADR 0008](docs/adr/0008-review-contracts-enforce-trust.md): findings are issues only (a pass is a rule status, not a finding); severity comes from the rule; a *fail* needs exact evidence |
| A1 Understanding model | Zhetao | Zhetao | ✅ | Recorded as **ADR 0009** (0008 went to A2): `qwen3-vl-plus`, thinking off. Labels verified, `--runs` stability added |
| A5a Planted errors | Mushahid | Mushahid | ✅ | 28 cases (plan: ≥15): 22 planted, 2 near-miss, 4 clean; replacements in the page's own font |
| R Draft rulebook | Mushahid | Mushahid | ✅ | 174 rules (110 code, 25 lookup, 39 LLM) from the LatentView rulebook v0.2, PARI's guidelines and six engineering books; every LatentView rule mapped or given a reason |
| A4 Consistency reviewer | Mushahid | Binjie | ✅ | Redesigned as a **check registry** ([ADR 0010](docs/adr/0010-review-stage-design.md)) instead of one `consistency.py`; 44 check functions across all categories, not just consistency |
| A3 Verifier | Mushahid | Binjie | ✅ | As planned, plus quote checks against the PDF text and one status per rule |
| A5b `di eval review` | Zhetao | Binjie | ✅ | Plus a CI regression gate, and **held-out validation** on unseen client drawings (`di eval heldout`), which the plan did not have |
| A6 Graph fan-out and report | Binjie | Binjie | ✅ | Report zones from the sheet's border markers ("Sheet 1, zone C4") |
| A7 Q&A agent (backlog) | – | Binjie | ✅ | [ADR 0011](docs/adr/0011-qa-agent.md); `di ask`, `di eval qa` |
| Standards / manufacturability / design-intent reviewers (backlog) | – | Binjie | ✅ | Three LLM reviewers (warnings only) plus five reference tables for the exact standards checks |
| A8 Hardening (backlog) | – | partly | ◐ | Done: a smoke test of all 1,175 client drawings (Spike C, 0 crashes); prompt-injection guard for the Q&A agent. Open: see §6 |
| API + dashboard (backlog) | – | – | ✗ | Not started (M5) |
| Spikes C, D, E (not in the plan) | – | Binjie | ✅ | They changed the design: see §5.1 and §5.5 |

---

## 3. What the system is now

```
                ┌──────────────── REVIEW WORKFLOW (LangGraph, fixed path) ─────────────────┐
PDF ─► 1 Intake ─► 2 Understand ─► 3 Review (parallel reviewers) ─► 4 Verify ─► 5 Report
       code ✅       vision LLM ✅    code checks ✅ + 3 AI reviewers ✅   code ✅      Excel + sheet ✅
                └──────────────────────────────────────────────────────────────────────────┘
Engineer ◄─► Q&A agent ✅ (di ask): read-only tools over the saved results, answers checked by code
```

| Stage | What it does now | Where |
|---|---|---|
| 1 Intake (code, $0) | Exact text and lines from the PDF; title-block fields by position, including PARI's `#` notes block; revision table; the printed general-tolerance table; stacked limits in printed order; **symbols**: GD&T frames from the text layer, datum flags and finish marks from vector shapes | `extraction/` |
| 2 Understand (vision LLM) | `qwen3-vl-plus`, thinking off: views, features, which dimension belongs to which feature, notes. Code-derived fields are kept out of its prompt | `understanding/` |
| 3 Review | **`checks`**: 44 code/lookup functions over 49 rules. **Three AI reviewers** (`drawing_practice`, `manufacturability`, `design_intent`, `qwen3.8-max`) for the 24 judgement rules they can see; 15 more are held back until their inputs exist | `review/checks/`, `review/llm_reviewer.py` |
| 4 Verify (code) | Drops a finding whose evidence does not resolve on the drawing; merges duplicates; gives every rule exactly one status | `review/verify.py` |
| 5 Report | Excel in PARI's checklist columns (Summary, Checklist, Not checked) and an annotated sheet with numbered findings | `report/` |
| Q&A | 8 tools (findings, rules, drawing search and items, standard lookups, feedback); citations and numbers checked by code | `qa/` |

**Rulebook and data:** 174 rules in `config/rules/`; reference tables in `config/reference/` (materials, PARI
DES-12 plating, IS 919 fits, IS 2102 general tolerances, ISO 261 / IS 4218 threads). A rule with no built check
reports *not checked*, never *pass*.

---

## 4. Results

**Seeded set** (28 cases; `di eval review`): what was planted is known, so this measures recall.

| | code checks | + AI reviewers |
|---|---|---|
| Planted errors caught (22) | 18 | 20 (19 on some runs) |
| Caught, where the rule is checked | 18/18 | 20/20 |
| False alarms on clean and near-miss drawings | **0** (CI gate) | 0 code; 1 AI warning |
| Precision | 64/64 | 78/89 (88%); 77/81 after the WPS-004 fix (§5.3) |

**Held-out set** (24 client drawings no development step had looked at; every finding labelled, labels confirmed
by the PARI proxy; `data/eval/heldout/2026-10-25/`): this measures precision on real drawings.

| | correct | incorrect | unsure | precision of decided |
|---|---|---|---|---|
| Code checks and lookups | 63 | 0 | 9 | **100%** |
| AI reviewers, first run | 14 | 25 | 16 | 36% |
| AI reviewers, after three rounds of fixes | 15 | 2 | 11 | **88%** (optimistic: these drawings guided the fixes) |

**Q&A agent** (`di eval qa`, 41 questions on 3 seeded and 3 held-out drawings): 40/41 right, 41/41 verified, no
unverified numbers, all 8 guards held. $0.35 per full run.

**Cost and time:** ~$0.04 and ~2 minutes per drawing for the full review (understanding ~$0.011, reviewers
~$0.015–0.025); code checks alone cost nothing and take seconds. Every model reply is committed in
`data/cache/`, so re-running any evaluation above is free. A1's model comparison spent $5.39 (its own $5 cap,
approved overrun); the rest of the work about $4.89 of an $8 budget (raised from $5 for the Q&A milestone).

---

## 5. How we got here

Each part follows the same order: the problem, what we thought, what we did, the result, what is left.

### 5.1 Why code checks come first

**Problem.** The Oct 06 plan assumed an LLM reviewer would do most of the reviewing once the rules arrived. Before
building it, Spike E ([docs/spikes/spike_e_llm_judgement.md](docs/spikes/spike_e_llm_judgement.md)) tested
whether `qwen3.8-max` can judge manufacturability and design intent on planted errors and on clean controls.

**What we found.**
- **It finds errors:** 10/10 planted errors caught.
- **It cannot be trusted to judge them:** precision 32–61%, about 3 findings per drawing, many unfounded
  ("tolerance too tight" with no rule behind it, speculation about the material, standard clearance holes
  called non-standard).
- **It does not apply numeric rules:** it flagged a hole at 8:1 depth to diameter *after computing 8:1*, below
  the 10:1 limit it was given.
- **It cannot set severity:** it rated a correct, fully specified heat treatment *Critical*.
- **Thinking on** cost ~6.5× and took ~11× longer (310 s per drawing) without a measured gain.

**What we decided** ([ADR 0008](docs/adr/0008-review-contracts-enforce-trust.md), then
[ADR 0010](docs/adr/0010-review-stage-design.md)):
- Every rule that can be decided exactly is **code** (`check_type: code`) or a **table lookup** (`lookup`). Only
  rules that need judgement are `llm`.
- **Only code may fail a drawing.** A *fail* must cite exact evidence (`pdf_text` or `vector`). An AI finding is
  at most a *warning* for a person to confirm.
- **Severity comes from the rulebook**, never from the model.
- Reviewer model: `qwen3.8-max`, thinking off.

That is why 135 of the 174 rules are code or lookup, and why the code checks were built before the AI reviewers.

### 5.2 Building the code checks

**The design** ([ADR 0010](docs/adr/0010-review-stage-design.md)). A check is a small pure function registered
by name with its parameters:

```python
@check("chain_sum", ChainSumParams)
def chain_sum(ctx: ReviewContext, rule: Rule, params: ChainSumParams) -> list[Finding]: ...
```

The rule in `config/rules/*.yaml` names the check and gives its parameters; findings are made with
`new_finding(rule, ...)`, so category and severity always come from the rule. A check that does not apply raises
`NotApplicable`; one that lacks its input raises `NotCheckable` (reported "not checked", never "pass"). `di rules`
shows which rules have a built check. This let 44 functions cover 49 rules, and lets a teammate add a check
without touching the graph.

**How each check was built.** The same loop every time:
1. Write the check and unit tests on synthetic pages.
2. **Sweep it over 200 random client drawings** (the development sample) and **read every finding**.
3. Fix what reading shows to be wrong; sweep again.
4. Confirm the seeded set still has 0 code false alarms (the CI gate), then commit.

Step 2 is where nearly every problem was found. The checks were right on synthetic tests and still wrong on real
drawings, because real drawings break assumptions:

| Challenge found in the sweep | What we did |
|---|---|
| **The title block was not where the data was.** Spike C ([docs/spikes/spike_c_template_coverage.md](docs/spikes/spike_c_template_coverage.md)): on 86% of 1,175 drawings the material cell prints `#`, and 17% use an older title-block layout | Read fields by position from the template config; read PARI's `# MATERIAL: …` notes block when a cell says `#` (the material and plating lookups went from skipping most drawings to checking them) |
| **Stacked limits in the wrong order.** RQ-002 (inverted limits) failed 13 of 13 sheets: the PDF stores `+0.018` and `0` in any order | Stage 1 orders a stacked pair by where it is printed; real failures dropped to 4, all genuine |
| **CAD trailing zeros.** LY-005 (decimals vs tolerance) failed 91 of 195 sheets, mostly `18.00` under ±0.2 | Trailing zeros under the general tolerance are not counted until PARI decides (rule parameter); two-decimal sizes like `15.21` still fail and are a question for PARI |
| **Placeholders.** `---`, `--`, `.....` in cells | One placeholder rule: any run of dashes or dots is empty |
| **Labels that look like numbers.** Hole tags `A.1` read as ".1 without a leading zero"; chamfers `2X45°` read as a fit code "X45"; `LM GUIDE ROD (HARDENED & GROUND)` read as a heat-treatment instruction | Narrower patterns, each found in the sweep and tested |
| **Text split across lines.** The ownership note prints over two lines, so 160 of 200 drawings "lacked" it | Match the note's words, not the joined line |
| **Dates.** `06-05-2024` rejected because the template format is `dd/mm/yyyy` | Accept `/`, `-` and `.` as the same separator |

**Results.** Seeded recall rose as checks were added: **10/22 → 15/22 → 18/22**, always with 0 false alarms and
every finding correct. On the 24 unseen drawings: **63 correct, 0 incorrect**. Code checks cost $0 and take
seconds.

**What is left.** 86 code/lookup rules, grouped in [docs/backlog/rules_to_build.md](docs/backlog/rules_to_build.md)
by what they need (§6). Several "unsure" held-out findings are policy questions for PARI, not bugs (§6).

### 5.3 Raising the AI reviewers' accuracy

**Problem.** Some rules need judgement ("is this fit plausible for plated steel?", "is the heat-treatment stage
stated?"). Spike E showed the model is noisy, so the question was how to make its warnings worth reading.

**What we built.** Three AI reviewers, one model call each, given the drawing's exact text and the understanding
output (not the image), and a short list of only the rules they own. Each reply is a JSON list of findings that
must cite IDs (`D7`, `N2`, a title-block field); verify drops any that do not resolve.

**The journey, round by round.**

| Step | Precision of AI findings | What we learned and changed |
|---|---|---|
| First calibration, 8 seeded cases | **1 of 26** right | Most false alarms were PARI's own template notes ("notes copied from another drawing") and rules about symbols the reviewers could not see (roughness, GD&T). **Fix:** leave template boilerplate out of the message; hold back rules whose input does not exist yet (`params.needs`) |
| All 28 seeded cases | 15/26 (**58%**) | Recall rose from 18/22 to 20/22 (P19 lost fit, P20 internal corner). The reviewers raised WPS-004 (zinc plating eats an H7 band) on every plated H7 hole; the PARI proxy confirmed it is real, so it went into the answer keys as a pre-existing issue |
| 24 unseen client drawings | 14 correct, 25 incorrect (**36%**) | Real drawings are noisier than planted ones. Two rules made most of the noise: NM-008 (11 of 12 wrong, PARI's standard bilingual notes) and MF-007 (4 of 5 wrong) |
| Fix round 1 | **57%** | Read the `#` notes block (the reviewers had been complaining about "missing" material); hold back NM-008 until PARI lists its standard notes; MF-007 only when the drawing states a conflict |
| Fix round 2 | 15 correct, 2 incorrect (**88%**) | WPS-004 narrowed to real fits and tight bands (it was firing on every plated hole) through the rule's `llm_instruction` |
| Experiment: give them the stage-1 symbols | back to **57%** | 8 held-back rules released; their 14 findings: 0 correct. Knowing *that* a symbol exists is not enough: these rules need to know which faces mate, seal or rotate. **Held back again** (`needs: [symbols, functional_faces]`) |

**How the fixes were made.** Never by editing the shared reviewer prompt: that would have changed every cached
reply and every past result. Changes went into the rulebook (which rules run, `llm_instruction` per rule) and
into what the reviewers are given, so each change was measured alone, and re-runs of unchanged reviewers were
free.

**Honest limits.**
- **88% is optimistic.** The same 24 drawings guided three rounds of fixes. Only a fresh unseen set can confirm
  it (§6).
- **Some catches are not stable.** P19 was caught on one run and missed on another (Spike E measured ~40% run-to-run
  stability). That is another reason AI findings are warnings.
- 11 "unsure" findings need an engineer's answer, not a model change.

### 5.4 How code checks and AI reviewers work together

- **Each rule has one owner.** `check_type` in the rule decides: `code` and `lookup` rules go to the `checks`
  reviewer, `llm` rules to the AI reviewer for their category. No rule is judged twice.
- **They run in parallel** in the graph and do not see each other's findings.
- **Different authority.** Code findings can *fail* the drawing with exact evidence. AI findings are always
  *warnings* with the model's reasoning, marked "AI reviewer" in the report.
- **Verify applies to both.** Any finding whose IDs, page, bbox or quoted text do not match the drawing is dropped
  (the reason is kept for debugging). This is what stops an AI reviewer from inventing a dimension.
- **One status per rule.** Every rule ends as pass, fail, warning, not applicable or not checked. An AI rule with
  no finding is *not checked*, not *pass*: silence from a model proves nothing.
- **The report shows all of it:** fails first, then warnings, each with its location on the sheet and how it was
  checked; a third sheet lists what was not checked and why.

### 5.5 Symbols: from the image to the PDF itself

**Problem.** GD&T, datum and surface-finish rules need the symbols. The plan was to let the vision model read
them.

**What Spike D found** ([docs/spikes/spike_d_symbols.md](docs/spikes/spike_d_symbols.md)): with the image, the
model found **0 of 32** finish marks, **0 of 9** datum flags and 16 of 39 GD&T frames, naming the right
characteristic for only 5. What it did find came from the text, not the pixels.

**The insight.** Solid Edge writes each feature control frame as a text line in a symbol font (`n 0.05 A` means
⊥ 0.05 | A), and datum flags and finish marks are simple vector shapes. So stage 1 reads them **exactly, at $0**:
frames by decoding 11 font glyphs, datum flags and finish marks by small geometry detectors. 745 of 1,175 client
drawings have at least one frame.

**Result.** Six GD&T and datum checks on the exact symbols (a frame references a defined datum, form tolerances
take no datum, ...), tuned on the 200-drawing sweep. Giving the symbols to the AI reviewers did not help (§5.3):
the next input they need is which faces are functional.

### 5.6 Reference tables from a scanned book

**Problem.** Fit, thread and general-tolerance rules need standard tables (IS 919, IS 2102, ISO 261). The only
source PARI gave is the scanned Westermann book.

**What we did.** Transcribed the needed pages into `config/reference/*.yaml`, each value citing its page. Because
a misread digit in a scan would produce a confident wrong finding, `tests/test_reference_tables.py` checks the
tables against the **structure of the standards themselves**: every fit zone must be exactly its IT grade wide,
fundamental deviations must agree across grades and between holes and shafts, general tolerances must widen with
size and class.

**Result.** All 40 fit zones pass, and the test found one **misprint in the book** (j6, 80–120 mm, printed "+1",
should be +13), corrected and noted. On the 200-drawing sweep, 56 printed fits were compared and all agree with
IS 919; PARI's machining table is exactly IS 2102 medium, the fabrication table coarse.

### 5.7 How we measure

- **Seeded set** (A5a): known planted errors, plus clean and near-miss drawings that must stay silent. Gives
  recall and false alarms. Answer keys were written before any reviewer existed and are never changed to fit a
  result. Its precision is optimistic, because we tuned on it.
- **Development sample:** 200 random client drawings (seeds 1 and 2) used for every sweep. Everything tuned
  there.
- **Held-out set:** 24 client drawings drawn from what no sweep had touched (`di eval heldout`). Every finding
  labelled correct / incorrect / unsure with a reason, and confirmed by the PARI proxy. This is the precision a
  real review would have.
- **CI gate:** the seeded set must keep 0 code false alarms and at least 18 catches; it runs on every push.
- **Reading, not just scoring.** Every evaluation here was followed by reading the findings or answers one by
  one. It found the stacked-limit bug, the noisy AI rules, the symbols failure and three flaws in the Q&A checker
  that the scores alone did not show.

### 5.8 The Q&A agent

**Problem.** Engineers want to ask "why is #4 flagged?" or "what are the limits of D12?". A free-form chatbot
would answer confidently and sometimes wrongly.

**What we decided** (a grilling session, then [ADR 0011](docs/adr/0011-qa-agent.md)):
- One agent with **read-only tools** over the saved review (it never sees the image again), plus one write tool
  for feedback.
- **Every answer is checked by code:** each citation (`[D12]`, `[F4]`, `[T:is919_fits H7 20]`) must exist, and
  every number must appear in what the tools returned. Tools do the arithmetic (limits of size, table lookups); the
  model only quotes. A failed answer is sent back to the model, up to 4 times.
- No design advice; drawing text is data, never instructions; feedback only when the engineer asks.

**Evaluation** (41 questions, `di eval qa`): 40/41 right, 41/41 verified. Reading every answer found three flaws
the score missed: malformed citations (`[L:C10]`) accepted; an injection test the agent never actually saw;
and, most serious, answers saying a tolerance was "not in the drawing's data" while describing a search that never
ran. All three fixed (an absence answer now needs a real search behind it).

---

## 6. What is left, and who builds what

Owners are **proposed**; change them before we start.

| # | Work | Proposed owner | Notes |
|---|---|---|---|
| 1 | **Rule package P1: text and title-block checks** (27 rules) | Mushahid | No new inputs; same pattern as `checks/notes.py` and `checks/title_block.py`. You wrote these rules, so you know what each means |
| 2 | **Rule package P2: reference tables** (19 rules) | Zhetao | Transcribe and cite a table, add a structure test like `tests/test_reference_tables.py`. Some need PARI documents (DES-11) |
| 3 | **Fresh held-out evaluation of the AI reviewers** | Zhetao | Replace the optimistic 88% with a number from untouched drawings (~$1; ask first) |
| 4 | **Send the PARI questions** (below) | Binjie | Their answers turn warnings into firm checks |
| 5 | **A8 leftovers** | whoever finishes first | `llm/client.py` imports from a private OpenAI module; a session closed without a status is recorded as "running"; kept sessions (`DI_RETENTION=keep`) are never swept; the AI reviewers' messages have no injection guard yet |
| 6 | **Q&A: compare `qwen-plus`; small prompt fixes** | Binjie | Verify its price first; ~$0.15 per run |
| 7 | **Review ADR 0010** (still "proposed") | Mushahid, Zhetao | First week: it is the pattern your checks will follow |
| 8 | **Rule packages P3 (vector geometry, 12) and P4 (features, views, symbols, 28)** | later | P4 needs new inputs; several may stay AI-reviewed |
| 9 | **M5: API and dashboard** | Binjie | After the above |

The 86 rules, with an owner column per rule, are in [docs/backlog/rules_to_build.md](docs/backlog/rules_to_build.md).
**Definition of done for a check:** unit tests; a sweep over the 200-drawing sample with every finding read;
`di eval review --no-understand` still at 0 code false alarms; `di rules` shows it built; docs updated.

**Questions for PARI:**
1. IZBP on alloy steel: DES-12's material column says mild and carbon steel only, but 39 of 141 sheets use it on
   alloy steel. Which holds?
2. LY-005: should two-decimal sizes such as `15.21` under ±0.2 be flagged?
3. MF-005: where must the heat-treatment stage be stated (title block, notes, or both)?
4. The list of PARI's standard notes (to release NM-008).
5. Which faces are functional (mating, sealing, rotating), or how a drawing shows it (to release the 8
   held-back symbol rules).
6. Is an item code (e.g. `P2207012111028`) acceptable in the material cell when the notes give the material?

---

## 7. Setup, commands, data, team rules

### Setup (unchanged from Oct 06)
1. Install uv (`winget install astral-sh.uv` or `brew install uv`), then `git clone`, `cd drawing-intelligence`,
   `uv sync`.
2. `.env` from `.env.example`; paste `QWEN_API_KEY` (and `OPENAI_API_KEY`) from Binjie; set `DI_RETENTION=keep`.
3. VS Code with the recommended extensions; optional `uv run pre-commit install`.

### Commands

| Command | What it does | Cost |
|---|---|---|
| `uv run pytest` | All 404 tests (fake models, synthetic PDFs, the real samples) | $0 |
| `uv run ruff check . ; uv run ruff format --check . ; uv run pyright` | Lint, format, types (CI runs the same) | $0 |
| `uv run di review drawing.pdf --export out/` | Full review; `out/<drawing>/review_report.xlsx` and `page_N_review.png` | ~$0.04, $0 if cached |
| `uv run di review drawing.pdf --no-understand` | Code checks only | $0 |
| `uv run di ask drawing.pdf` | Chat about the reviewed drawing (`-q "..."` for one question, `--keep`, `--session ID`) | ~$0.01 per question |
| `uv run di rules` | Rulebook summary: which rules have a built check | $0 |
| `uv run di eval review --no-understand` | Seeded set, code checks (the CI gate) | $0 |
| `uv run di eval review` | Seeded set with understanding and AI reviewers | $0 from the cache |
| `uv run di eval heldout --drawings data/eval/heldout/2026-10-25/drawings.txt --out DIR` | Re-run the held-out set and write `findings.csv` to label | $0 from the cache |
| `uv run di eval qa` | Q&A evaluation | $0 from the cache; ~$0.35 uncached |
| `uv run di extract`, `di run`, `di eval baseline`, `di eval understand`, `di telemetry`, `di models` | As on Oct 06 | as before |

Paid commands show an estimate and ask before spending.

### Data

| Folder | Contents |
|---|---|
| `data/raw/`, `data/client_set/`, `data/baseline/`, `data/labels/` | As on Oct 06 (labels now verified by A1) |
| `data/eval/seeded/` | The 28 planted-error cases and their answer keys (A5a) |
| `data/eval/heldout/2026-10-25/` | The 24 held-out drawings, labelled findings per round, README |
| `data/eval/qa/` | Q&A questions and results |
| `data/cache/` | Every model reply; makes re-runs free. **Commit new entries** after a paid run |
| `data/feedback/`, `data/sessions/` | Engineers' verdicts from `di ask`; session workspaces. **Not committed** |

### Team rules
- **One branch per task**, from `main`. **Pull request** into `main`; CI green on Windows, macOS and Linux;
  Binjie approves; **squash merge**.
- **Before review:** pytest, ruff and pyright pass locally; for a new check, the 200-drawing sweep is read and the
  seeded gate holds.
- **Models:** Qwen only (`qwen3-vl-plus`, `qwen3.8-max`). Never call `gpt-6-astra` without asking Binjie.
- **Budget:** $8 for the project's API use; **ask before any paid run, with an estimate**; check `di telemetry`.
  Unit tests use fake models; paid tests are marked `@pytest.mark.live`.
- **Never commit** `.env` or API keys. Never edit `data/baseline/` or `data/labels/`, and never change an answer
  key to fit a result.
- **Don't edit the shared prompts** (`understanding/prompts/`, `review/prompts/`) without asking: a prompt change
  invalidates every cached reply and every past result. Adjust a rule's `llm_instruction` instead.
- `data/telemetry.db` conflicts: keep either side (`git checkout --theirs data/telemetry.db`).
- Decisions a new teammate would find surprising get a short ADR. Claude Code is welcome; review its diff like
  anyone else's.

Questions → Binjie.
