# P2 reference-data status

P2 reference-data contribution; statuses describe cited data readiness, not drawing pass/fail or check implementation.

| Rule | Data status | Tables / scope |
|---|---|---|
| WPM-001 | reference_ready | material_heat_treatment. DES-11 all 13 rows and all six process columns, including NIL and the special-selection exception. |
| WPM-002 | reference_ready | material_heat_treatment. All printed hardness and case-depth bands, original units and normalised mm values. |
| WPM-004 | reference_ready | material_heat_treatment. Source policies retained: after-finish-machining instruction, prior-toughening preference, chrome avoidance recommendation. Do not silently strengthen recommendations into bans. |
| WPM-005 | reference_ready | material_heat_treatment, raw_material_sizes_des11. EN9 <=32 mm, EN24 >32 mm per WPM-005; printed EN24 notation retained. Stock availability is not filtered by preferred-use limits. |
| WPS-001 | reference_ready | plating_processes. Existing 10-process DES-12 table retained; not an exhaustive prohibition on other finishes. |
| WPS-003 | reference_ready | plating_processes, plating_prerequisites. All ten prerequisite/constraint/remark text cells; structured numeric/material subset remains explicitly scoped. |
| MF-011 | reference_partial | material_heat_treatment. The 13 DES-11 preferred rows are transcribed, but a complete controlled approved-material list is not supplied. DES-11 note iii permits justified special selections. |
| WPE-001 | reference_ready | us_india_materials. All 14 Sheet1 G5:H18 rows, with conditional/prose alternatives preserved; not universal metallurgical equivalence or blanket substitution approval. |
| MF-003 | reference_ready | raw_material_sizes_des11, raw_material_sizes, raw_material_catalogue. Complete 2016 DES-11 stock table plus all 768 nonempty cells in the 16-sheet 2024 catalogue. Direct numeric stock lookup is a documented 22-row subset. Profile drawings are not transcribed. |
| WF-007 | reference_ready | Rule params / pending source. The cited part-class mapping already exists in WF-007.params.table. Preserve T+S:B, A:C, B:C, C:D. |
| WST-130 | reference_ready | hardness_conversion_steel. All 34 numeric source rows, HB ball types, HRC, HRB and tensile strength; blank cells and operating footnotes retained. Acceptance tolerance remains a separate rule-policy decision. |
| WST-132 | reference_ready | material_specific_weight. All 16 solid-material specific-weight entries on PDF 04L plus copper/aluminium on 03R; babbitt range retained. Envelope association is future check logic. |
| WST-240 | reference_ready | is1715_self_holding_tapers. All ten designations with printed alpha, gauge D and tapped-shank thread; no silent change of angle convention. |
| WST-239 | reference_ready | is3458_standard_tapers. All 12 preferred ratios named by the source/rule. |
| MC-007 | reference_partial | keyways. Both nominal key tables on PDF 49R are transcribed (12 taper-key, 11 Woodruff-key options). Applicable parallel-key/keyway tolerance tables still need a confirmed source. |
| MC-008 | source_needed | Rule params / pending source. Need PARI to identify the retaining-ring standard and provide its groove dimensions/tolerances. DES-11 contains no circlip table; no standard is guessed. |
| WST-229 | reference_ready | is6688_taper_pins. All 16 small-end nominal diameters and the 1:50 taper. |
| WST-242 | reference_ready | is1369_thread_runout_undercut. All 15 ISO coarse-thread undercut rows: angle-specific external/internal widths, radii and g/g1 expressions, including printed blanks. No fine-pitch or unlisted-size extrapolation. |
| WST-249 | reference_ready | is2473_centre_holes. Complete A/B pilot-diameter lists needed by this designation rule; unrelated centre-hole geometry is outside this transcription. |
