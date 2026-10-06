# Architecture decision records

Short records of decisions that shape the project: the context, the decision, and what it costs.
Add one when a decision would surprise a new teammate. Never edit an accepted record's decision; supersede
it with a new one.

| # | Decision | Date |
|---|---|---|
| [0001](0001-workflow-plus-qa-agent.md) | Fixed LangGraph workflow for review, one agent for Q&A | 2026-10-06 |
| [0002](0002-openai-sdk-direct.md) | Call OpenAI and Qwen through the `openai` SDK in our own `llm/` module | 2026-10-06 |
| [0003](0003-session-scoped-data.md) | Client data lives only for one session | 2026-10-06 |
| [0004](0004-model-registry.md) | One model registry file drives model choice, prices and thinking | 2026-10-06 |
| [0005](0005-typed-contracts-and-baseline.md) | Redesign while porting, guarded by typed contracts and a baseline diff | 2026-10-06 |
| [0006](0006-tooling.md) | uv, ruff, pyright, pytest, pre-commit, CI on three OSes | 2026-10-06 |
| [0007](0007-commit-client-data.md) | Commit the client data to the repository (keys stay out) | 2026-10-06 |
