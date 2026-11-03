# P10 Qwen3.7-Plus: single-upload audit evidence

24/24 drawings completed; 72 successful reviewer records, including 63 new requests and 9 trial cache hits.
107 findings: 32 AI reviewer predictions and 75 deterministic code/lookup predictions. Human validation pending.
No separate P2 table directory is included.

All 72 reviewer JSON outputs are stored in **full/reviewer_reports.json**. Each key is the original
report relative path, and each value is the exact UTF-8 JSON text, including whitespace/newlines.
No report was summarized or regenerated. Original/published per-report SHA-256 values remain in
provenance/redaction_map.json. The bundled verifier checks those virtual report paths as well as
all retained physical evidence files. Other intermediate exports remain in the private checkpoint.

Full run/call/row ledgers, prior-trial cost state, logs, blank human-review CSV and three example
review PNGs are retained. Unconfirmed false-positive candidates are listed in review_notes.json.
Published workspace identifiers are redacted. These are audit derivatives, not resumable private checkpoints.
Use the private original for native scoring; do not bypass original-manifest checks.

Run from repository root: `uv run python spikes/qwen37plus/verify_results.py`.
Combined conservative estimate USD 0.374744 excludes probe, historical understanding and unknown failure charges.
This is Plus on Virginia Global; not completed Max evaluation, confirmed defects, or comparative accuracy.
Model and workspace scope both changed relative to the failed Max experiment.
