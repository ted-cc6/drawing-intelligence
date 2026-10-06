# 0005 Redesign while porting, guarded by typed contracts and a baseline diff

**Status:** accepted · 2026-10-06

## Context
Notebooks 01 (PDF extraction) and 02 (vision LLM) were moved into a package, with a redesign during the move
rather than a line-by-line port. Without a "matches the notebook" check, there must be another way to tell
that nothing got worse.

## Decision
Redesigned:
- Typed Pydantic contracts with a `schema_version` for `Extraction` and `DrawingKnowledge`. The
  `DrawingKnowledge` model is also the strict JSON schema sent to the LLM.
- Every page of a PDF is processed.
- Template regions and glyph remapping live in `config/templates/*.yaml`.
- Image rendering for review (`viz/`) is separate from the pipeline.
- Image tiling is configurable, so the eval can trade cost against quality.

Moved unchanged, with unit tests: the classification regexes and the token-cleanup heuristics. They were
tuned by hand on real drawings, and rewriting them without labelled data is too risky.

Guard: `di eval baseline` diffs new extraction outputs against the notebooks' saved outputs, and the
understanding scorecard (criteria 1–4 and 7 from notebook 02) is ported to `di eval understand`.

## Consequences
- Every later stage reads typed objects, and a schema change is visible as a version bump.
- Differences from the notebooks are reported for a human to explain, not blocked.
