# Rulebook

What the review checks on a drawing, as data. Every `*.yaml` file in this folder is loaded and validated by
`load_rulebook()` (`src/drawing_intelligence/review/rulebook.py`). Run `uv run di rules` to validate and summarise
it. Any edit changes the rulebook version, and that version is recorded in every review result.

## Format

```yaml
rules:
  - id: TB-001                      # category prefix + 3 digits, unique across all files
    category: title_block           # see the list below
    requirement: The title block states the material.
    severity: major                 # critical | major | minor | info (provisional until the client confirms)
    check_type: lookup              # code | lookup | llm
    check: title_block_field        # registered check function; required for code and lookup
    params: {field: material, placeholder_ok: ["#"]}
    applies_to: {part_family: [prismatic, round], drawing_type: [machining, fabrication]}  # default: all
    source: {document: Check List.docx, section: Title block requirements}
    status: draft                   # draft | client_confirmed
```

**Categories** (the client's checklist, plus three the review adds): `title_block`, `material`, `tolerance`,
`gdt`, `datum`, `thread_weld`, `surface_treatment` (surface finish / coating / heat treatment), `inspection`,
`consistency`, `manufacturability`, `design_intent`. The checklist's "common rejection conditions" go in their
own category with severity `critical`.

## What the check type decides

| check_type | Who checks | Can it *fail* a drawing? |
|---|---|---|
| `code` | a deterministic function (arithmetic, presence, format) | yes, with exact evidence |
| `lookup` | a table lookup (IS 2102 tolerances, material names, thread series) | yes, with exact evidence |
| `llm` | a reasoning model | **no**: warnings to confirm only (Spike E) |

The severity of a finding is always the rule's severity, never the model's. A *fail* must cite evidence read
from the PDF text layer or vector geometry. Anything resting only on vision is a warning (Spike D).

## Tips for drafting

- **Numeric limits go in `params`, checked by code.** An example is depth ≤ 10 × diameter. Spike E showed the model doesn't apply numeric rules reliably.
- **Allow the client's placeholders.** About 86% of sheets print `#` for material, meaning "see the parts list" (Spike C). A presence check should take a `placeholder_ok` list rather than flagging those.
- **Keep `status: draft`** until LatentView/PARI confirm the rule.
