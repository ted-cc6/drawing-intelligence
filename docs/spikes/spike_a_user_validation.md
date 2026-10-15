# Spike A · User Validation

- **Status:** Part 1 complete as a desk estimate (2026-10-13). The timed manual check, the [A]-tag review and the
  client replies are still open.
- **Started:** 2026-10-13
- **Owner:** Binjie Wang (PARI proxy)
- **Related:** R1 · A1, A2 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §5.3, §10
- **Throwaway code:** `spikes/spike_a_user_validation/` (`item_counts.py`, `time_model.py`, `results/item_counts.csv`)
- **Budget:** $0 (no LLM calls)

---

## Outcome

- **Manual check baseline: about 30 minutes for a drawing like the samples** (A3, one page, about 20 dimensions);
  90% range 22–43 minutes. A typical A2 prismatic drawing from the client set takes about **38 minutes** (27–54),
  a typical round part about **33 minutes** (24–46). This replaces the 25-minute guess in §5.3; the M5 baseline
  becomes 30 minutes and the target ≤ 15 minutes.
- **With the tool, about 14 minutes** (9–20), if it meets the M1 and M2 targets. The median ratio is 0.45 on the
  samples and 0.36 on a typical A2 prismatic drawing, so the M5 target (≤ 50%) is reachable but not guaranteed
  on small drawings (68% probability on the samples, 92% on typical client drawings). Keep the target.
- **A single unaided checker finds only about half the errors** (56% in the closest study; 40–80% across the
  inspection literature). The manual baseline is therefore the time for a pass that misses roughly half the
  errors, and the M1 target of 80% is above what one manual pass achieves.
- **Revisit when** the PARI proxy (or a PARI checker) times a real manual check of the 4 samples, or Spike C
  shows the note counts used here are inflated.

---

## Question

Does our picture of PARI's last point check match reality, and how long does a manual check actually take?

Specifically:

1. How long does a careful manual check of each of the 4 samples take, using the checklist categories?
   → **Estimated** (this document); measurement still open.
2. Which issues does a manual check find on each sample, and in which category? → **Open** (needs the timed check).
3. How long does each kind of item take (dimension, title-block field, note, standards lookup)? → **Estimated**
   from published operator times; see Step 2.
4. Are the [A]-tagged jobs (J5, J6, J13) and the provisional severity scale right? → **Open.**
5. What did the client say in reply to the requirements email? → **Open** (email not yet answered).

## Decision It Unblocks

- **M5 baseline** (§5.3): replaces the 25-minute estimate with a measurement.
- **M1 reference:** the manual findings show how many issues a careful human finds on the same drawings.
- **MoSCoW prioritisation** of the user stories.
- **Open items O1, O2, O7**; validates assumptions A1 and A2.

## Time Box

`[3]` hours. The desk estimate used about 2 hours; the timed check gets its own `[2]` hours when it can be done.

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [ ] All 4 samples checked by hand and timed, with split times per step — *replaced for now by the desk estimate below*
- [ ] An issue list per sample in the checklist columns
- [x] §5.3 of `01_discovery.md` updated — *with the estimated times; to be replaced by measured times*
- [ ] Every [A] tag confirmed or changed, with the reason
- [ ] Client replies (if any) logged against O1–O7

## Method (planned)

1. **Before looking at any tool output for a sample**, check it by hand and record each issue in the checklist
   columns.
2. Time the whole check, with split times per step.
3. Record each sample's time and issue list in the Log.
4. Re-read §1.1, §3 ([A]-tagged jobs), §4.3 and §5 as the PARI proxy; list what you would change.
5. When the client replies, log their answers per open item.

**Change (2026-10-13):** a hand check is not possible yet, so steps 1–3 are replaced for now by a desk estimate
from published research, real item counts and a Monte Carlo model (Log, Steps 1–7). Steps 1–5 above remain the
way to confirm it.

---

## Log

### Step 1 · How much is on a drawing? (2026-10-13)

`item_counts.py` runs the package's extraction (no LLM, no session) on the 4 samples and on 20 randomly chosen
drawings from each client folder (seed 13). All 44 files extracted without error.

| Set | Dimensions (median, IQR) | Notes (median, IQR) | Views (median) | Words on sheet (median) | Sheet size |
|---|---|---|---|---|---|
| 4 samples | 19.5 (18–27) | 17 (16–20) | 7 | 368 | all A3 |
| 20 prismatic | 24.5 (16–35) | 38.5 (33–53) | 2 | 468 | 17 × A2, 2 × A3, 1 × A1 |
| 20 round | 16 (12–21) | 31.5 (23–39) | 1.5 | 432 | 11 × A2, 6 × A3, 2 × A4, 1 × A1 |

Every sheet also carries about **14 title-block fields**. Words that appear on all 4 samples (the template's
fixed text) number **303**, so a sample has only **49–103 words of its own** (median ≈ 65).

*Caution:* the client drawings show about twice as many "notes" as the samples. Part of that may be text the
extractor classifies as notes on A2 sheets; Spike C will check. The estimate below is therefore given separately
for samples and client drawings.

### Step 2 · Method 1: bottom-up task model

**Model.** A careful check is a sequence of item checks. For a drawing with *D* dimensions, *N* notes,
*T* = 14 title-block fields, *L* = 3 standards look-ups and *F* real issues:

```
T_manual = k · ( O + D·t_dim + T·t_tb + N·t_note + L·t_lookup + H + F·t_write )
```

where *O* is overhead (open the files, orient, read the title block once), *H* the whole-sheet judgement (views,
GD&T, datums, manufacturability, design intent), and *k* a speed factor for the individual checker, shared by
every step.

**Unit times.** Each unit time is a triangular distribution (min, mode, max). The modes are built from
published operator times where they exist:

- Keystroke-Level Model (Card, Moran & Newell, 1980): mental preparation **M = 1.35 s**, point **P = 1.10 s**,
  click **B = 0.20 s**, keystroke **K = 0.20 s** (0.12 s good to 0.28 s poor typist), hands between mouse and
  keyboard **H = 0.40 s**.
- Silent reading: **238 words per minute** for non-fiction (Brysbaert, 2019).
- Visual search for one feature in one view: **≈ 2 s** — a team assumption, no published value used.

| Item | Mode built from | Mode | Triangular (s) |
|---|---|---|---|
| Dimension | find the feature in 2 views 2 × (M + 2 s) = 6.7 s; read value and tolerance ≈ 1 s; judge consistency and tolerance 2 M = 2.7 s; chain arithmetic for about a third of dimensions (M + 8 K + M) / 3 ≈ 1.4 s; note it M = 1.35 s → 13.2 s, rounded up for re-reading | 15 s | (8, 15, 40) |
| Title-block field | locate 2 s; read 1 s; compare with the rule M; cross-check with other fields M → 5.7 s, plus hesitation | 8 s | (3, 8, 20) |
| Note | read ≈ 5 words at 238 wpm ≈ 1.3 s; find the feature it refers to ≈ 3 s; judge 3 M ≈ 4 s → 8.3 s | 10 s | (4, 10, 30) |
| Standards look-up | open the document P + B + load ≈ 6 s; navigate 3 (M + P + B) ≈ 8 s; read ≈ 120 words of table at 238 wpm ≈ 30 s; compare M → ≈ 46 s, plus finding the right row | 60 s | (30, 60, 180) |
| Writing one issue in the 7 checklist columns | ≈ 140 characters × K = 28 s; 7 M = 9.5 s; 7 (P + B) = 9.1 s → 46.6 s | 45 s | (30, 45, 90) |
| Overhead *O* | team assumption | 2 min | (1, 2, 4) min |
| Whole-sheet judgement *H* | team assumption | 4 min | (2, 4, 10) min |
| Issues per drawing *F* | team assumption | 3 | (1, 3, 6) |
| Checker speed *k* | KLM typist range 0.12–0.28 s around 0.20 s, narrowed for experienced checkers | 1.0 | (0.75, 1.0, 1.5) |

**Analytic mean.** The mean of a triangular distribution is (min + mode + max) / 3. For the sample median
(D = 20, N = 17):

| Component | Mean (min) |
|---|---|
| Overhead | 2.3 |
| Dimensions 20 × 21.0 s | 7.0 |
| Title block 14 × 10.3 s | 2.4 |
| Notes 17 × 14.7 s | 4.2 |
| Look-ups 3 × 90 s | 4.5 |
| Whole-sheet judgement | 5.3 |
| Write-up 3.33 × 55 s | 3.1 |
| **Sum** | **28.8** |
| **× E[k] = 1.083** | **31.2** |

Using only the modes (every item at its most likely time, *k* = 1) gives 20.9 minutes; the mean is higher
because the distributions are skewed toward slow cases.

**Monte Carlo.** `time_model.py` draws every unit time independently (and *k* once per run) 100,000 times
(seed 13):

| Drawing | Mean (min) | Median | 90% range (p5–p95) |
|---|---|---|---|
| Cam Plate (D = 21, N = 16) | 31.2 | 30.6 | 22.0–42.5 |
| Sample median (D = 20, N = 17) | 31.2 | 30.6 | 21.9–42.5 |
| Round-part median (D = 16, N = 32) | 33.6 | 33.0 | 23.5–46.0 |
| Prismatic median (D = 25, N = 39) | 38.9 | 38.1 | 26.8–53.6 |
| Prismatic p75 (D = 35, N = 53) | 46.4 | 45.4 | 31.6–64.6 |

**Where the time goes.** For the sample median, dimensions take 24% of the mean, whole-sheet judgement 18%,
look-ups 16% and notes 15%. A ±50% error in the per-dimension time moves the estimate by about ±3.8 minutes.

### Step 3 · Method 2: inspection-rate cross-check

Document-inspection research recommends a careful checking rate of about **300 non-commentary words per hour**
(one "logical page"; range roughly 30–600), from Gilb & Graham (1993). *This figure is as reported in secondary
sources; it was not verified against the book.*

| Words counted | Time at 300 words/h | at 600 words/h |
|---|---|---|
| The sample's own words (≈ 65) | 13 min | 6.5 min |
| Every word on the sheet (368) | 74 min | 37 min |

The rate was set for prose and code, not drawings. Counting only a drawing's own words undercounts the work,
because one dimension "word" needs several geometric checks. Counting every word overcounts it, because the
template text is read once and not inspected. The two bound the estimate at **13–74 minutes**, and Method 1's
31 minutes falls inside.

### Step 4 · Method 3: practitioner benchmarks

- A mechanical-design practitioner with 20 years' experience (Sekkei Genba Lab, 2026) recommends allowing
  **15–30 minutes for a simple 2D detail drawing** and **30–60 minutes for a complex part with GD&T and multiple
  views**. The samples are simple detail drawings; the A2 client drawings with 25–35 dimensions sit between the
  two bands.
- A planning rule of thumb of **4 hours per sheet for "checking and drawing completion"** (planningengineer.net,
  seen in search results; the page blocked direct access) includes finishing the drawing, so it is not comparable
  and is not used.

### Step 5 · Triangulation

| Method | Sample-type drawing (A3, ≈ 20 dimensions) | Typical A2 prismatic |
|---|---|---|
| 1 · Bottom-up model | 31 min (22–43) | 38 min (27–54) |
| 2 · Inspection rate | 13–74 min | — |
| 3 · Practitioner benchmark | 15–30 min | 30–60 min |
| **Adopted baseline** | **30 min** | **38 min** |

The adopted baseline is the top of the practitioner range and the centre of the model. The model is the only
method that uses the drawings' own content, and the other two bracket it.

### Step 6 · How much does a manual check catch?

No study measures error detection on engineering drawings. The closest evidence is human inspection of other
structured documents:

- 33 people inspecting 44 real (not seeded) spreadsheets found **54 of 97 errors (56%)**, and 48% of the logic
  mistakes. Two spreadsheet audit tools usefully flagged 0.52% of the detection opportunities (Aurigemma &
  Panko, 2010).
- In the same paper's review: individual inspectors find **50–80%** of seeded spreadsheet errors; software
  engineers working alone find **40–60%**; a team inspection round finds **60–80%**.
- Inspection accuracy falls as working speed rises — a speed–accuracy trade-off found across seven industrial
  studies (Drury, 1973).

Assuming drawings behave like these documents: with the mode of 3 real issues per drawing, a single careful pass
finds about 1.7 and misses about 1.3. A faster check misses more.

### Step 7 · Assisted check (with the tool)

```
T_assisted = k · ( O + R + (F · recall / precision) · t_verify + S + F · recall · t_edit )
```

| Item | Triangular | Note |
|---|---|---|
| Read the summary *R* | (0.5, 1, 2) min | |
| Verify one reported finding *t_verify* | (15, 30, 90) s | location and evidence are given (J7) |
| Spot-check what the review did not cover *S* | (2, 5, 10) min | team assumption |
| Edit one accepted row *t_edit* | (10, 20, 40) s | the row is pre-filled |
| recall, precision | 0.8, 0.7 | the M1 and M2 targets |

| Drawing | Assisted median (p5–p95) | Ratio median (p5–p95) | P(ratio ≤ 0.5) |
|---|---|---|---|
| Sample median | 13.8 min (9.3–20.2) | 0.45 (0.31–0.64) | 0.68 |
| Round-part median | 13.8 min (9.3–20.3) | 0.42 (0.29–0.60) | 0.78 |
| Prismatic median | 13.8 min (9.3–20.2) | 0.36 (0.25–0.53) | 0.92 |
| Prismatic p75 | 13.8 min (9.3–20.2) | 0.30 (0.20–0.45) | 0.98 |

Mean assisted time is 14.1 minutes. Before the speed factor, it splits into spot-check 5.7, verifying findings
2.9, overhead 2.3, summary 1.2 and edits 1.0 minutes. The spot-check is the largest part, so **how much the
checker trusts the review matters more than precision**: dropping precision from 0.7 to 0.5 adds about 1.5
findings to verify, roughly 1.2 minutes.

### Findings

1. Manual check of a sample-type drawing: **≈ 30 minutes** (90% range 22–43); typical A2 prismatic ≈ 38 minutes;
   round part ≈ 33 minutes.
2. Three independent methods agree on the order of magnitude: the model sits inside both the inspection-rate
   bracket and the practitioner range.
3. Assisted check: **≈ 14 minutes**. The M5 target (≤ 50%) is met with 68% probability on small drawings and 92%
   on typical client drawings.
4. One manual pass is expected to find about half the errors.
5. The assisted time is dominated by the spot-check — that is, by trust — not by false alarms.

### Implications (input, not the decision)

- **§5.3 and M5:** baseline 30 minutes, target ≤ 15 minutes (≤ 50%). Done in `01_discovery.md` on 2026-10-13.
- **M1:** the 80% recall target is above a single manual pass (≈ 56%). When reporting M1, also report the PARI
  proxy's own recall on the same planted-error set, so the comparison is like for like.
- **Product:** the tool's biggest lever on M5 is reducing the spot-check. Reporting *not checked* categories
  clearly (US-1.1 AC3) and showing what was checked and passed (US-8.1 AC2) tells the checker where they don't
  need to look.
- **Larger drawings benefit more:** the tool's time is nearly flat while manual time grows with item count, so
  the pilot (M5 online) should include A2 client drawings, not only the A3 samples.

### Limits of this spike

- **Nothing was measured.** The unit times are built from published operator times plus team assumptions (visual
  search time, overhead, whole-sheet judgement, issues per drawing, spot-check). They have not been validated on a
  real check.
- **Detection rates come from spreadsheets and software**, not drawings.
- **Practitioner figures** come from one experienced practitioner's blog, not a study. The Gilb & Graham rate was
  taken from secondary sources.
- **Note counts on client drawings may be inflated** by extraction (Step 1).
- **Unit times are drawn independently** apart from the shared speed factor *k*. Real checks are more
  correlated: a difficult drawing slows every step. The true spread is probably wider than the 90% ranges shown.

### Still Open

- The timed manual check of the 4 samples by the PARI proxy (replaces Steps 2–5 with a measurement).
- An issue list per sample in the checklist columns (needed for the M1 human reference).
- Review of the [A]-tagged jobs and the severity scale.
- Client replies to the requirements email (O1–O7).

---

## Sources

- Card, S. K., Moran, T. P., & Newell, A. (1980). *The Keystroke-Level Model for User Performance Time with
  Interactive Systems.* Communications of the ACM, 23(7). Overview: https://en.wikipedia.org/wiki/Keystroke-level_model
- Brysbaert, M. (2019). *How many words do we read per minute? A review and meta-analysis of reading rate.*
  Journal of Memory and Language, 109.
- Aurigemma, S., & Panko, R. (2010). *The Detection of Human Spreadsheet Errors by Humans versus Inspection
  (Auditing) Software.* Proceedings of EuSpRIG 2010. https://arxiv.org/abs/1009.2785
- Drury, C. G. (1973). *The effect of speed of working on industrial inspection accuracy.* Applied Ergonomics,
  4(1). https://researchconnect.buffalo.edu/en/publications/the-effect-of-speed-of-working-on-industrial-inspection-accuracy/
- Gilb, T., & Graham, D. (1993). *Software Inspection.* Addison-Wesley. Checking-rate figure as reported in
  secondary sources, e.g. https://www.researchgate.net/publication/344267092_Chapter_8_Specification_Quality_Control
- Sekkei Genba Lab (2026). *Drawing Review Checklist: 6 Things You Must Never Miss.*
  https://sekkei-tech.com/2026/05/27/drawing-review-checklist-mechanical-design/
- Planning Engineer FZE. *How to calculate Engineering Working Hours.*
  https://planningengineer.net/how-to-calculate-engineering-working-hours/ (not used in the estimate; see Step 4)
