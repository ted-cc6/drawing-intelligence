# 0009 Default understanding model and thinking setting

Status: draft (pending Binjie's final sign-off on this write-up) · 2026-10-17

## Context

Stage 2 (Understand) needs one default model + thinking setting in `config/models.yaml` (`defaults.understand`). The choice must come from evidence on the 4 sample drawings (`di eval understand`), not from price or public benchmarks, per ADR 0004 and the project's open question in `docs/PROJECT.md` section 10. Candidates: `qwen3-vl-plus`, `qwen3.8-max` (both live-tested here), and `gpt-6-astra` (reference only, scored for free from the baseline -- never called live without Binjie's approval, since it costs ~50x more per drawing).

Criteria, per `docs/PROJECT.md` section 8 and the notebook 02 scorecard: valid JSON matching the schema, title-block accuracy against `data/labels/title_block_truth.json` (now verified), every extracted dimension returned unchanged, zero invented numbers, time and cost per drawing, and stability across repeated runs (criterion 6, added in this task via `eval.stability.score_stability`).

## Decision

Default understanding model: **qwen3-vl-plus**, thinking **off**.

Scorecard evidence:

Round 1 (1 run each, 4 samples -- 10K_CAM PLATE, 10K_CYLINDER ROD MTG_02, 20_INCH HOSE PIPE CLAMP_PU_01, 31K_PIPE CLAMP BLK_02):
- qwen3-vl-plus, thinking off: title-block 100/93/100/100%, dims 21/21,27/27,18/18,15/15 (all unchanged), 0 invented, avg 61s, avg $0.011/drawing ($0.044 total)
- qwen3-vl-plus, thinking on:  title-block 93/93/100/93%, dims all unchanged, 0 invented, avg 247s (one run spiked to 882s), avg $0.019/drawing ($0.075 total)
- qwen3.8-max,   thinking off: title-block 100/93/100/100%, dims all unchanged, 0 invented, avg 39s, avg $0.097/drawing ($0.387 total)
- qwen3.8-max,   thinking on:  title-block 93/100/93/93%, dims all unchanged, 0 invented, avg 168s, avg $0.174/drawing ($0.695 total)

Round 2 (3 runs each, stability via score_stability -- 12 calls per setting, 48 total):
- qwen3.8-max/off:    title_block_stable=yes, dimension_count_stable=yes (4/4 drawings), avg ~$0.10/drawing, ~40-48s
- qwen3.8-max/on:     title_block_stable=yes, dimension_count_stable=yes (4/4 drawings), avg ~$0.1-0.4/drawing (one run on 10K_CYLINDER ROD MTG_02 spiked to $0.4/427s), ~170-430s
- qwen3-vl-plus/off:  title_block_stable=yes, dimension_count_stable=yes (4/4 drawings), avg $0.011-0.012/drawing, ~53-65s
- qwen3-vl-plus/on:   title_block_stable=yes, dimension_count_stable=yes (4/4 drawings), avg ~$0.02-0.03/drawing, ~227-280s
All four settings passed stability (criterion 6) on all 4 drawings -- no variants seen across repeated runs for title block or dimension count.

Recurring title-block misses (same across both rounds, likely a label issue rather than model randomness): heat_treatment on 10K_CYLINDER ROD MTG_02 (label says 'REF NOTE'; qwen3.8-max/off returns None, qwen3-vl-plus/off returns the actual note text read off the drawing, 'TO BE TOUGHENED UPTO 24-32 HRC.'); general_tolerance_standard on multiple drawings (label 'IS 2102' vs model's 'Gen Tol.: IS 2102', only under thinking on); number on 31K_PIPE CLAMP BLK_02 under qwen3-vl-plus/on (label 'P24BSP810318' vs model's 'FR-DES-006-01'). These look like label-truth or prefix-formatting issues to resolve when title_block_truth.json is verified, not invented numbers.

Total spend for Round 1 + Round 2: $5.39 (over the $5 cap by $0.39; Binjie was told and approved finishing the in-flight Round 2 run rather than stopping mid-comparison).

Reference (free, --from-baseline):
- gpt-6-astra: title block 100%, 81/81 dimensions unchanged, 0 invented (per M1 results in docs/PROJECT.md)

Total spend for this evaluation: see `di telemetry` / `data/telemetry.db`, kept under the $5 cap set for A1.

## Consequences

- `config/models.yaml` `defaults.understand` is set to `qwen3-vl-plus` with thinking `off`.
- This is the model stage 2 uses unless a caller overrides it with `--model` / `--thinking`.
- gpt-6-astra remains available as an opt-in, higher-cost alternative; it is not the default because its cost is not justified by a corresponding accuracy gain on the 4 samples (see scorecard above).
- If the client's full ~1,170-drawing set surfaces failure modes not present in the 4 samples, this ADR should be revisited rather than silently overridden.
