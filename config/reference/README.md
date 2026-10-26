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
