# Spike D · Symbol Recognition

- **Status:** Complete (2026-10-15). 10 drawings / 13 pages, qwen3-vl-plus off (all pages) and on (5 pages: the 4 samples + the dunnage plate).
- **Started:** 2026-10-15
- **Owner:** Binjie (with Claude Code)
- **Related:** R5 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** `spikes/spike_d_symbols/` (`answer_key.py`, `run_understand.py`, `score.py`, `results/`)
- **Budget:** ≤ $`[1]`, Qwen only · **Spent:** $0.419 logged (off $0.223 + on $0.196), plus any timed-out calls the provider billed (not visible in our logs)

---

## Outcome

- **The vision model does not read symbols from the image.** With thinking off, qwen3-vl-plus found **0 of 32**
  surface-finish marks and **0 of 9** datum flags, and **16 of 39** GD&T frames (41%). It named the right
  characteristic for only **5 of those 16**. On 4 of the 6 drawings that carry symbols it reported none at all.
  Phantoms were low (2 of 18 GD&T reports, 11% — both datum letters filed as GD&T; none on the 4 symbol-free
  samples outside the title block), but the miss rate makes vision symbols unusable for *fail* findings (R5).
- **What it did find came from the text, not the pixels.** Every matched GD&T frame has a bbox identical to the
  extraction's text bbox. Solid Edge writes each feature control frame as a text line in the
  `SolidEdgeANSI1Symbols` font (`n 0.05 A` = ⊥ 0.05 | A); stage 1 passes those lines through undecoded, and the
  model sometimes guesses what the letters mean — mostly wrongly.
- **Q4 answered: yes, from text and vectors, at $0.** GD&T frames are **exact** from the text layer once the
  glyph font is decoded (11 glyphs mapped, verified by rendering); **745 of 1,175** client drawings have at least
  one frame. Datum flags (boxed letter / filled triangle) and finish marks ("VV" triangles, "√Ra" check marks)
  are found by simple vector-geometry detectors — 5/9 datum flags were found and 32/34 finish candidates were right before
  the manual review. Weld symbols could not be tested: **none of the 10 drawings has a drawn weld symbol** —
  welds are specified in notes.
- **Thinking on is ruled out on latency.** It averaged **454 s and ~24k output tokens per page** (4× the latency, 3.5× the output of off). Three of seven attempted pages stalled for 25–30 min or timed out, so it was measured on only 5 pages. There it found one datum flag that off missed. It also found fewer GD&T frames (2/4 vs 4/4, with no characteristic named) and 0 of 2 finish marks. Not worth the latency.
- **Revisit when** a drawing set with drawn weld symbols is available, or a different vision model is
  proposed; otherwise symbols come from text + vectors and vision only fills gaps as *warnings to confirm*.

---

## Question

How reliably does the vision model read symbols that exist only in the image — GD&T frames, datums, surface-finish and weld symbols?

Specifically:

1. On `[10]` drawings, how many symbols of each type are really there (counted by hand)?
2. How many does the model report that aren't there (phantoms), and how many does it miss?
3. Does thinking on vs off change this?
4. Can any symbol type be found from PDF vector paths or text instead of the image?

## Decision It Unblocks

- **Risk R5:** whether symbol-based findings can be *fail* or only *warnings to confirm*.
- **US-4.2, US-4.3:** how the GD&T and weld checks are built.
- The understanding model default (task A1) gets a symbol-accuracy number.

## Time Box

`[3]` hours

- **Rule if the limit is reached:** stop, record what is known, and carry unresolved questions into the risk
  register as open risks.

## Success Criteria

The spike is done when all of the following hold:

- [x] Hand counts for `[10]` drawings, per type — as a reviewed answer key, not a blind hand count (see Limits)
- [x] Phantom and miss rates per symbol type and thinking setting (on: 5 pages: the 4 samples + the dunnage plate)
- [x] R5 re-scored (trigger: phantom rate above `[10]`%) — see register diff
- [x] A recommendation: which symbol types can support *fail* findings

## Method (planned)

1. Pick `[10]` drawings: the 4 samples plus `[3]` prismatic and `[3]` round parts that visibly contain symbols.
2. Count symbols by hand, per type and per page. Coordinate with whoever owns `data/labels/symbol_counts.json` (task A1) — keep your counts in `spikes/spike_d_symbols/results/` and don't edit `data/labels/` yourself.
3. Run understanding with `qwen3-vl-plus` (thinking off and on) through the package functions; save the replies in `out/`.
4. Compare per type: correct, phantom, missed.

---

## Log

### Step 1 · How symbols are stored in the PDFs (2026-10-15)

A scan of all 1,175 PDFs (text layer + fonts) showed the `SolidEdgeANSI1Symbols` font on 1,107 files. Besides
`O` (= ⌀, already remapped in `wipro_pari.yaml`), its glyphs were decoded by rendering crops around examples:

| glyph | meaning | glyph | meaning |
|---|---|---|---|
| `r` | ▱ flatness | `a` | ◎ concentricity |
| `t` | — straightness | `d` | ⌯ symmetry |
| `n` | ⊥ perpendicularity | `^` / `_` | ↗ circular / ↗↗ total runout |
| `i` | ∥ parallelism | `l` | ⌖ position |
| `j` | ⌭ cylindricity | `h` | ⌒ profile of a line |
| `u` | ± | `v` | ° |
| `` ` `` | ↧ depth | `q` | □ square |

So each feature control frame is one text line: glyph + tolerance + datum letters. 745 of 1,175 drawings have at
least one frame (380/643 prismatic, 365/532 round); **the 4 A3 samples have none**. Surface-finish marks, datum
flags and weld symbols are vector lines only (every line is its own path, no grouping). N-grade text (`6 N9`)
appears on 38 round parts; "WELD" text on 120 files is almost all boilerplate notes ("WELD CLASS : B IF
APPLICABLE").

### Step 2 · Drawings and answer key (2026-10-15)

Drawings (near-duplicate RH/LH variants skipped): the 4 samples (GD&T phantom controls); prismatic
`P23Y5B096056002` (A2), `10K_DUNNAGE DOOR LM BLK MTG PLT_01` (A3), `P23Y5B076198001` (A1, 2 pages, fabrication);
round `P23Y5B071019001` (A1, densest), `PRF83A106004002` (A3, older PARI template), `PRT84S103156003` (A2, 3 pages,
fabrication). 13 pages.

The answer key (`answer_key.py`, free) merges three sources:

1. **GD&T** — exact, from the symbol-font text lines (type, tolerance, datum references, bbox).
2. **Datum flags and finish marks** — candidates from vector geometry: a single capital letter inside a drawn box
   or next to a filled equilateral triangle; clusters of stroked equilateral triangles ("VV" marks); an Ra value
   (0.1–50) next to two strokes meeting at ~60° with one arm ≥ 1.5× the other ("√"). Template regions skipped.
3. **Manual review** — every page overlay was inspected by eye (`out/answer_key/*.png`); corrections with reasons
   in `results/manual_labels.json`: +4 datum flags missed by the detector (boxed letters attached under frames,
   one flag ~30 pt from its triangle), −2 revision triangles (Δ1) on the older-template sheet that the template
   regions don't mask.

Counting rule: every √ is one symbol (`50√(12.5√)` = 2); note-level symbols count; title-block template marks
(e.g. the "VV" in the MACHINING field, the projection symbol) do not.

| | GD&T | datum | surface finish | weld |
|---|---|---|---|---|
| 4 samples | 0 | 0 | 0 | 0 |
| P23Y5B096056002 | 7 | 2 | 2 | 0 |
| 10K_DUNNAGE … PLT_01 | 4 | 1 | 2 | 0 |
| P23Y5B076198001 (2 p) | 0 | 0 | 8 | 0 |
| P23Y5B071019001 | 14 | 3 | 10 | 0 |
| PRF83A106004002 | 8 | 2 | 4 | 0 |
| PRT84S103156003 (3 p) | 6 | 1 | 6 | 0 |
| **Total** | **39** | **9** | **32** | **0** |

### Step 3 · Model runs (2026-10-15)

`run_understand.py` calls `extract_pdf()` + `understand_page()` directly; cache and telemetry in `out/`; resumable
with a hard $0.95 guard. A 1-page dry run cost $0.011. **Thinking off, all 13 pages: $0.223, 110 s/page, ~6.8k
output tokens/page.** Thinking on, first page (CAM PLATE): $0.045, 347 s, 28k output tokens. The remaining samples
took 303–980 s each (CYLINDER ROD needed one SDK retry after the default 600 s timeout). P23Y5B096056002
timed out three times (3 × 600 s) and ended the run.
A retry with `DI_API_TIMEOUT_S=1200` on the three densest drawings finished the dunnage plate (311 s) and then
stalled on PRF83A106004002 for more than 25 min. A watchdog stopped it, as agreed. Pages
completed with thinking on: the 4 samples (303–980 s each) and the dunnage plate. **Thinking on, 5 pages: $0.196,
454 s/page, ~24k output tokens/page.**
`git status data` stayed clean (nothing written to `data/`).

### Step 4 · Scores (2026-10-15)

`score.py` → `results/scores.csv`, `results/per_page.csv`. A model symbol is *correct* when it matches an unused
answer-key symbol of the same type on the same page within 60 pt (bbox centres); model symbols inside template
regions are counted separately (`template`), not as phantoms.

| setting | type | key | model | correct | phantom | missed | char. right |
|---|---|---|---|---|---|---|---|
| off | GD&T | 39 | 18 | 16 | 2 (11%) | 23 (59%) | 5 / 16 |
| off | datum | 9 | 0 | 0 | 0 | 9 (100%) | — |
| off | surface finish | 32 | 0 | 0 | 0 | 32 (100%) | — |
| off | weld | 0 | 0 | 0 | 0 | 0 | — |
| on (5 p) | GD&T | 4 | 2 | 2 | 0 | 2 | 0 / 2 |
| on (5 p) | datum | 1 | 1 | 1 | 0 | 0 | — |
| on (5 p) | surface finish | 2 | 1 | 1* | 0 | 1 | — |
| on (5 p) | weld | 0 | 0 | 0 | 0 | 0 | — |

\* Not a real hit. The model filed the flatness frame (`r0.05`, same bbox as the text) as `surface_finish 0.05`. It
matched the real "VV" mark only because of the 60 pt radius. Counted honestly, on found 0/2 finish marks. On the same page,
off found 4/4 frames, 0/1 datum and 0/2 finish marks.

Per drawing (off): DUNNAGE 4/4 frames, P23Y5B071019001 12/14 (+ datum letters B, C filed as GD&T), the other
three drawings with frames 0/7, 0/8, 0/6. Template-region reports: 9 (tolerance-table and title-block labels
filed as `other`, one as `surface_finish`). Characteristic errors: ◎ reported as "⌀", ⌯ as "⌀", ▱ as "□", — as
"∥" — the model is guessing the meaning of the undecoded glyph letters.

### Findings

- Vision recall for symbols is near zero: 0% datum flags, 0% finish marks; GD&T 41% and only from the text.
- All 16 matched GD&T bboxes are identical to the extraction text bboxes (distance 0) → the "detections" are
  text reads.
- Phantoms in the drawing area are rare (2, both mis-typed datum letters); most noise is template text filed as
  symbols.
- GD&T is fully recoverable from the text layer; datum flags and finish marks largely from vector geometry.
- Thinking on: On 5 pages, thinking on cost 4× the latency. It found the one datum flag that off missed, but fewer frames (2/4) and no finish marks. On the 4 samples it reported no symbols in the drawing area (only title-block marks).

### Implications (input, not the decision)

- **Decode the glyph font in stage 1** (`glyph_remap` in `config/templates/wipro_pari.yaml`, 13 more glyphs) and
  parse frames into structured GD&T (characteristic, tolerance, ⌀ modifier, datums). This makes US-4.2 GD&T checks
  deterministic and lets them raise *fail* findings.
- **Add vector detectors for datum flags and finish marks to stage 1** (port `answer_key.py`'s detectors with
  tests); emit them with `source: "vector"`. Datum flags need the boxed-letter rule plus the attached-to-frame
  case.
- **Stop asking the vision model for symbols** (or only for types the detectors cannot see), and treat any
  vision-only symbol as a *warning to confirm*.
- Keep `qwen3-vl-plus` thinking **off** for understanding.
- Weld checks (US-4.3) are note-based on this client's drawings; parse weld notes rather than symbols until
  drawings with drawn weld symbols appear.

### Limits of this spike

- The answer key is a **reviewed silver standard**, not a blind hand count: GD&T is exact; datum and finish
  counts are detector output corrected by one visual review (Claude Code), still to be spot-checked by a human
  (overlays in `out/answer_key/`).
- 10 drawings, 13 pages, one run per setting; no run-to-run variance measured.
- Weld: 0 symbols in the set, so only weld *phantoms* were testable.
- The 4 samples contain no GD&T, datum flags or finish marks — they test phantoms only.
- Thinking on: Measured on 5 pages only (4 symbol-free samples + 1 drawing with 7 symbols). The 3 densest drawings stalled or timed out, so the setting has no symbol-recall number on dense sheets.
- Calls that timed out may have been billed by the provider; they are not in the logged spend.

### Still Open

- Human spot-check of the datum/finish answer key (≈5 min per drawing using the overlays).
- Do drawn weld symbols exist anywhere in the client set? (`Welding Notes & Symbols.pdf` in the prismatic folder
  is a reference sheet, not a part.)
- Older/variant templates (17% per Spike C) need their own template regions so revision triangles and title-block
  marks are masked.
