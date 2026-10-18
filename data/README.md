# data/ (committed, ADR 0007)

Everything in this folder is committed, including client drawings, so a clone has all it needs. API keys
are never here; they live in the git-ignored `.env`.

| Folder | Contents |
|---|---|
| `raw/` | the four sample PDF drawings |
| `client_set/` | the client's full dataset: ~1,170 drawings, Check List, WP Guidelines, template |
| `exports/` | outputs exported with `--export` (annotated images) |
| `sessions/` | one workspace per session; deleted at session end unless `DI_RETENTION=keep` |
| `cache/` | LLM response cache (`DI_RETENTION=keep` only) |
| `baseline/` | outputs of the original notebooks, used by `di eval baseline` |
| `labels/` | hand-made answer keys (`title_block_truth.json`, `symbol_counts.json`) |
| `eval/seeded/` | the planted-error drawings (A5a) and their answer keys; see its README |
| `telemetry.db` | anonymous per-call cost and latency; no drawing content |
