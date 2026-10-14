# Spike E · LLM Judgement

- **Status:** Complete (2026-10-13). 16-case test set, qwen3.8-max off/on, spend $1.50 of $2.
- **Started:** 2026-10-13
- **Owner:** Binjie Wang
- **Related:** R3, R4, R13 · R19 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** `spikes/spike_e_llm_judgement/` (`make_bases.py`, `build_cases.py`, `review_prompt.md`,
  `run_review.py`, `score.py`, `score_dedup.py`, `cases/`, `results/`)
- **Budget:** ≤ $`[2]`, Qwen only — **spent $1.50** (reviewer $1.481 + 2 base understandings $0.019)

---

## Outcome

- **The model finds the errors but cannot be trusted to judge.** Thinking-off qwen3.8-max caught **10/10**
  planted J5/J6 errors (100% recall), but on deduplicated findings its precision is only **32%–61%** (strict
  to lenient): it emits ~3.2 findings per drawing, many of them unfounded ("tolerance too tight" with no rule,
  material speculation, standard clearance holes called non-standard). So LLM reviewer findings must be
  **warnings to confirm, never an automatic *fail*** (R4), and noisy enough to need suppression (R3).
- **It does not apply numeric rules.** It flagged a near-miss hole at 8:1 depth/diameter in both runs *after
  computing "8:1"* — below the 10× limit. Numeric J5 checks (depth/diameter, stock size) belong in **code or
  lookups**, not the LLM.
- **It cannot be trusted to set severity.** It rated a benign, fully-specified heat treatment **Critical**.
  Severity must come from the **rulebook**, not the model.
- **Thinking-on is ruled out on cost, not quality.** It cost **~6.5× more and ~11× the latency (310 s/drawing)**
  — over the M4 budget intent — and was run without clean/near-miss controls, so its precision was not measured.
  Default the reviewer role to **qwen3.8-max, thinking off**. `gpt-6-astra` was not tested (budget).
- **Revisit when** the rulebook (Spike B) lands — numeric checks move to code, severity to the rulebook, and the
  LLM is measured again only on the open-ended judgement it is actually needed for.

---

## Question

Can a reasoning model catch manufacturability and design-intent errors (J5, J6) with valid evidence and few false alarms?

Specifically:

1. Of `[10]` planted J5/J6 errors, how many does the model catch?
2. How many findings does it raise on the unmodified drawings, and how many of those are real?
3. How many findings cite evidence that doesn't exist (what the verifier would drop)?
4. How much do model choice and thinking change the result and the cost?

## Decision It Unblocks

- **Risks R3 and R4:** whether LLM reviewers may raise *fail* findings or only *warnings to confirm*.
- **J5 and J6 priority** in MoSCoW: build now, or later.
- The model and thinking default for the reviewer roles.

## Time Box

`[3]` hours

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [x] `[10]` planted cases with answer keys written before any run (+ 4 clean, 2 near-miss; see integrity note)
- [x] Recall, precision and invalid-citation count per model setting (precision for off; on under-sampled)
- [x] Cost and latency per setting
- [x] R3 and R4 re-scored (trigger: precision below `[60]`%) — plus R13; see register diff

## Method (planned)

1. Plant errors in the **understood drawing JSON**, not the PDF — reviewers read JSON, so this is cheaper and fully controlled. Use saved understanding outputs for the 4 samples (the cache or a `DI_RETENTION=keep` run).
2. Write `[10]` cases (e.g. heat-treatment note missing for C-45, hole depth > 10 × diameter, thread to a shoulder without relief) with an answer key **before** running any model.
3. Write a throwaway reviewer prompt; ask for findings with category, evidence (dimension IDs / rule) and reasoning.
4. Run on the 10 planted cases and the 4 unmodified samples, with `qwen3.8-max` thinking off and on; `[2]` runs each.
5. Score recall, precision, invalid-citation count and cost.

---

## Log

### Step 1 · Test set and bases (2026-10-13)

Errors are planted in the **understood `DrawingKnowledge` JSON**, not the PDF (reviewers read JSON). 16 cases:
**10 planted** (5 J5 manufacturability, 5 J6 design-intent; 6 round / 4 prismatic; ≥ 3 error types each),
**4 clean controls**, **2 near-miss** (look suspicious but correct). Each case is one planted change from its
base; every `case.json` validates against the real schema. Bases: 4 reused free from
`data/baseline/understanding/qwen/` + **2 round parts generated** once (B5 `45K_TCP_PIN_SLEEVE` 20MnCr5, B6
`19500_COUPLING SPACER` C45) for **$0.019**. Planted errors are grounded in **PARI's own guidelines** (DES-11
material/heat-treatment, DES-12 plating) and the US-5/US-6 acceptance criteria, with public DFM references for
the generic machining rules (Sources). Answer keys (category, evidence ids, severity, rule + citation) were
written **before** any run.

*Schema note:* the saved B3 baseline carried feature types (`distance`, `thickness`) outside the current
`FeatureType` enum, so reused bases are normalised (unknown types → `other`). The saved baselines do not all
conform to the current schema.

### Step 2 · Reviewer and the budget correction (2026-10-13)

Throwaway reviewer (`review_prompt.md`): read only the JSON (delimited **as data, not instructions**), return
**strict JSON** findings with category (manufacturability | design_intent), severity, evidence ids, rule,
reasoning, correction; empty list if nothing is wrong. Model qwen3.8-max, role `review`. Telemetry and cache
are routed to `out/` (never `data/`); the cache is **off** for the runs (temp 0 would make run 2 a cache hit),
and the runner is resumable so a re-run never double-charges.

A 1-case dry run (J6-1, off) cost $0.0117. The projection used a 2.4× thinking multiplier — **wrong**: the
first real thinking-**on** calls used **~13,000 reasoning tokens each (~$0.09/call, ~7×)**, projecting the full
64-call matrix to **$3.30**, over budget. The run was stopped (`TaskStop`) and re-planned: **off on all 16
cases × 2 runs; on once on the 10 planted cases only** (clean/near-miss covered by off), with a hard
`$1.90` guard. Final spend **$1.481** reviewer + $0.019 bases = **$1.50**. `git status data` was clean before
and after every run.

### Step 3 · Scores per setting (2026-10-13)

`results/scores_by_setting.csv` (raw, before dedup/labelling):

| setting | recall | findings/call | invalid citations | stability | avg cost | avg latency |
|---|---|---|---|---|---|---|
| **off** | **100%** (10/10) | 3.2 | 12 / 102 | 40% | $0.013 | 29 s |
| **on** | 85% (11/13)† | 2.2 | 2 / 29 | 56% | $0.083 | 310 s |

† on was run **1 run on 7 of 10 cases** (2 on the other 3) and with **no clean or near-miss controls**, so its
precision and false-alarm rate were **not measured**. Thinking-on is ruled out on cost/latency regardless (M4).

### Step 4 · Deduplicated, labelled precision — thinking off (2026-10-13)

The raw precision double-counts: one base (B5) underlies 6 cases, so its pre-existing issues recur. Findings
are deduplicated to **one per (base, category, theme)** and labelled by theme (fixed labels, below), then
precision is a **range**: strict (unclear = false) to lenient (unclear = real). `results/precision_dedup.csv`,
`results/findings_labeled_dedup.csv`.

| theme | n | label | in J5/J6 precision? |
|---|---|---|---|
| planted error detected | 10 | real | yes |
| B · title-block HT `---` vs note (consistency) | 2 | real (severity → Minor) | yes |
| C · other Ø30/Ø20/Ø66 "untoleranced" | 4 | unclear (IS 2102 applies) | yes |
| G · GD&T symbol interpretation | 1 | unclear | yes |
| Z · other | 6 | unclear | yes |
| D · Ø6.4/Ø8.4 "non-standard drill" | 2 | **false** (M6/M8 clearance) | yes |
| F · material/treatment speculation | 5 | **false** | yes |
| H · "tolerance too tight", no rule/evidence | 6 | **false** (§4.1) | yes |
| Z2 · thread relief on an M5 *tapped* hole | 2 | **false** | yes |
| A · garbage note `YFYFGHYFGHGF` | 2 | real, **out of scope** (J3) | no |
| E · misspelling / bad hardness string | 1 | real, **out of scope** (J3) | no |
| Z1 · bore `+0.2` with no nominal | 1 | **understanding artefact** | no |

**In-scope distinct findings: 38 — real 12, unclear 11, false 15.**
**Precision: 32% (strict) to 61% (lenient).** Even lenient, ~40% of distinct findings are false alarms.

### Step 5 · Integrity of the answer keys (2026-10-13)

- **`build_cases.py` was re-run after the review calls** (`expected.json` mtime 18:40, post-run), to refresh two
  DFM citation URLs. Only the `rule`/citation text changed; **category, evidence and severity were fixed before
  the run and unchanged**, and the scorer ignores `rule`, so results are unaffected. The reviewer reads
  `case.json` (independent of `expected.json`), and the post-run rebuild reproduced `case.json` byte-identically.
- **Two keys differ from the checkpoint-1 proposal:** J5-3 (sharp corner) and J5-4 (tight tolerance) had their
  base drawings swapped (J5-3 → B1 cam plate, J5-4 → B4 block) and the tight-tolerance value changed ±0.005 →
  ±0.003. This was decided **at build time, before any review call** (shown in the checkpoint-2 manifest), not a
  post-hoc edit.

### Findings

- **Recall is excellent, precision is poor.** off caught every planted error (10/10) but, deduplicated, scores
  **32–61%** precision; it raises ~3.2 findings per drawing. The failure mode is over-reporting, not blindness.
- **The false alarms are real false alarms.** The largest false themes are "tolerance too tight" with no rule or
  functional evidence (6), material/treatment speculation (5), standard M6/M8 clearance holes called
  "non-standard" (2), and thread relief demanded on a tapped hole (2). These are confident and plausible-looking
  — exactly what a verifier that only checks citations would pass (R4).
- **Citations are mostly valid; reasoning is the weak point.** Only 12/102 (off) findings cited an id not in the
  input. So **R4 is the live risk, not invalid citations**: wrong judgement with a valid citation.
- **It does not do arithmetic rules.** NM-1 (a Ø5 × 40 hole, 8:1) was flagged in both runs *after the model
  wrote "8:1"* — below the 10× limit. The model treats "deep-ish" qualitatively.
- **It over-rates severity.** The benign title-block-vs-note HT inconsistency was rated **Critical** (off, both
  runs). Severity cannot come from the model.
- **Its most frequent *real* extra finding is a title-block consistency issue** (HT field `---` vs a note that
  specifies the treatment) — a J2/J3 matter it reports as design_intent, and it over-rates it. This ties to R19
  (title-block handling) and argues for a dedicated consistency/title-block check rather than leaving it to the
  judgement reviewer.
- **Run-to-run stability is 40%** (off, 2 runs) — the same drawing yields different findings each run (R13).
- **Thinking-on: ~6.5× cost, ~11× latency, quality not measured.** 310 s/drawing alone rules it out under M4.

### Implications (input, not the decision)

- **LLM reviewer findings are *warnings to confirm*, never *fail*** (R4 contingency becomes the default), shown
  below Critical/Major code findings, with per-rule suppression (US-11.2) for noisy themes.
- **Move the numeric J5 checks to code/lookups:** depth/diameter (US-5.1 AC1), stock size (US-5.2), general
  tolerance vs a capability table. The LLM keeps only the open-ended judgement (sharp corners, "does this make
  sense") as warnings.
- **Severity comes from the rulebook** (O2), not the model; the reviewer proposes a category and evidence, the
  rulebook sets severity.
- **Add a dedicated consistency / title-block check** (title-block field vs note, J2/J3) so the judgement
  reviewer is not the one surfacing — and over-rating — those.
- **MoSCoW for J5/J6:** *Should* — J6 material/treatment-vs-guideline checks (grounded in DES-11/12, high value,
  the model gets these) and the code-based J5 numeric checks. *Could* — open-ended LLM manufacturability/
  design-intent judgement, as suppressible warnings only.
- **Reviewer default:** qwen3.8-max, **thinking off**.

### Limits of this spike

- **The same assistant designed the cases, the planted errors and the labels, and ran the model.** Planted
  errors may be easier to catch than real ones (R8; Spike F rates realism). The precision labels are judgement
  calls; the range (strict/lenient) brackets the unclear ones.
- **Precision was measured for thinking-off only.** On had no clean/near-miss controls and fewer runs, so its
  precision and false-alarm rate are unknown.
- **One model, one prompt, one temperature (0).** No `gpt-6-astra` (budget), no prompt tuning. A better prompt
  (e.g. "only flag what a named rule supports") might cut false alarms a lot — untested.
- **Small set** (16 cases, 6 bases), and the bases are a mix of real pipeline output and reused baselines; two
  pre-existing data issues (a garbage note, a dropped bore nominal) came from the understanding, not the drawing.
- Precision depends on the labels (Step 4); they are recorded in `results/findings_labeled_dedup.csv` for review.

### Still Open

- Whether a stricter prompt ("cite a specific rule or do not report") raises precision enough to narrow the
  warnings — worth one cheap follow-up within budget.
- `gpt-6-astra` recall/precision for the reviewer role (needs approval + budget; ~50× cost).
- A **PARI convention question:** is a title-block heat-treatment field of `---` with the treatment given only
  in a note acceptable (it is common here), or a defect? It drives whether the consistency check fails or passes.
- Severity definitions (O2) — needed before any finding can be shown as *fail*.

### Sources

- PARI PRD-GD-DES-11, *High Carbon & Alloy Steel Material Selection* (client guideline, `data/client_set/WP
  Specific Guidelines/`), read 2026-10-13 — heat-treatment per material; standard round-bar stock sizes.
- PARI PRD-GD-DES-12, *Surface Treatment / Plating Process Selection* (same folder), read 2026-10-13 — hard
  chrome requires a hardened surface (≥ 45 HRC), radiused not chamfered corners.
- JLCCNC, *CNC Machining Design Guideline*, https://jlccnc.com/help/article/CNC-Machining-Design-Guideline —
  internal corner radius ≥ cutter radius; read 2026-10-13.
- Xometry, *ISO 2768*, https://www.xometry.com/resources/certifications/iso-2768 — general tolerance classes
  (fine 6–30 mm = ±0.1 mm); read 2026-10-13.
