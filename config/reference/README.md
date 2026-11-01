# Reference tables

Data the `lookup` rules check against (ADR 0010): one YAML file per table, named as the rules' `params.table`
names it. Every table says where it comes from. Their content is part of the rulebook version recorded in every
review result, so a table change shows up like a rule change.

| File | What it holds | Source |
|---|---|---|
| `materials.yaml` | How a title-block material designation maps to a material class and family | PARI DES-11, US–India equivalents, the designations printed on the client drawings |
| `plating_processes.yaml` | PARI's surface treatments, how they are written, and the materials each suits | PARI PRD-GD-DES-12 rev 4 |
| `is919_fits.yaml` | Fit deviations (µm) for 40 tolerance zones, 0–500 mm | IS 919 via the Westermann tables (pdf 43L–44R) |
| `is2102_general_tolerances.yaml` | General tolerances by class, linear and angular | IS 2102-1969 via the Westermann tables (pdf 73L) |
| `iso_metric_threads.yaml` | Metric thread sizes and pitches to M80; tabulated tolerance classes | ISO 261; IS 4218 via the Westermann tables (pdf 45R–46L) |

The standards tables are transcribed from a scan. `tests/test_reference_tables.py` checks them against the
standards' own structure (each fit zone is its IT grade wide, fundamental deviations agree across grades and
between holes and shafts, general tolerances widen with size and class), so a misread digit fails a test. The
one misprint found in the book (j6, 80–120 mm) is corrected and noted in the file.

Patterns are case-insensitive regular expressions matched anywhere in the field. The first match wins, so list
specific patterns (hard anodizing) before general ones (anodizing).


## Zhetao's P2 reference-data contribution

`material_heat_treatment.yaml` is the complete DES-11 page-1 transcription, with all 13 material rows and all
78 treatment cells (21 numeric, 57 NIL). `raw_material_sizes_des11.yaml` preserves all six page-2 stock rows,
11 stock-form lists and 251 market-size entries. Each includes exact source identity, revision, date, PDF
page/row citations and a source SHA-256. NIL, blank cells and dash placeholders remain distinct.

Other P2 sources and their exact supported scope are recorded in `docs/reference/P2_REFERENCE_STATUS.md`.
The 2024 workbook's full cell-value catalogue is separate from the 2016 DES-11 sizes; do not silently merge
conflicting source dates. Raw recommendation text is retained and is not promoted to a mandatory prohibition.

Validation: `uv run pytest tests/test_reference_tables.py tests/test_reference_tables_des11.py
 tests/test_reference_tables_p2.py` (run this as one command). The uploaded example test is unchanged.
No drawing detector or shared prompt is added by this contribution. Reference-data readiness is independent
of whether a review sweep raises findings. The rulebook hash already includes these table files.
