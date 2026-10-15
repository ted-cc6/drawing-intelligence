# 0008 Review contracts enforce the trust rules; findings are issues only

**Status:** accepted · 2026-10-15

## Context
Every reviewer, the verifier, the eval and the report share one set of review types (task A2). Spikes C, D and E
measured what each source of a finding can be trusted with:
- **Spike E:** an LLM reviewer catches planted errors (10/10), but only 32–61% of its findings are right. It doesn't apply numeric limits, and it set severity wrongly (a benign heat treatment came back Critical).
- **Spike D:** the vision model found 0/32 surface-finish marks and 0/9 datum flags. The GD&T it did report came from the text layer, not the image. The PDF text layer and vector geometry are exact.
- **Spike C:** 86% of sheets print `#` for material on purpose.

If these limits are only conventions, every new reviewer has to remember them.

## Decision
`schemas/review.py` and `review/rulebook.py` enforce them as validators:
- **LLM findings:** a finding with `source: llm` can only be a `warning`. An `llm` rule cannot fail.
- **Severity:** it comes from the rule. `new_finding()` copies it, and a finding without a rule must be a warning with severity `info`.
- **Fails need exact evidence:** a `fail` needs every evidence item to come from `pdf_text` or `vector`. Vision-only evidence caps the finding at a `warning`.
- **Stable finding IDs:** the ID is a hash of the rule and the evidence keys (page, kind, ref), not the wording. The same issue gets the same ID on every run, which makes dedup, eval matching and engineer feedback possible.
- **Findings are issues only:** the per-rule outcome (pass, fail, warning, not applicable, not checked) is a separate `RuleStatus`, which feeds the report's Pass/Fail column.
- **Severity levels:** `critical | major | minor | info`, provisional until the client confirms. Categories are the client's checklist categories plus `consistency`, `manufacturability` and `design_intent`.
- **Engineer feedback:** `FindingFeedback` (accept or reject, by finding ID) is defined now and stored as session data.
- **Rulebook loading:** rules live in `config/rules/*.yaml`. The loader reports every problem at once, and can check rule params against the registered check functions.

## Consequences
- A reviewer cannot produce an untrustworthy *fail*, even by mistake; it fails validation instead.
- Severity, and so the order of the report, can only change through the rulebook, which is versioned and reviewed.
- Weakening a trust rule takes a schema change and a new ADR.
- The extraction stage still marks every symbol `source: "vision"`. Symbols from text and vectors (Spike D) need a `DrawingKnowledge` change; that is a separate task, and evidence can already cite symbol IDs with `provenance: vector`.
