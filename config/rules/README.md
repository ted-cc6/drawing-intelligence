# Rulebook

What the review checks on a drawing, as data. Every `*.yaml` file in this folder is loaded and validated by
`load_rulebook()` (`src/drawing_intelligence/review/rulebook.py`). Run `uv run di rules` to validate and summarise
it. Any edit changes the rulebook version, and that version is recorded in every review result.

## Format

```yaml
rules:
  - id: TB-001                      # source prefix + 3 digits, unique across all files (see IDs below)
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

**IDs** keep the prefix of the document a rule comes from, so every rule traces back to it:
- LatentView's Rulebook and Detection Guide keep their own prefixes, padded (`TB-01` → `TB-001`, `MD-01` → `MD-001`).
- `WPM`, `WPS`, `WPE` and `WPW` are PARI's WP guidelines: material and heat treatment, surface treatment, US-India
  material equivalents, and welding notes.
- `CN` and `RQ` come from the team's requirements (`docs/01_discovery.md`) and the errors the team found on PARI's
  sample drawings.
- `ISO`, `NASA`, `HNF`, `DSM`, `DTT` and `WST` come from engineering-drawing books: ISO 129, NASA Goddard's drawing
  standards manual, Hanford's HNF-64101, the NAAMS design drawing standards, a D&T tutorial, and the Westermann
  Tables (Indian Standards) that PARI supplied.

A prefix is not a category: `LY-005` is a `tolerance` rule. [docs/rulebook/](../../docs/rulebook/) records where
every LatentView and book rule went: encoded here, merged into another rule, or left out and why.

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
