# Local validation for this handoff

Validated against upstream `ed2fc468b35fcb84059c5d308329569c20dbf3c2` on Windows with the locked
project dependencies and Python 3.13.18. No paid API calls or remote pushes were made.

- All `src/` byte hashes matched the completed checkpoint after applying the original Colab native
  evaluator patch. The production model registry remains byte-identical to upstream.
- Offline verifier passed: all exported evidence hashes, original/redacted manifest linkage,
  immutable prediction rows, 24 successful drawings, 72 successful Plus reviewer records,
  107 unlabelled findings, and source counts.
- Full `pytest -m "not live"`: **597 passed**. Two subsequently added transport regression tests:
  **2 passed**. Total: **599 distinct passing tests**.
- `ruff check .` and `ruff format --check .` passed.
- Pyright passed with the project interpreter explicitly selected: **0 errors, 0 warnings**.
  The later transport test file was also checked separately, with 0 errors/warnings.
- The reproduction runner's default prepare-only path successfully froze and verified all 24
  actual repository PDFs and audited source files, using an offline placeholder endpoint and no key.
- Colab notebook code parsed, paid execution defaults OFF, and notebook lint/format checks passed.
  A complete fresh paid Colab run was not performed during packaging.
- Submitted files were scanned for personal workspace IDs and API-key-like literals; none found.
  Databases, checkpoint ZIPs, original notebook payload, runtime folders and mixed response caches are excluded.

Environment adjustments: sandbox temporary directories required a workspace-local TEMP/TMP and pytest
base directory; the system Node executable was too old, so the bundled modern Node was used for Pyright.
These were local test-environment settings, not changes to project dependencies or application behavior.

Single-upload packaging update: per-report hashes were retained for all 72 combined reviewer JSON texts. Two new bundle-integrity regression tests were added; see handoff validation for their results.
