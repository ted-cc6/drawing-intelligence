# Qwen3.7-Plus: separate Virginia Global, same-24 evaluation

The original Max run was blocked by repeated provider HTTP 500 responses. This contribution preserves
the native held-out evaluator and adds an independent Plus reproduction entry point and audit evidence.
Production `config/models.yaml` is unchanged: its review default remains `qwen3.8-max`.

The completed run used `qwen3.7-plus`, thinking off, temperature 0, a 32,000-token output limit,
strict JSON Schema, and the original three reviewer prompts. Qwen3-VL-Plus supplied cached understanding.
Plus requests were streamed, serialized with a three-second gap, and allowed infrastructure retries.
The 24 PDF paths and byte hashes are frozen in `frozen_inputs.json`.

| Item | Recorded result |
| --- | ---: |
| Successful drawings | 24/24 |
| Reviewer calls represented in the full evaluation | 72 |
| New reviewer API calls / cached trial calls | 63 / 9 |
| Understanding cache hits | 25 page calls across 24 drawings |
| Findings | 107 |
| Deterministic code / lookup findings | 69 / 6 |
| AI design-intent / manufacturability / drawing-practice findings | 21 / 7 / 4 |
| Full-run registry estimate | USD 0.336175 |
| Successful three-drawing trial registry estimate | USD 0.038569 |
| Combined registry estimate | USD 0.374744 |

Costs are conservative registry estimates at USD 1.20/4.80 per million input/output tokens, not invoices.
Probe, historical understanding, earlier failed experiments, and unknown failure charges are excluded.
The run finished at 2026-11-03 17:36:14 UTC (2026-11-04 01:36:14 Asia/Shanghai).
There were no new API errors or retries in the full run. No paid calls were made while preparing this package.

## What this establishes

The actual Virginia Global workspace accepted the small strict-schema probe and completed all three
reviewers on all 24 drawings. Max and Flash remain separate experiments. Both review model and workspace
deployment scope changed compared with the failed Max run; these results do not isolate the failure cause.
There is no comparative accuracy or production-readiness claim.

**Human validation is pending.** Findings are predictions, not 107 confirmed defects.
For example, an AI warning for `P23Y5B157012001.PDF` claims material thickness is missing, while its
annotated drawing visibly includes `1.6 THK.`. This is a false-positive candidate requiring engineer review.
Suggestions in `review_notes.json` are separate from the original, blank label columns.

## Read and validate the submitted evidence (free)

From the repository root:

```bash
uv sync --locked
uv run python spikes/qwen37plus/verify_results.py
uv run pytest tests/test_heldout_audit.py tests/test_qwen37plus_evidence.py -q
```

The evidence directory is
`data/eval/heldout/2026-11-03_qwen37plus_virginia_global_same24/`.
Start with `summary.json`, `findings_for_human_review.csv`, `review_notes.json`, `full/reviewer_reports.json`, and the three PNG examples in `full/reports/`.
All 72 reviewer JSON outputs are bundled, without altering their text, in
`full/reviewer_reports.json`. Its keys retain the original report paths and the verifier checks each
original/published per-report digest. Three representative annotated PNGs, original attempt/call ledgers
and recovery logs are retained. This reduces the entire code/data upload to 37 physical files.
Tiles, duplicate XLSX exports, SQLite databases and mixed historical response caches are omitted.

Personal workspace IDs were replaced with `WORKSPACE_REDACTED`. `provenance/redaction_map.json` contains
the original and published hashes of every exported evidence file. The original state manifest digest
still points to the original unredacted manifest; the verifier checks this explicit linkage.
These are published audit derivatives, **not resumable copies of the private checkpoint**.
The original checkpoint and Colab-export SHA-256 values are in `provenance/input_artifacts.json`.
For later native `score_heldout` scoring, apply the human labels to the original private checkpoint,
whose manifest hash is unchanged. The redacted derivative intentionally fails the native original-manifest
check; do not delete that check or claim final metrics from this unlabelled publication.

## Reproduce in a new run (paid only with explicit flags)

Use the project Python environment. Set `QWEN_BASE_URL` to your own Virginia **Global** workspace's
OpenAI-compatible URL and provide a key authorized for that workspace. The model/scope combination must
be enabled in your account. Do not paste a key into a committed file.

PowerShell:

```powershell
$env:QWEN_BASE_URL = 'https://YOUR_WORKSPACE.us-east-1.maas.aliyuncs.com/compatible-mode/v1'
# Free preparation only:
uv run python spikes/qwen37plus/run.py
# Supply QWEN_API_KEY privately in your local environment before this paid command:
uv run python spikes/qwen37plus/run.py --run --budget-usd 1 --approval-note 'Your name: personally authorize this separate Plus evaluation, cumulative evaluator soft cap USD 1; unknown and historical charges additional.'
```

Or use `reproduce_colab.ipynb` after this branch is uploaded. Paid execution defaults to OFF.
The runner makes an isolated config copy under `spikes/qwen37plus/out/`, leaving production defaults alone.
It preserves the original workflow, PDF hashes and prompt/schema. Model-specific cached responses may
reduce cost if already available, but they are not bundled; a fresh run will generally call all reviewers
and may call understanding as well. A USD 1 soft cap may therefore stop a fresh run early.
The soft cap is checked **between PDFs**, can be exceeded by one PDF, and cannot account for unknown charges.

Rerun the same command and output folder to resume native successful attempts. Keep the local telemetry
and cache together. Use a new `--out` folder when changing inputs/config/endpoint. The source adapter
checks the expected native evaluator layout and refuses incompatible versions before paid reviewer calls.
The exact transport used in the historical run is retained as `provenance/transport_executed.py.txt`;
the runnable transport has formatting/import cleanup for repository checks.

## Source dependency and validation

The native evaluator/CLI and audit tests are extracted from the reviewed patch embedded in the user's
Colab export. They add prepare-only manifests, attempt retention, cache/schema checks, explicit budgets,
and label scoring. All resulting `src/` hashes matched the completed checkpoint before packaging.
The tested upstream baseline is `ed2fc468b35fcb84059c5d308329569c20dbf3c2`.
This package does not include or change the separate P2 contribution.

Official references: [model capabilities](https://www.alibabacloud.com/help/en/model-studio/qwen3-7-plus),
[structured output](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output),
[pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing).
