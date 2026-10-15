# Spikes

Throwaway code for the Phase 1 spikes in [`docs/01_discovery.md`](../docs/01_discovery.md) §10. A spike answers
one question within a fixed time box; its output is a **finding**, not production code. Findings are written in
[`docs/spikes/`](../docs/spikes/), one file per spike.

| Spike | Code folder | Findings |
|---|---|---|
| A · User validation | [`spike_a_user_validation/`](spike_a_user_validation/) (desk estimate; the timed check is manual) | [`spike_a_user_validation.md`](../docs/spikes/spike_a_user_validation.md) |
| B · Rulebook extraction | [`spike_b_rulebook/`](spike_b_rulebook/) | [`spike_b_rulebook.md`](../docs/spikes/spike_b_rulebook.md) |
| C · Template coverage | [`spike_c_template_coverage/`](spike_c_template_coverage/) | [`spike_c_template_coverage.md`](../docs/spikes/spike_c_template_coverage.md) |
| D · Symbol recognition | [`spike_d_symbols/`](spike_d_symbols/) | [`spike_d_symbols.md`](../docs/spikes/spike_d_symbols.md) |
| E · LLM judgement | [`spike_e_llm_judgement/`](spike_e_llm_judgement/) | [`spike_e_llm_judgement.md`](../docs/spikes/spike_e_llm_judgement.md) |
| F · Planted-error realism | — (manual: proxy rates each case) | [`spike_f_planted_error_realism.md`](../docs/spikes/spike_f_planted_error_realism.md) |
| G · Provider data policy | — (desk research) | [`spike_g_provider_data_policy.md`](../docs/spikes/spike_g_provider_data_policy.md) |

## Rules

1. **Never imported by the package.** `src/` and `tests/` must not depend on anything here. If spike code proves
   useful, rewrite it properly in `src/` with tests.
2. **Use the package, don't copy it.** Import from `drawing_intelligence` (installed by `uv sync`) and run scripts
   with `uv run python spikes/<folder>/<script>.py`.
3. **Don't touch committed data.** Never write into `data/`. Prefer calling package functions directly (e.g.
   `extraction.pipeline.extract_pdf(pdf)` with no `out_dir`) over the `di` CLI: the CLI opens a session, which
   sweeps `data/sessions/` and writes `data/telemetry.db` (risk R17). After any CLI run, check `git status`.
4. **Outputs:** bulky or per-drawing output goes in `spikes/<folder>/out/`, which is git-ignored. Commit only
   small summary files (a CSV or JSON table) in `spikes/<folder>/results/`, and quote the key numbers in the
   findings document.
5. **Money:** Qwen models only. Each paid spike has a budget cap in its findings document; check `di telemetry`
   or your own token log as you go. Never call `gpt-6-astra` without Binjie's OK.
6. **Lint:** CI runs `ruff check .` and `ruff format --check .` over the whole repo, including this folder, so
   keep spike scripts ruff-clean. Pyright and pytest don't look here.
7. **Time box:** when it runs out, stop, write down what is known, and move what is unresolved to the risk
   register.
