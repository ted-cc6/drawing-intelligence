# Rules still to build

Snapshot of 2026-10-25 (`main`): 49 of 135 code/lookup rules have a check; these 86 do not. `di rules` shows the live
status. The packages group rules by what a check needs, which decides how hard it is and who can take it.

How to build one: write a `@check` function in `src/drawing_intelligence/review/checks/` (ADR 0010), give it unit
tests in `tests/test_checks.py`, sweep it over the 200-drawing development sample and read every finding, then
confirm `di eval review --no-understand` still has 0 code false alarms. Until a rule has a check it is reported
"not checked", never "pass".

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
