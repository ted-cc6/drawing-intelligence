# Spike C · Template Coverage

- **Status:** Complete (2026-10-13). Extraction run over all 1,171 client drawings + 4 samples.
- **Started:** 2026-10-13
- **Owner:** Binjie Wang
- **Related:** R6, R7 · A4 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** `spikes/spike_c_template_coverage/` (`coverage.py`, `title_block.py`, `check_proxy.py`,
  `summarise.py`, `plausibility.py`, `render.py`, `results/`)
- **Budget:** $0 (extraction only, no LLM calls)

---

## Outcome

- **Stage-1 extraction is robust across the whole client set.** All 1,175 files extracted with **0 exceptions**
  in 4.8 min; **every file has a text layer** (no scanned sheets); only **1 file (0.1%)** found no dimensions.
  The template regions, anchored to the sheet edges, crop the title block correctly from **A4 up to A0** without
  retuning. This clears R6's 2% trigger by a wide margin.
- **Round parts extract as well as prismatic** (0 crashes in both families). R7 is not supported at the
  extraction stage; it remains a question for stage-2 quality, not stage 1.
- **The "single template FR-DES-006-01" half of assumption A4 is false.** ~17% of sheets (203 files) carry an
  older/variant title block with different label wording (counting 12–13 of our 16 standard labels, or fewer).
  The "vector PDF with a text layer" half of A4 is **validated**.
- **A found cell is not a read value.** The proxy locates *some* text in a key cell on 99.7% of files, but
  graded for plausibility the fields split sharply: number, title and sheet size are real values on ~99.7–99.9%,
  scale on 96.9% (35 files truncated to `1 :`), but **material is a real value on only 13.4% — on 86% (1,016
  files) it is the placeholder `#`**, which is really printed on the sheet (also in SURFACE TREATMENT and
  MACHINING). The 4 A3 samples are **unrepresentative** here: all four carry a real material, so they hid both
  the `#` convention and the variant templates.
- **The Spike A note inflation is mostly real, not an extraction bug:** A2/A1 client sheets carry **bilingual
  English + French** notes plus multi-line material/finish/heat-treatment/tolerance blocks that the English-only
  A3 samples lack. A minority of "notes" are genuine misclassifications (stray text fragments).
- **Revisit when** stage 2 maps title-block fields (the variant templates need their own label set, and `#`
  must not be read as a material), or if new sheets appear that are rotated (1 seen) or exported to US Letter
  instead of A-series (1 seen).

---

## Question

Does extraction work across the whole client set — all 1,171 drawings, A0–A4, multi-page, prismatic and round?

Specifically:

1. How many files open and extract without an exception?
2. How many have a text layer (at least one dimension found)?
3. How many have the title block read correctly (key fields non-empty: number, title, material, scale, sheet size)?
4. How do these rates differ by part family and sheet size?
5. What are the main failure reasons?

## Decision It Unblocks

- **Risk R6** (template variations) and **R7** (round parts): re-score with evidence.
- **Assumption A4:** all client drawings are vector PDFs on FR-DES-006-01.
- **US-1.2, US-1.3, US-1.4:** which inputs must be rejected or fixed.

## Time Box

`[2]` hours

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [x] Every file in both client folders processed
- [x] Crash rate, no-text-layer rate and title-block failure rate, per family and sheet size
- [x] Failures grouped by reason, with 10 inspected by hand (4 imperfect files + 6 edge cases rendered)
- [x] R6 re-scored (trigger: failure rate above `[2]`%), R7 re-scored, A4 validated or not

## Method (planned)

1. Loop over `data/client_set/Generic Prismatic Parts/` and `data/client_set/Generic Round Parts (Pins, Shafts)/`.
2. For each PDF, call `drawing_intelligence.extraction.pipeline.extract_pdf(path)` **without `out_dir`** (no images written, no session, no telemetry). Catch every exception.
3. Record one row per file: family, file name, page count, page size, sheet size from the title block, dimension count, title-block fields found, warnings, exception type, seconds.
4. Write the full table to `out/` (git-ignored) and a summary by family × sheet size to `results/`.
5. Open `[10]` failing files by hand and group the failures by reason.

---

## Log

### Step 1 · Title-block proxy and its check (2026-10-13)

Stage 1 has no parsed title-block fields, so the proxy (`title_block.py`) works on geometry only, using the
text lines stage 1 places in the bottom-right `title_block` region:

1. **Labels.** Count how many of 16 fixed Wipro PARI labels (`MATERIAL`, `SCALE`, `SHEET SIZE`, `DRG./PART
   CODE`, …) appear as substrings of the region text.
2. **Values.** For five key fields (number, title, material, scale, sheet size), look for a value line in a
   small box anchored to **that label's** position — not to absolute page coordinates. Because the box follows
   the label, it still lines up when the same block is printed lower-right on a bigger sheet. Four fields print
   their value just below the label; the title prints to the right on the same row.
3. **Status:** `empty` (no region text) / `no_template` (< 8 labels) / `missing_values` (a key value missing) /
   `ok`.

**Check against the draft truth.** `check_proxy.py` compared the five values on the 4 samples with
`data/labels/title_block_truth.json` (a draft, `_verified: false`). After fixing the title anchor (two
`DESCRIPTION` labels exist; the revision-table one must be skipped), the proxy reproduced **20/20** key values
exactly and all 4 samples read `ok`. This check is **circular** (see Limits): the draft truth was built by
position from the same text layer and the offsets were tuned on these samples, so it shows self-consistency, not
correctness. The proxy is used for aggregate "is a cell present/plausible" rates (Step 6), not as ground truth.

### Step 2 · Trial run, 14 files (2026-10-13)

`coverage.py --trial` on the 4 samples + 5 prismatic + 5 round (seed 13): 0 errors, 2.2 s, all title blocks
`ok`. One round sheet measured 2404×1684 pt while its title block said A1 (nominal 2384×1684) — a ~20 pt
(≈7 mm) margin over nominal. The ISO-match tolerance was widened from 12 to **25 pt** so a border/bleed does
not read as a different size class; 25 pt is far below the √2 gap between adjacent ISO sizes, so no collisions.

### Step 3 · Full run, 1,175 files (2026-10-13)

`coverage.py` over `data/raw` (4) + Generic Prismatic Parts (639) + Generic Round Parts (532). **1,175 files,
0 errors, 286.6 s (4.8 min).** `git status` was clean before and after every run; only `out/` (git-ignored) and
`results/` changed. One CSV row per file is in `out/coverage.csv`; the tables below are in `results/`.

**Headline rates (`results/summary_by_family_size.csv`):**

| family | size | n | crash | no-dim | tb-fail | mismatch | med. dims | med. notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| prismatic | A0 | 3 | 0% | 0% | 0% | 0 | 81 | 74 |
| prismatic | A1 | 104 | 0% | 0% | 0% | 0 | 66 | 68 |
| prismatic | A2 | 486 | 0% | 0% | 0% | 0 | 22 | 37 |
| prismatic | A3 | 41 | 0% | 0% | 0% | 0 | 21 | 20 |
| prismatic | A4 | 1 | 0% | 0% | 0% | 0 | 13 | 19 |
| prismatic | mixed | 4 | 0% | 0% | 0% | 0 | 133 | 143 |
| round | A1 | 36 | 0% | 0% | 0% | 0 | 33 | 45 |
| round | A2 | 339 | 0% | 0% | 0% | 0 | 15 | 39 |
| round | A3 | 141 | 0% | 0.7% | 0.7% | 0 | 13 | 21 |
| round | A4 | 15 | 0% | 0% | 13.3% | 0 | 10 | 17 |
| round | non-standard | 1 | 0% | 0% | 0% | 1 | 6 | 25 |
| sample | A3 | 4 | 0% | 0% | 0% | 0 | 19 | 17 |
| **ALL** | **all** | **1175** | **0%** | **0.1%** | **0.3%** | **1** | **20** | **37** |

Sheet-size mix (client set): A2 dominates (825), then A3 (186), A1 (140), A4 (16), A0 (3), 4 mixed-page,
1 non-standard. Title-block label coverage across all files: **972** read 16/16, **116** read 13/16, **85** read
12/16, 1 read 9/16, 1 read 0/16 — i.e. **203 files (≈17%) use a variant title block**.

### Step 4 · The four imperfect files, inspected by hand (2026-10-13)

`render.py` wrote PNGs to `out/png/` (git-ignored). The only files that fail any check:

| file | family/size | symptom | cause (from the render) |
|---|---|---|---|
| `PRT84F150002001.pdf` | round A3 | 0 dims, title block empty | **Drawing rotated 90°**: portrait 842×1190 page holding a landscape drawing, `/Rotate` flag = 0, so all text is sideways and the title block sits up the left edge. The bottom-right region lands on empty border. |
| `PAA04A010002003.pdf` | round A4 | `missing_values`, 9/16 labels | **Older variant block** (`PARENT DESCRIPTION`/`PARENT CODE`, `FINISH MATRL. SIZE`). The **SCALE cell is genuinely blank** on the sheet, so a missing value is correct, not a bug. |
| `PAL54A025427001.pdf` | round A4 | `missing_values`, 12/16 labels | Same variant family; a key value not found in its box. |
| `PAV14B041624001.pdf` | round | `size_mismatch` (tb read `ok`) | Page is **US Letter** (612×792 pt), title block says A4 — the drawing was exported to Letter instead of A-series. Proxy still read all five fields. |

Edge cases also rendered and confirmed healthy: an A0 sheet (3370×2384) crops perfectly on the standard
template (16/16, `ok`); mixed-page prismatics and an A4 variant that reads `ok`.

### Step 5 · Side question — are A2 "notes" real? (2026-10-13)

Five A2 sheets rendered with every item classified as a `note` boxed in red (`render.py --notes`). The higher
count (A2 median 37–39 vs A3 samples 17) is **mostly real**: these sheets carry **bilingual English + French**
notes (e.g. `DEBURR ALL UNSPECIFIED…` / `ÉBAVUREZ TOUS LES TROUS…`) plus multi-line `MATERIAL/FINISH/
MACHINING/WEIGHT`, tolerance and heat-treatment blocks — each line counted separately — which the English-only
A3 samples do not have. A **minority are misclassifications**: stray text fragments over the drawing body boxed
as notes, because `classify.py` tags any item with ≥ 4 letters that is not a dimension or view label as a
"note". So the raw note count over-states real engineering notes; stage 2 should consolidate.

### Step 6 · Field plausibility — a found cell vs a real value (2026-10-13)

A reviewer noted that the proxy counts placeholders and truncations as reads. `plausibility.py` re-reads
`out/coverage.csv` (no re-extraction) and grades each key field **real / placeholder / missing / implausible**:
placeholder = `#` `-` `--` `---` `NA` `N/A` `NONE`; scale must match `d+(.d+)? : d+(.d+)?`; sheet size `A\d`;
the drawing number must look like a part code and, when the file name is itself a part code, be a prefix of it
(≈49 client files use descriptive names like the samples, so the prefix check is skipped there). Results in
`results/field_plausibility.csv`:

| field | real | placeholder | missing | implausible | real % |
|---|---:|---:|---:|---:|---:|
| number | 1171 | 0 | 1 | 3 | 99.7% |
| title | 1173 | 0 | 2 | 0 | 99.8% |
| sheet_size | 1174 | 0 | 1 | 0 | 99.9% |
| scale | 1138 | 0 | 2 | 35 | 96.9% |
| **material** | **158** | **1016** | **1** | **0** | **13.4%** |

- **Material is a real value on only 13.4%** — `#` fills 86%. By variant: `#` on 91% of standard(16) blocks and
  65% of variant(12–13) blocks, so `#` is the *standard* Wipro PARI convention, not a variant artefact.
- **Scale implausible on 35 files**: all `1 :` — the `1 : 1` value is split in the text layer and only `1 :`
  lands in the value box. A stage-1 text-merge nuance, not a drawing defect.
- **Number implausible on 3**: garbage tokens (`B`, `T+S`) read from two variant blocks, plus the rotated file's
  missing read. Everywhere else the number matches the part code.
- **By family:** material real 7.8% (prismatic) vs 19.5% (round); number/title/sheet-size ≥ 99.2% in both.

### Findings

- **Extraction does not break on the client set.** 0/1,175 crashes; 0 files without a text layer; 1 file with no
  dimension (the rotated sheet). The edge-anchored template regions handle A4→A0 unchanged.
- **Round == prismatic for stage 1.** No crashes in either family; the only no-dimension and both
  `missing_values` files happen to be round, but all trace to template/orientation, not to round geometry.
- **Title-block templates vary, and a found cell is not a read value.** ~17% of sheets use a variant block
  (older `PARENT …` layout; a 13-label variant), so the standard 16-label set does not describe all sheets. The
  proxy finds a cell value on 99.7%, but only number, title and sheet size are real values at that rate; scale is
  real on 96.9% (35 truncated `1 :`) and **material is real on just 13.4%** — `#` on 86%. "Reads five fields on
  99.7%" would have been wrong.
- **Two rare input shapes to reject or handle:** one 90°-rotated PDF (breaks dimensions and the title-block
  crop) and one US-Letter export (page/title-block size disagree). Each is 1 of 1,175 (0.09%).
- **The proxy is a proxy.** It confirms a title block is present and readable by position; it is checked against
  a *draft* truth for 4 samples only. Real field accuracy is stage 2's job.

### Implications (input, not the decision)

- **US-1.2 / US-1.3 (reject or fix inputs):** add a cheap orientation check (page portrait but content/title
  block not where expected) and flag non-A-series page sizes. These are the only inputs that need rejecting.
- **Stage-2 title-block prompt:** carry at least two label sets — the standard Wipro PARI block and the older
  `PARENT DESCRIPTION/FINISH MATRL. SIZE` variant — or let the LLM read labels by position rather than fixed
  strings. Do not assume 16 fixed labels. Treat `#`/`-`/`NA` as "not filled on this sheet", never as a material;
  a `#` material is not automatically a finding (see Still Open).
- **CI smoke test (R6 mitigation):** run extraction on one sheet of each size (A4, A3, A2, A1, A0) plus the
  rotated file as a known-hard case; assert 0 exceptions and a non-empty title block for the standard ones.
- **Note handling:** treat the stage-1 `notes` count as an upper bound; expect roughly double on bilingual A1/A2
  sheets, and let stage 2 merge multi-line and duplicate-language notes.

### Limits of this spike

- The title-block "read" is a geometric proxy, not parsed fields.
- **The check against `title_block_truth.json` is circular.** That draft truth was itself built by position from
  the same PDF text layer, and the proxy's value-box offsets were tuned on the same 4 A3 samples. Agreement on
  20/20 values therefore shows the offsets are self-consistent, not that the values are correct; it is not
  independent ground truth. (`_verified: false` in the file.)
- Value-box offsets were tuned on the A3 standard block. On variant blocks the proxy leans on the labels still
  matching; a value in an unexpected cell is missed (seen on the two A4 files).
- **64 files are multi-page; the title block was checked on page 1 only** (page count is recorded, and `mixed`
  flags a size change across pages). A title block on a later page was not examined.
- "No dimension found" uses the stage-1 classifier; a sheet could have dimensions the classifier misses without
  being counted here (not observed beyond the rotated file).
- The plausibility grades are shape checks, not correctness: a well-formed but wrong value (e.g. a scale of
  `1 : 1` that should be `1 : 2`) still grades `real`.
- Rates reflect this snapshot of `data/client_set/`; new drawings could add template variants not seen here.

### Still Open

- **For PARI/LatentView:** what does `#` in MATERIAL (and SURFACE TREATMENT and MACHINING) mean, and where is
  the material actually defined — on the parent/assembly drawing, in a BOM, or by the part code? This decides
  whether a `#` material is a finding, a "see parent" pointer, or simply ignored. It affects 86% of sheets.
- One PARI/LatentView question: are rotated exports and US-Letter exports expected in the real intake, or
  artefacts of this sample? That sets whether US-1.2 must handle them or merely reject them.
- Field-level title-block accuracy on the variant templates — deferred to stage 2 and its own eval.
- Whether to add the rotated and Letter files to a small "hard inputs" fixture for CI.
