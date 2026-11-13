# Rules still to build

Snapshot of 2026-10-25 (`main`): 49 of 135 code/lookup rules have a check; these 86 do not. `di rules` shows the live
status. The packages group rules by what a check needs, which decides how hard it is and who can take it.

How to build one: write a `@check` function in `src/drawing_intelligence/review/checks/` (ADR 0010), give it unit
tests in `tests/test_checks.py`, sweep it over the 200-drawing development sample and read every finding, then
confirm `di eval review --no-understand` still has 0 code false alarms. Until a rule has a check it is reported
"not checked", never "pass".

## Ranking of the 59 left (2026-11-12)

On `main` at `6e76182`: 76 of 135 code/lookup rules have a check; 59 do not (41 `code`, 18 `lookup`). Ranked by
how hard the check is to build with what stage 1 and `config/reference/` give today. "PARI hits" counts the 137
PARI drawings in `data/client_set/` whose text has the rule's trigger (0 means the check will rarely fire).

With the deadline close, the easy and medium checks are built with a lighter test bar: one passing and one failing
unit test per check and one sweep over the client drawings. A check that rests on a heuristic gets
`result: warning`, so it cannot add a false fail and the seeded eval keeps 0 code false alarms.

**Easy (18):** stage-1 text plus a table already transcribed or a pattern an existing check uses.

| Rule | Why easy | PARI hits |
|---|---|---|
| NM-001 | the three notes are in `params` | 136 |
| MC-002 | Ø and depth from the hole callout, a ratio | 64 |
| DM-003 | `chain_checks` already finds chains that close on an overall | n/a |
| WPM-001, WPM-002 | DES-11 `material_heat_treatment`; same shape as `treatment_material_compat` | 73 |
| WPS-001, WPS-003 | `plating_processes`, `plating_prerequisites` | 11 |
| WPS-005, MF-006 | plated part + chamfer callout / threads with no masking note (warning) | 11 |
| WPM-004 | two keywords; "nitriding follows finish machining" left to the LLM | 0 |
| NASA-061 | border regions are in the template | n/a |
| WST-130 | `hardness_conversion_steel` | 2 |
| WPE-001, WST-239, WST-229, WST-249, WST-240, NASA-078 | regex plus a list or table | 0 |

**Status (2026-11-12, branch `feat/easy-checks`): all 18 easy rules have a check (76 → 94 of 135).** Tests in
`tests/test_checks_easy.py`; `di eval review --no-understand` unchanged (71/71, 0 code false alarms). Sweep over
the 137 client drawings, findings read one by one:

| Rule | pass | finding | not checked | Notes |
|---|---|---|---|---|
| WPM-001 | 31 | 1 fail | 36 | induction hardening on 20MnCr5 (DES-11: NIL). Not checked = material not a DES-11 row (M.S.) |
| WPM-002 | 27 | 4 fail | 35 | 20MnCr5 case hardened 40-45 and 55-60 HRC (DES-11 56-60); EN24 "HARDENED 32-35 HRC", in no DES-11 column |
| WPS-001 (warning) | 41 | 1 | 0 | "ZINK BLACK PASSIVATION": not DES-12's name for IZBP |
| WPS-005 (warning) | 1 | 8 | 0 | hard / flash chrome parts with chamfers |
| MF-006 (warning) | 1 | 8 | 0 | flash chrome parts with threads, no masking note |
| DM-003 (warning) | 9 | 8 | 0 | chains that close on an overall with no reference link |
| NM-001 | 136 | 1 fail | 0 | one portrait sheet on another template |
| MC-002 | 62 | 0 | 0 | |
| NASA-061 (warning) | 123 | 0 | 14 | judged against the zone markers' line; sheets with no markers are not checked |
| WPS-003, WPM-004 | 1, 2 | 0 | 0 | |
| WST-130, WPE-001, WST-239, WST-229, WST-249, WST-240, NASA-078 | n/a | 0 | 0 | trigger absent on all 137 (unit tests only) |

Narrower than the rule text: WPM-004 judges "not chrome plated" only (nitriding after finish machining is left to
the AI reviewers); MF-006 judges thick or hard platings only (`processes`), as PARI leaves IZBP threads unmasked;
NASA-061 flags only items that reach the zone markers, because the template's border strips are wider than the
printed frame. Heat treatment and material are read from the notes as well as the title block (`checks/_process.py`):
PARI's title block mostly says "---" and the notes carry "TO BE TOUGHENED UPTO 28-32 HRC" and "# MATERIAL : EN9".
A bare HARDENED is compared with every DES-11 column for the material.

**Medium (21):** text heuristics with false-alarm risk, nearness on the sheet, a small stage-1 change, or a PARI
decision.
- Hole and thread callouts: MX-003, MC-004, MC-006, MX-006.
- Material and size: WPM-005 (31 hits), MF-003, WST-132.
- GD&T by nearness: NASA-134, MD-021, DTT-057 (stage 1 does not read MMC/LMC modifiers yet).
- Part class: SC-002, WF-007. The title block has a PART CLASS. cell the template does not read yet, and some
  notes say "WELD CLASS : B".
- Labels and markers: VW-003 (70 hits), NASA-100, NASA-006.
- Dimensions: DM-002, DSM-023, MP-009 (17 hits).
- Needs PARI: MD-002 and SC-001 (thresholds not set), MF-011 (no approved-materials list).

**Status (2026-11-12, branch `feat/medium-checks`): 12 of the 21 built (94 -> 106 of 135).** Tests in
`tests/test_checks_medium.py`. The template now reads the PART CLASS. cell (`part_class`), so SC-002 and WF-007
have it. Sweep over the 137 client drawings, findings read one by one:

| Rule | pass | finding | not checked | Notes |
|---|---|---|---|---|
| SC-002 | 43 | 3 fail | 91 | PART CLASS. empty. Not checked = variant title block |
| WF-007 | 9 | 0 | 0 | weld class read from "WELD CLASS : B IF APPLICABLE" |
| WPM-005 (warning) | 5 | 2 | 0 | Ø35 En-8(D) bar (DES-11: EN24 above Ø32). Judged on stock notes only ("USE STD. Ø20g6 En-8(D) BRIGHT BAR") |
| MF-003 (warning) | 5 | 2 | 0 | same Ø35 bar: not a size the raw-material list stocks for EN8 |
| MC-006 | 19 | 1 fail | 32 | M50 x 1.5 x 30 DEEP in 20MnCr5 (0.6 × D). Not checked = material unknown |
| VW-003 (warning) | 76 | 0 | 0 | the letter is looked for on every sheet of the drawing |
| MP-009 (warning) | 13 | 0 | 0 | rows read by content; a call-out wrapped onto a second line joins its row |
| MX-003 | 9 | 0 | 0 | revision descriptions ("... ADDED") and "ALL HOLES" notes are not call-outs |
| MD-021 (warning) | 0 | 2 | 0 | 1 real (datum A on M65 x 2), 1 false (the flag is on the Ø16 extension line next to an M10) |
| WST-132 (warning) | 41 | 0 | 91 | a box of the three largest dimensions × 50: only a gross error is caught, because stage 1 does not always read the longest dimension |
| NASA-134, DTT-057 | n/a | 0 | 0 | no position tolerance and no MMC/LMC on any client drawing (unit tests only) |

Not built, moved:
- To PARI (`docs/pari_questions.md`): MC-004 (PARI's tapped call-outs never state a drill depth, so it would
  fail every blind tapped hole), MD-002, SC-001, MF-011.
- To hard: DM-002 (627 repeated dimension texts on 104 drawings; telling a duplicate from a symmetric feature
  needs feature identity), MX-006 (a pattern's location is geometry), NASA-100 (revision triangles on the field
  are graphics), NASA-006 (the "indicated" marker is a hatch or XXXX line, not text), DSM-023 (needs underline
  detection).

**Status (2026-11-13, branch `feat/hard-checks`): the 18 rules better kept off the AI reviewers are built
(106 -> 124 of 135).** The 29 left were split by whether an AI reviewer can judge them: it reads stage 2's JSON
and never sees the sheet, so a rule about how something is drawn (arrowheads, lines through text, which way a
value reads, boxes, underlines) cannot go to it. Those 18 are code; the other 11 (MX-012, DM-002, MD-002,
SC-001, MX-009 for the AI reviewers; WST-206, MX-006, MP-012, MC-007, MC-008, WST-242 split between both) are
next. Stage 1 reads the drawing's graphics for them (`extraction/graphics.py`, schema 2.3, kept out of the
understanding prompt): each value's arrowheads and the dimension line or leader it sits on, its reading
direction, whether it is boxed, underlined, crossed or in a table cell, full circles, the radius of the arc a
radius arrow lands on, revision triangles on the field, datum triangles, and note lines a leader starts from.
PARI's Solid Edge PDFs draw every stroke as a straight segment (arcs are chains) and every arrowhead as a filled
2.3 x 6.9 pt triangle whose legs are stroked as well. Tests in `tests/test_checks_hard.py`. Seeded eval: 19 of
22 caught (DSM-023 now catches P20's R 0.2 drawn R 8; floor raised to 19), 19/19 where built, 73/73 correct, 0
false alarms on the clean drawings. Sweep over the 137 client drawings, findings read one by one:

| Rule | pass | finding | n/a or not checked | Notes |
|---|---|---|---|---|
| CN-003 (warning) | 136 | 0 | 1 | table cells, revision numbers, Ra values, balloons and stacked-limit fragments are not values |
| ISO-023 (warning) | 136 | 0 | 1 | ordinate values have no arrowheads by design and are not judged |
| ISO-025 (warning) | 137 | 0 | 0 | every PARI arrowhead is filled |
| ISO-027 (warning) | 78 | 0 | 59 | counts arrowheads collinear with the radius line, not on joined leaders |
| ISO-029 (warning) | 125 | 11 | 1 | all 11 read as real: hatching, centre, extension and outline lines through 15°, 45°, Ø6.6, 35±0.1, R 6 ... A value's own line is not judged (a text box is deeper than its characters) |
| ISO-030 (warning) | 125 | 0 | 12 | |
| ISO-031 | 127 | 9 warnings | 1 | all angles reading from the left (20°, 25°, 30°); ISO 129 orients angles by its figure 22, so angles warn and linear values fail |
| DSM-023 (warning) | 90 | 0 | 47 | lengths tip to tip, 5-50% off, not at the same ratio as two others nor exactly at a standard scale; radii by an arc fit, only 3x off. Not checked = fewer than 3 lengths at a standard scale |
| DTT-002, MX-011 (warning) | n/a | 0 | 137 | no boxed basic dimension and no position tolerance on these 137. A box is four strokes meeting at corners: extension lines around a vertical value are not one |
| WST-050 (warning) | 78 | 0 | 59 | |
| MD-013 (warning) | 2 | 3 | 132 | the datum triangle sits on the extension line where a dimension's arrow lands, which ASME reads as that feature of size: a drafting ambiguity worth a warning |
| MD-020 (warning) | 0 | 0 | 137 | no datum flag on a pattern call-out |
| NASA-100 | 18 | 1 warning | 118 | revision 2 of PRR74A055037005 has no mark on the field. Numbers up to the latest listed one count as listed (stage 1 cannot read numbers drawn in a cell's triangle) |
| NASA-006 (warning) | 1 | 0 | 136 | "AS SHOWN" dropped from the triggers, "INDICATED AREA" added; the leader may have no arrowhead |
| MX-026 | 1 | 0 | 136 | PARI's weld length / pitch table covers every stitch weld it does not size |
| MF-011 (warning) | 35 | 1 | 101 | judged on carbon, alloy and tool steels (what DES-11 covers): SAE4140/41CrMo4 is not a DES-11 grade |
| MC-004 | 0 | 0 | 137 | judges a stated drill depth only (`report_missing: false`); no client drawing states one |

Counted, not read one by one, over all 1,171 client drawings (findings / drawings): ISO-029 333 / 231, ISO-031
238 / 145 (12 fails), MD-013 32 / 32, MF-011 32 / 32, CN-003 30 / 15, NASA-100 20 / 15, DSM-023 10 / 10, MX-011
10 / 4, the rest 4 or fewer. Nearly all the ISO-029 and ISO-031 hits are on the P23Y5 sheets (upper-case .PDF,
none in the 137), an older drawing style that puts lines through values and angles reading from the left more
often; a sample of them read as real. Sampling these also found three faults, now fixed: extension lines read as
a basic-dimension box, hole-table rows deeper than the cell test allowed, and a revision triangle taking the
label of a dimension beside it.

Narrower than the rule text, until PARI answers (`docs/pari_questions.md` §1b, §3): MF-011 does not judge
mild steel, stainless, cast iron, aluminium or plastics; MC-004 does not ask for a drill depth; MX-011 and
MD-020 only judge by nearness, not by knowing which feature a frame is on.

**Hard (20):** new vector detection, knowing what a feature is, or a missing table.
- Arrowheads and lines: CN-003, ISO-023, ISO-025, ISO-027, ISO-029, WST-050.
- Text direction (stage 1 does not record it): ISO-030, ISO-031.
- Feature identity: MX-009, MX-011, MX-012, MD-013, MD-020, MP-012, WST-206, DTT-002 (boxed basic dimensions),
  MX-026 (weld symbols are graphics).
- Tables: MC-007 (keyway tolerances not transcribed), MC-008 (no circlip table), WST-242 (undercut tied to a thread).

## P1 Text and title-block checks (27)

**Status (2026-10-27, branch `feat/p1-text-checks`, Mushahid): all 27 have a check.** Six are narrower than the
rule text, because of what PARI's drawings and stage 1 give: NASA-030 (resolves a numbered reference, not the flag
half), WST-070 and WST-069 (the callout's own depth or angle, not the hole diameter, which text cannot tie to it),
MX-004 (only text that names a hole or tapping; a bare `M8` label cannot be told from an external thread, so it is
not judged), WST-203 (fires only when limits of size are printed beside the deviations, which PARI never does) and
RV-003 (only the older title block's CAR. NO. column; the current one has none). DTT-007 fails a dimension value
written with the word DIA and warns on the word in a note (change notes, file paths and MAJOR/MINOR/PITCH DIA are
left alone). NASA-012 and WPW-001 needed stage 1 or a guideline: the template now reads the DRN.BY / CHKD.BY /
APPD.BY cells, and WPW-001 follows PARI's welding guideline ("choose only one"). Checks that no development
drawing exercises (NASA-030, HNF-057, ISO-011, NASA-111, WST-064, WST-220, WST-203, WST-238, HNF-066, WST-056,
WST-069, MX-004) are covered by unit tests only.

**Review fixes (2026-10-29, Binjie's review of PR #6):** seven edge cases fixed with regression tests (WST-238
taper minutes, WST-064 count in a decimal, WST-220 capitals and zero pitch, HNF-057 and DSM-012 / VW-008 label
forms, NASA-029 repeated 1, NASA-012 unread cells). Four rules that follow a PARI convention PARI has not
confirmed now only warn, through the rule-level `result: warning` field (MX-029 insert spec, DSM-012 scales,
MF-013 colour code, RV-003 change reference); remove the field when PARI answers.

Stage-1 text only (body notes, dimension text, title block, revision rows). No new inputs; same pattern as `checks/notes.py` and `checks/title_block.py`. Easiest; good first task.

| Rule | Category | Check | Requirement | Needs | Owner |
|---|---|---|---|---|---|
| NASA-029 | consistency | `general_notes_consecutive` | General notes are numbered consecutively from 1, with no gaps or repeated numbers. |  | |
| NASA-030 | consistency | `note_references_resolve` | Every note reference on the drawing field ('SEE NOTE 5' or a flag number) points to a note that exists, and every not... |  | |
| DTT-007 | consistency | `diameter_radius_symbol_prefix` | Diameter dimensions are preceded by the diameter symbol (Ø) and radius dimensions by R; no 'DIA' suffix or 'D' forms. |  | |
| ISO-011 | consistency | `non_length_value_has_unit` | Values in units other than the drawing's length unit (e.g. torque in N·m, pressure in kPa) show their unit symbol wit... |  | |
| NASA-111 | consistency | `angle_format_consistent` | Angles use one format throughout (decimal degrees or degrees-minutes-seconds), and an angle's tolerance uses the same... |  | |
| WST-064 | consistency | `pitch_notation_arithmetic` | For equally spaced features dimensioned as number × pitch = total (e.g. 4 × 60 = 240, or 7 @ 75 = 525 in steelwork), ... |  | |
| WST-056 | consistency | `chamfer_callout_complete` | A chamfer is dimensioned by its length and angle, either as separate dimensions or combined as length × angle (e.g. 6... |  | |
| WST-069 | consistency | `countersink_callout_complete` | A countersunk hole callout gives the hole diameter, the countersink diameter and the included angle, and the angle is... |  | |
| WST-070 | consistency | `counterbore_callout_complete` | A counterbored hole callout gives the hole diameter, the counterbore diameter and the counterbore depth (e.g. 6ϕ, 12ϕ... |  | |
| WST-127 | consistency | `softening_treatment_vs_hardness` | When the only heat treatment named is a softening one (annealing, spheroidizing, sub-critical annealing, stress relie... |  | |
| WST-203 | tolerance | `limits_match_deviations` | Where a dimension shows both its deviations and its limits of size, each limit equals the basic size plus the matchin... | stacked limits + deviations | |
| WST-220 | thread_weld | `thread_lead_multiple_of_pitch` | For a multi-start thread, the lead is a whole multiple of the pitch (lead ÷ pitch = number of starts, e.g. Tr 40×14 (... | trapezoidal thread callouts | |
| WST-238 | consistency | `taper_values_consistent` | Where a taper is dimensioned by more than one of ratio 1:x, cone angle, and diameters over a length, the values agree... |  | |
| MX-004 | thread_weld | `thread_callout_complete` | Incomplete thread callout |  | |
| HNF-057 | title_block | `supersede_note_complete` | A drawing that replaces another carries a 'SUPERSEDES DWG [number] REV [number]' note near the title block, giving bo... |  | |
| NASA-012 | title_block | `checker_independent` | The checker named in the title block is a different person from the designer and the drafter. | designer/drafter/checker cells | |
| RV-001 | title_block | `revision_table_complete` | Revision table has an entry for every revision, with description, date and author |  | |
| RV-003 | title_block | `revision_change_ref` | The ECN or change reference is quoted for revised drawings |  | |
| DSM-012 | title_block | `scale_is_preferred` | The drawing and detail-view scales are full size where possible, otherwise a preferred scale: 1:2, 1:5, 1:10, 1:20 or... | view scales from notes | |
| WPW-001 | thread_weld | `weld_note_options_resolved` | Welding notes have exactly one option chosen (Applicable / Not Applicable, Required / Not Required) | weld-note option boxes | |
| MF-013 | surface_treatment | `paint_colour_code` | Paint or powder-coat colour is specified by code (e.g. RAL) |  | |
| NASA-005 | title_block | `continuation_sheet_title_fields` | Every continuation sheet repeats the title-block identification (drawing number, sheet number, title and scale), and ... | multi-sheet | |
| NASA-001 | title_block | `sheet1_has_title_revision_notes` | On a multisheet drawing, sheet 1 carries the complete title block, the revision block and the general notes. | multi-sheet | |
| VW-008 | consistency | `detail_view_scale` | Detail views state their scale | detail-view labels | |
| HNF-061 | design_intent | `soft_metric_conversion_suspect` | Dimensions are hard metric (chosen in mm), not soft conversions of inch values. | inch-conversion heuristic | |
| HNF-066 | consistency | `dual_dimensioning` | Dual dimensioning is avoided; where used, a general note explains the secondary values, they are placed the same way ... |  | |
| MX-029 | thread_weld | `insert_spec` | Missing insert specification |  | |

## P2 Reference tables (lookup) (19)

Transcribe a cited table into `config/reference/`, add its model in `review/reference.py` and a structure test (see `tests/test_reference_tables.py`), then the check. PARI tables need PARI's documents (DES-11 etc.).

| Rule | Category | Check | Requirement | Needs | Owner |
|---|---|---|---|---|---|
| WPM-001 | surface_treatment | `heat_treatment_allowed` | The heat treatment specified is one PARI allows for that material | PARI DES-11 material_heat_treatment | |
| WPM-002 | surface_treatment | `hardness_in_range` | The hardness (and case depth) is within PARI's range for the material and process | PARI DES-11 material_heat_treatment | |
| WPM-004 | surface_treatment | `treatment_combination` | Nitrided parts are not chrome plated, and nitriding follows finish machining | PARI DES-11 material_heat_treatment | |
| WPM-005 | material | `material_for_size` | Round-bar material suits the size: EN9 up to 32 mm diameter, EN24 above | PARI DES-11 material_heat_treatment | |
| WPS-001 | surface_treatment | `surface_treatment_approved` | The surface treatment is one of PARI's listed processes | plating_processes (exists) | |
| WPS-003 | surface_treatment | `treatment_prerequisites` | The surface treatment's prerequisites are met | plating_processes: add prerequisites | |
| MF-011 | material | `material_approved` | Material is on the approved or preferred list | PARI approved materials list | |
| WPE-001 | material | `us_india_equivalent` | A US material designation is shown with its Indian equivalent | US-India equivalents (DES-11) | |
| MF-003 | manufacturability | `stock_size_available` | Stock form or size is given where it matters (plate thickness, bar diameter) | PARI raw-material sizes | |
| WF-007 | thread_weld | `weld_class_for_part_class` | Welding standard and quality level are stated (e.g. ISO 5817 level C) | part class -> weld level (params) | |
| WST-130 | consistency | `hardness_scales_agree` | Where a hardness is given in two scales, or together with a tensile strength (e.g. '58-62 HRC (650-750 HV)'), the val... | Westermann hardness conversion | |
| WST-132 | consistency | `mass_within_envelope` | A stated part mass is no more than the mass of the part's bounding envelope (length × width × height, or π/4·D²·L for... | Westermann specific weights | |
| WST-240 | consistency | `self_holding_taper_matches_table` | A Morse or Metric self-holding taper is called out by its designation (Metric 4, 6, 80; Morse 0 to 6), and any gauge ... | IS 1715 tapers | |
| WST-239 | design_intent | `taper_ratio_standard` | A taper uses a standard ratio from IS 3458 (1:0.289, 1:0.5, 1:0.866, 1:1.5, 1:3.429, 1:5, 1:6, 1:10, 1:15, 1:20, 1:30... | IS 3458 tapers | |
| MC-007 | manufacturability | `keyway_standard` | Keyways and keys follow the standard with correct tolerances | keyway table | |
| MC-008 | manufacturability | `circlip_groove_standard` | Retaining-ring grooves follow the ring standard | circlip groove table | |
| WST-229 | manufacturability | `taper_pin_hole_callout` | A hole for a taper pin is called out with the 1:50 taper and the pin's nominal size, which is the small-end diameter,... | IS 6688 taper pins | |
| WST-242 | manufacturability | `thread_undercut_matches` | A thread undercut has at least the width and radius IS 1369 gives for the thread size, with a diameter no larger than... | IS 1369 undercuts | |
| WST-249 | manufacturability | `centre_hole_designation_complete` | A centre-hole callout gives the type (A without, B with a protective chamfer), a standard pilot diameter d1 (1, 1.6, ... | IS 2473 centre holes | |

## P3 Vector geometry (12)

Needs the PDF's lines and arrowheads around each dimension (stage 1 already matches dimension lines for the scale check: `checks/_geometry.py`). Medium-hard; measure false alarms on the 200-drawing sample.

| Rule | Category | Check | Requirement | Needs | Owner |
|---|---|---|---|---|---|
| CN-003 | consistency | `unattached_dimension` | Every dimension value has a matching dimension line |  | |
| DM-002 | consistency | `duplicate_dimension` | No duplicate or over-dimensioning |  | |
| DM-003 | consistency | `closed_chain` | No closed dimension chains unless one link is a reference dimension |  | |
| DSM-023 | consistency | `dimension_matches_scale_or_underlined` | A dimension whose value does not match the drawn geometry at the view scale is underlined as not to scale; out-of-sca... |  | |
| ISO-023 | consistency | `dimension_line_terminations` | Every dimension line ends in a distinct termination (arrowhead or oblique stroke) or, for running dimensions, starts ... |  | |
| ISO-025 | consistency | `single_arrowhead_style` | One arrowhead style (open, closed or filled) is used throughout a drawing; an oblique stroke or a dot replaces an arr... |  | |
| ISO-027 | consistency | `radius_single_arrowhead` | A radius dimension has exactly one arrowhead, with its point on the arc end of the dimension line (inside or outside ... |  | |
| ISO-029 | consistency | `dimension_text_not_crossed` | No line crosses or splits a dimension value. |  | |
| ISO-030 | consistency | `dimension_value_method_consistent` | A drawing places dimension values by one method throughout, ISO 129 method 1 (aligned with the dimension line, read f... |  | |
| ISO-031 | consistency | `dimension_text_readable_direction` | With method 1, values are parallel to their dimension lines and read from the bottom or the right-hand side of the sh... |  | |
| NASA-061 | consistency | `content_inside_border` | Views, dimensions and notes stay inside the drawing border and do not run into the margins. |  | |
| WST-050 | consistency | `full_circle_by_diameter` | Full circles are dimensioned by their diameter, using one of the illustrated methods (across the circle, by a leader ... |  | |

## P4 Features, views and symbols (28)

Needs to know what a dimension is on (hole, shaft, thread, pattern), views and markers: from the vision understanding or new stage-1 detectors. Hardest; several may stay LLM-reviewed.

| Rule | Category | Check | Requirement | Needs | Owner |
|---|---|---|---|---|---|
| MX-003 | consistency | `hole_depth_stated` | Missing depth | hole features | |
| MX-006 | consistency | `pattern_callout_complete` | Pattern not fully defined | patterns | |
| MX-009 | consistency | `angle_stated` | Missing angle | angles on features | |
| MX-011 | gdt | `basic_dims_for_position` | Missing basic dimension | basic dims + position frames | |
| MX-012 | tolerance | `tolerance_coverage` | Missing tolerance | which features need tolerances | |
| MX-026 | thread_weld | `intermittent_weld_complete` | Missing intermittent weld length or pitch | weld symbols | |
| NASA-006 | consistency | `where_indicated_has_marker` | When a note or title-block option applies "where indicated" or to "surfaces marked", the matching marker symbol or fl... | 'where indicated' markers | |
| NASA-078 | consistency | `rotated_view_labelled` | A rotated view, section or detail states the angle and direction of rotation. | rotated views | |
| NASA-100 | title_block | `revision_markers_match` | Each revision marker on the field (revision symbol at the point of change) matches an entry in the revision block, an... | revision triangles on the field | |
| VW-003 | consistency | `section_labels_match` | Section and detail views are labelled, and labels match cutting lines and detail circles | section/detail labels and cutting lines | |
| MD-002 | datum | `datums_needed` | No datums on a part that needs them | part needs datums | |
| MD-013 | datum | `datum_feature_size_toleranced` | Datum feature of size without size tolerance | datum feature of size | |
| MD-020 | datum | `pattern_datum_defined` | Pattern used as a datum without definition | pattern datums | |
| MD-021 | datum | `thread_datum_qualifier` | Threaded feature as datum without qualifier | thread datums | |
| MP-009 | datum | `hole_table_complete` | Hole / coordinate table entries: Every tagged hole (A1, B2 …) has a row with X, Y, size and depth; the table origin i... | hole tables | |
| MP-012 | datum | `ordinate_origin` | Origin point: The 0,0 point for ordinate or coordinate dimensioning is clearly marked and is a datum feature | ordinate origin | |
| DTT-002 | gdt | `basic_dimension_untoleranced` | Basic dimensions are shown enclosed in a rectangle (box) and carry no tolerance of their own. | boxed basic dimensions | |
| DTT-057 | gdt | `material_modifier_on_feature_of_size` | MMC and LMC modifiers appear only on tolerances of features of size (not on flatness, circularity, cylindricity or ru... | MMC/LMC modifiers | |
| NASA-134 | gdt | `projected_zone_on_threads` | Position tolerances on tapped holes, threaded inserts and dowel-pin holes use a projected tolerance zone with its hei... | tapped holes + position | |
| WST-206 | tolerance | `fit_letter_case_matches_feature` | A fit symbol on an internal feature (hole, bore, slot) uses a capital letter (e.g. H7) and one on an external feature... | internal vs external feature | |
| MC-002 | manufacturability | `depth_to_diameter` | Hole depth is reasonable for the diameter (about 10 × D unless deep drilling is noted) | hole depth vs diameter | |
| MC-004 | manufacturability | `tap_drill_depth` | Blind tapped holes have a drill depth beyond the thread depth (about 3 pitches) | blind tapped holes | |
| MC-006 | manufacturability | `thread_engagement` | Thread engagement suits the material (e.g. at least 1.5 × D in aluminium) | thread engagement + material | |
| MF-006 | surface_treatment | `masking_note` | Masking is stated for surfaces that must stay uncoated (threads, mating faces) | surfaces to mask | |
| WPS-005 | surface_treatment | `plating_edge_radius` | Hard chrome, flash chrome and QPQ parts have sharp edges blended by radius, not chamfer | edge breaks on plated parts | |
| SC-001 | design_intent | `lifting_info` | Lifting points are identified with rated capacity; lifting lugs are designed and marked | lifting points | |
| SC-002 | title_block | `part_class_stated` | Safety-critical parts are flagged (guards, interlocks, load-bearing members) | safety-critical parts | |
| NM-001 | consistency | `template_notes_present` | Standard general notes are present (deburr, unspecified radii, general tolerance) | needs PARI's standard-notes list | |
