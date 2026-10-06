# 0001 Fixed LangGraph workflow for review, one agent for Q&A

**Status:** accepted · 2026-10-06

## Context
The system has two workloads. Batch review runs the same steps on every drawing. Q&A is open-ended. Inputs
are vector PDFs on one template, the budget is a few minutes and about $1 per drawing, and the review must
cover four kinds of error (arithmetic, standards, manufacturability, design intent).

Options considered:
- One agent with every tool (extraction through review).
- Many agents that hand work to each other.
- A fixed workflow, with an agent only where the path really varies.

## Decision
- The review path is a **fixed LangGraph graph**: intake (code) → understand (one vision call) → parallel
  specialist reviewers → verifier (code) → report.
- **Q&A is the one agent**, with read-only tools over the session's saved results.
- Extraction is a deterministic node, not an agent.

## Consequences
- Every check runs every time, in the same order, so results are reproducible and explainable to a client.
- Only judgement steps pay for an LLM. Reviewers read text JSON, not images, and run in parallel.
- Specialist reviewers keep separate prompts and reference knowledge, without the token cost of agents
  talking to each other.
- A single agent would skip or reorder checks and carry images plus all reasoning in one growing context.
  We accept being less flexible on the review path in exchange.
