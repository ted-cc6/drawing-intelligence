# Independent fresh Flash evaluation — Zhetao Zhang

This notebook starts a new evaluation from a clean Colab session. No old manifest, Max checkpoint, cached
prediction, label file, cost database, or notebook variables are required. It clones the project at
`b16a66aa77e8003458f4f55f6347fd415a9a6701` into a separate workspace and installs this evaluator.

The tested system uses `qwen3-vl-plus` for understanding and `qwen3.8-flash` for the three AI reviewers,
thinking off. All 24 drawings use the same model setup. Strict JSON output, prompts, rules, verifier and
output token settings are inherited from the pinned project. Flash is registered only in the evaluation's
runtime configuration. This measures the Flash variant and does not complete validation of the Max baseline.

Before predictions, freeze 24 unseen drawings with seed 2026103102, the exact baseline source/config hashes,
this driver hash, endpoint and model specification. Exclude historical development sweeps, sample PDFs,
seeded bases, prior held-out sets, named spike inputs, guidelines/templates and byte/text duplicates. The
notebook includes 25 known previously selected or inspected drawings as exclusions; it needs no old files
to apply these exclusions. Additional private team exposures can be added before freezing. The recorded
team exclusion note is carried forward explicitly, not invented by the notebook author.

Zhetao requested this new Flash run on 2026-10-31. The new run has a $2.50 estimated soft cap. A $0.50
planning reserve leaves room within the previously authorized $3 session budget. This is a reservation,
not a reconstructed prior cost ledger or a claim about the provider invoice. Flash estimation uses the
higher documented US scope prices, $0.15 input / $0.47 output per million tokens, checked 2026-10-31.
Vision costs use the repository registry rates. Actual charges can differ and failed calls may have
unreported costs. The threshold is checked between drawings and can be exceeded by one drawing.

No paid calls are made by unit tests or by the notebook author. The delivered paid-run cell is ON because
the user requested the new run; it displays the model, sample and cap before making calls. Credentials
come from Colab Secrets or hidden input. No API key is written into source, response caches or exports.

Started attempts, successes, failures, rows, hashes and a fresh cost ledger are saved. Failures stop the
batch and cannot silently become successful zero-finding drawings. An explicit infrastructure retry must
archive original attempts before rerunning the same request; quality/schema failures cannot be rerolled.
Starting this notebook again reuses its own frozen run rather than selecting easier replacement drawings.
Optional Google Drive persistence and a new-run checkpoint are available for future continuation.

Independently label every verified finding against the original drawing. Only label, label_reason and
labelled_by may change. Record PARI proxy/engineer confirmation. Report decided precision, correct /
(correct + incorrect), alongside unsure counts/bounds and the drawing-cluster bootstrap interval. Keep
code/lookup findings separate. No recall or overall drawing accuracy is claimed. Undefined precision is
null, not 100%. Failed or incomplete batches remain PROVISIONAL. A final score requires all drawings and
engineer confirmation. The new model's results must not be presented as the original Max model's score.

The GitHub ZIP contains the evaluator, tests, this protocol, frozen inputs, prediction records, any labels
and metrics, and new response caches. It excludes runtime databases, sessions and environment files.
The separate checkpoint includes the new run's private cost ledger for restoration. Open a task PR into
main, request Binjie review, and wait for CI; this notebook does not push, merge or send messages.

Validation: `uv run pytest tests/test_flash_restart.py -q`, `uv run ruff check .`,
`uv run ruff format --check .`, `uv run pyright`, `uv run pytest -m 'not live'`.

Model source: https://www.alibabacloud.com/help/en/model-studio/qwen3-8-flash
