# Spike D · Symbol recognition

Throwaway code for Spike D. Question, success criteria and findings:
[`docs/spikes/spike_d_symbols.md`](../../docs/spikes/spike_d_symbols.md).

| Script | What it does | Cost |
|---|---|---|
| `common.py` | The 10 drawings, the model, and an LLM client whose cache and telemetry live in `out/` | — |
| `answer_key.py` | Builds the answer key: GD&T from the text layer (exact), datum flags and finish marks from vector geometry, plus `results/manual_labels.json`; draws review overlays in `out/answer_key/` | free |
| `run_understand.py` | Runs stage-2 understanding with `qwen3-vl-plus`, thinking off and on; resumable, with a budget guard | ≤ $1 |
| `score.py` | Correct / phantom / missed per symbol type and setting → `results/scores.csv`, `results/per_page.csv` | free |

```bash
uv run python spikes/spike_d_symbols/answer_key.py
uv run python spikes/spike_d_symbols/run_understand.py --dry   # one page, prints the projected cost
uv run python spikes/spike_d_symbols/run_understand.py
uv run python spikes/spike_d_symbols/score.py
```

To review the answer key, open `out/answer_key/<drawing>_p<n>.png`: magenta = GD&T, blue = datum, red = surface
finish. Fix anything wrong in `results/manual_labels.json` (`remove` an auto id or `add` a symbol), then rerun
`answer_key.py` and `score.py`.
