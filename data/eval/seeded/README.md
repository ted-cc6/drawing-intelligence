# Planted-error drawings (A5a)

The client has no drawings with labelled errors, so we made our own: copies of the four samples in `data/raw/`
with one known mistake planted in each. They measure the review (recall: planted errors caught; precision:
findings that are real). Zhetao's `di eval review` (A5b) runs on them.

**28 cases:** 22 planted, 2 near-miss (a change that is still correct and must not be flagged) and 4 clean
(unchanged samples, to count false alarms).

## Files

Each case folder `<case>/` holds:
- `<case>.pdf`: the drawing. The planted value is written in the sample's own font, size and position, so it looks
  like the original; dimension lines and other line art are kept.
- `case.json`: what the seed script changed and where (visual page coordinates, PDF points).
- `expected_findings.json`: the **answer key**, written by hand from the approved case list before any reviewer
  existed. Never change a key to fit a reviewer's output; if a key is wrong, fix it on its own, with a reason.

Rebuild the drawings with `uv run di eval seed` (or `--only <case>`); the output is byte-identical, and the
script stops if an edit would remove any other text. The cases are defined in `CASES` in `src/drawing_intelligence/eval/seed.py`. Load the keys with
`load_answer_keys()` in `src/drawing_intelligence/eval/answer_key.py`, whose docstring defines the format.

## The cases

Category, severity and result come from the rule in `config/rules/` (an `llm` rule can only give a warning).

| Case | Sample | Planted change | Rule | Category / severity | Result |
|---|---|---|---|---|---|
| P01 | CAM | Overall `100` → `105`: the chain 35 + 30 + (35) no longer adds up | CN-001 | consistency / critical | fail |
| P02 | HOSE | Reference `(24)` → `(26)`: 24 + 32 + (26) ≠ 80 | CN-004 | consistency / major | fail |
| P03 | CAM | Boss height `15` → `17`; the other boss, drawn equal, stays `15` | CN-002 | consistency / critical | fail |
| P04 | BLK | Overall `100` → `3.94"` on a metric drawing | HNF-005 | consistency / major | fail |
| P05 | BLK | Hole callout `2-⌀6.4` removed | MX-001 | consistency / critical | warning |
| P06 | CAM | Slot height `20` removed | MX-002 | consistency / critical | warning |
| P07 | BLK | Drawing number removed | TB-001 | title_block / critical | fail |
| P08 | CAM | Material `M.S.` removed | TB-012 | title_block / major | fail |
| P09 | CYL | Surface treatment `I.Z.B.P. (TRIVALENT)` removed | TB-013 | title_block / major | fail |
| P10 | CAM | Checked date `01/10/2025` → `25/09/2025`, before the drawn date | RQ-001 | title_block / minor | fail |
| P11 | HOSE | Title-block scale `1 : 1` → `2 : 1`; the views say SCALE 1:1 | TB-006 | title_block / minor | fail |
| P12 | BLK | Revision `00` → `01` with an empty revision table | TB-004 | title_block / critical | fail |
| P13 | CAM | `⌀ 16 H7` upper limit `+0.018` → `-0.018` (below the lower limit) | RQ-002 | tolerance / major | fail |
| P14 | CAM | `28.5±0.1` → `28.500±0.1` | LY-005 | tolerance / major | fail |
| P15 | BLK | `70±0.2` → `70±0.002` | TL-003 | tolerance / minor | fail |
| P16 | CYL | Heat-treatment note and its frame removed; the field still says `REF NOTE` | RQ-003 | surface_treatment / major | fail |
| P17 | CYL | `TOUGHENED` → `TEMPERED` (tempering with no hardening) | WST-126 | surface_treatment / minor | fail |
| P18 | HOSE | Heat treatment `---` → `HARDENED 40-45 HRC` on a polyurethane part | WST-123 | surface_treatment / major | fail |
| P19 | CAM | `H7 (+0.018/0)` removed from the ⌀ 16 locating bore | TL-002 | design_intent / critical | warning |
| P20 | CAM | Internal corner `R 8` → `R 0.2` | MC-001 | manufacturability / major | warning |
| P21 | CAM | Surface treatment → `HARD ANODIZING` on an M.S. part (aluminium only) | WPS-002 | surface_treatment / major | fail |
| P22 | HOSE | Surface treatment `N.A.` → `I.Z.B.P. (TRIVALENT)` on a polyurethane part | WPS-002 | surface_treatment / major | fail |
| N01 | CYL | `24-32 HRC` → `28-32 HRC`, still inside PARI's C45 toughening range | none | — | — |
| N02 | BLK | `70±0.2` → `70±0.1`, tighter but ordinary | none | — | — |
| C01–C04 | all four | unchanged | none | — | — |

Samples: CAM = `10K_CAM PLATE`, CYL = `10K_CYLINDER ROD MTG_02`, HOSE = `20_INCH HOSE PIPE CLAMP_PU_01`, BLK =
`31K_PIPE CLAMP BLK_02`. By category: consistency 6, title block 6, tolerance 3, surface treatment 5, design intent
1, manufacturability 1. Not covered yet: thread / weld, GD&T, datum, inspection, material naming (the four samples
have no thread callouts, GD&T frames or datum flags; a later round could seed client-set drawings that do).

## Reading the answer key

- `expected`: the planted error. A finding catches it when it has the key's rule (or one in `also_acceptable`)
  and cites some of the key's evidence. `also_acceptable` lists other rules the same change really breaks (P01's
  105 also no longer matches the drawn length, DSM-023): a finding under one of them is not a false alarm.
- `must_not_flag` (N01, N02): rules that must stay quiet on that evidence.
- `pre_existing`: issues already in the client's original, repeated in every case built from it. Finding them is
  right, but it does not catch the planted error. Suggestion for A5b: score a planted case on what it adds over
  its clean twin (same sample), and score the clean cases against `pre_existing`.
- Evidence uses the ids of the **seeded** PDF's extraction. A removed dimension shifts the ids after it (P05,
  P06), and `3.94"` in P04 is not classed as a dimension, so it is `text` evidence. A removed item is a `region`
  (or a `title_block` field with no quote) at the place it was. Notes are `text` evidence with their quote.

**Issues in the originals** (`pre_existing`): TB-016 on all four (checked and approved dates are filled in, as on
any released drawing); CYL's `11` printed `-0.2` above `-0.1` (RQ-002, to confirm with PARI); HOSE's
`Polyurethene` (MF-011) and its untoleranced `34.97` and `49.97` (LY-005, possibly intended); BLK's `PAINTING`
with no colour code (MF-013).

Added 2026-10-25, after the LLM reviewers raised it: the H7 holes on CAM (`⌀ 16 H7`) and CYL (`⌀8 H7`) are
zinc plated (I.Z.B.P., 8-12 µm per PARI DES-12) with no allowance for the plating, which can take up the whole
18 µm H7 band (WPS-004). It is in the original drawings, so it is `pre_existing` in every case that keeps both the
H7 hole and the plating (not P09, P19 or P21). Confirmed as a real issue by the PARI proxy; the planted errors
are unchanged.

## Notes for the reviewer builders

- **WST-123** (P18): its `non_metals` list has no polyurethane, and the samples spell it `Polyurethene`.
- **TL-003** (P15, N02): its `ratio` is not set yet. P15 is about 150× tighter than the general tolerance, N02
  about 3×. Every CYL case also has `20±0.02` (about 10×), not listed as an issue.
- **NM-001**: its params say `UNSP. RADII` and `UNSP. CHF`; the template prints `UNSP.RADII` and `UNSP.CHF.`.
- The extraction does not mark CAM's `(30)` (D11, vertical) as a reference dimension.
- Every sample prints SURFACE AREA in `in^2`; HNF-005 leaves that field out (an open question for PARI).
