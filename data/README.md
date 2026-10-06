# data/ (git-ignored)

Everything in this folder except this file is ignored by git. Client drawings and anything derived from
them must never be committed.

| Folder | Contents |
|---|---|
| `raw/` | input PDF drawings |
| `sessions/` | one workspace per session; deleted at session end unless `DI_RETENTION=keep` |
| `cache/` | LLM response cache (`DI_RETENTION=keep` only) |
| `baseline/` | outputs of the original notebooks, used by `di eval baseline` |
| `labels/` | hand-made answer keys (`title_block_truth.json`, `symbol_counts.json`) |
| `telemetry.db` | anonymous per-call cost and latency; no drawing content |
