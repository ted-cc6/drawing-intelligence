# Nov 12: rule checks, easy and medium tiers (76 -> 106 of 135 code/lookup rules)

On `main`. The 59 unbuilt code/lookup rules were ranked easy (18), medium (21) and hard (20); the ranking, the
per-rule sweep results and what each check leaves out are in `docs/backlog/rules_to_build.md`. Every open
question for PARI is now in one list, `docs/pari_questions.md`. The Space is not redeployed (still the Nov 08
code).

With the deadline close, the new checks use a lighter test bar: one passing and one failing unit test each and
one sweep over the 137 client drawings with every finding read. A check that rests on a heuristic only warns
(`result: warning`), so it cannot add a false fail.

| Batch | Rules | Commit |
|---|---|---|
| Easy, 18 | WPM-001, WPM-002, WPM-004, WPS-001, WPS-003, WPS-005, MF-006, DM-003, NM-001, NASA-061, NASA-078, WST-130, WPE-001, MC-002, WST-239, WST-229, WST-249, WST-240 | `71d1c21` |
| PARI questions | `docs/pari_questions.md`: findings on PARI's drawings, warn-only conventions, inputs the next checks need, O1-O9, the 49 `needs_pari` rules | `b483102` |
| Medium, 12 of 21 | SC-002, WF-007, WPM-005, MF-003, MC-006, MX-003, MP-009, VW-003, MD-021, NASA-134, DTT-057, WST-132 | `a5a26c2` |

What changed in how the review reads a drawing:
- Heat treatment, plating and material are read from the notes as well as the title block
  (`review/checks/_process.py`). PARI's title block mostly says "---" for heat treatment and the notes carry it
  ("TO BE TOUGHENED UPTO 28-32 HRC", "# MATERIAL : EN9"); about two thirds of the sheets have a variant title
  block with no fields at all.
- The template reads the PART CLASS. cell (`part_class`).
- New module `review/checks/manufacturability.py` (hole depths, tapers, centre holes, hole tables).

What the sweep found on PARI's own drawings (all listed with drawing numbers in `docs/pari_questions.md` §1):
20MnCr5 induction hardened (DES-11: NIL); case hardness outside DES-11's range; EN24 "HARDENED 32-35 HRC" in no
DES-11 column; Ø35 En-8(D) bar above DES-11's Ø32 limit and not a stocked size; chamfers and no masking note on
chrome-plated parts; closed dimension chains; an M50 x 1.5 thread 0.6 × D deep; empty PART CLASS. cells; a datum on
an M65 thread with no qualifier.

Left (29): MC-004, MD-002, SC-001, MF-011 wait on PARI; DM-002, MX-006, NASA-100, NASA-006 and DSM-023 moved
to hard, which now holds 25 rules that need vector geometry (arrowheads, lines through text, text direction,
boxed basic dimensions) or knowing which feature a dimension is on.

Tests: 628 unit tests, 76 regression tests, ruff, format, pyright. `di eval review --no-understand` unchanged:
recall 18/18 where a check is built, precision 71/71, 0 code false alarms. Spend: $0 (no model calls).
