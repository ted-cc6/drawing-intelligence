# 0010 How the review stage runs the rulebook

**Status:** proposed (for team review before A4 starts) · 2026-10-23

## Context
ADR 0001 fixed the shape of stage 3 (parallel specialist reviewers, then a verifier) and ADR 0008 fixed the
contracts (`Rule`, `Finding`, `RuleStatus`, `ReviewResult`). Three things between them were never decided:

- **How a rule becomes a finding.** The draft rulebook (task R) has 174 rules naming 130 check functions
  (110 `code`, 25 `lookup`, 39 `llm` rules; no `llm` rule names a function). None is built.
- **Which reviewer runs which rules.** `docs/PROJECT.md` drew four reviewers (consistency, standards,
  manufacturability, design intent); the rulebook has eleven categories.
- **How the parallel reviewers share the graph state**, and what happens when one is missing or fails.

A4 builds the first check function. The other 129 will copy its pattern, so the pattern is decided here.

## Decision

### 1. Check functions (`code` and `lookup` rules)
- A check is a **plain, pure function** in `src/drawing_intelligence/review/checks/`, one module per category
  (`consistency.py`, `title_block.py`, ...). It is registered by name with its params model:

  ```python
  class ChainSumParams(BaseModel):
      model_config = ConfigDict(extra="forbid")


  @check("chain_sum", ChainSumParams)
  def chain_sum(ctx: ReviewContext, rule: Rule, params: ChainSumParams) -> list[Finding]: ...
  ```

- The registry (`check name -> (function, params model)`) is what `load_rulebook(checks=...)` already accepts,
  so `di rules` reports any rule whose check name or params are wrong.
- **Input:** a read-only `ReviewContext` with the `Extraction`, the per-page `DrawingKnowledge` (`None` for a
  page whose understanding is missing or invalid), the `Rulebook`, and the reference tables. A check loops over
  the pages itself, so cross-page checks need no special case.
- **Output:** a list of findings, each made with `new_finding(rule, ...)`, so category, severity and source
  always come from the rule. An empty list means the rule passed.
- **Other outcomes are exceptions:** `raise NotApplicable(reason)` (e.g. no threads on the drawing) or
  `raise NotCheckable(reason)` (e.g. the check needs `DrawingKnowledge` and there is none). Any other exception
  is caught by the runner, logged, and recorded as `not_checked` with the error as the note. One broken check
  never stops a review.
- **No I/O, no LLM, no randomness.** Same input, same findings. Every check has unit tests on a synthetic
  sheet.
- **`lookup` = `code` + a table.** A lookup check is written the same way; its table (approved materials,
  IS 919 fits, thread sizes, ...) is data in `config/reference/*.yaml`, loaded once into the context. The
  tables' hash is added to the rulebook version, so a table change shows up in every `ReviewResult`.

### 2. Which reviewer runs which rules: split by check type, not category
- **One deterministic reviewer, `checks`,** runs every applicable `code` and `lookup` rule (135 rules, all
  categories). Code takes milliseconds, so splitting it gains nothing, and one runner means one way of
  handling statuses and errors.
- **Three LLM reviewers** run the 39 `llm` rules. Each makes **one call** with all its rules, the drawing JSON
  (text, not images) and a strict output schema (`rule_id`, evidence refs, comment, correction). Each item
  becomes a warning through `new_finding`:

  | Reviewer | `llm` rules from categories | Rules |
  |---|---|---|
  | `drawing_practice` | consistency, datum, thread_weld, inspection | 21 |
  | `manufacturability` | manufacturability | 4 |
  | `design_intent` | design_intent, surface_treatment | 14 |

  The mapping is one dict in `review/reviewers.py`. A test fails if an `llm` rule's category has no reviewer.
  The model comes from `defaults.review` in `config/models.yaml`.
- An LLM reviewer may also return an observation no rule covers (`rule_id: None`, warning, severity `info`).
- The plan's "standards" reviewer is absorbed into `checks`: IS 2102 and the PARI guidelines are lookup rules.
- `Finding.category` keeps the domain for the report and the eval. `Finding.reviewer` says which node produced
  it.

### 3. Graph state, fan-out and join
- `understand` fans out to every built reviewer node in parallel. They join at `verify`, then `report`.
- As today, the graph state holds **paths only**. Each reviewer writes `review/<reviewer>.json` (a
  `ReviewerOutput`: findings, the statuses of its own rules, cost, latency, error) and returns
  `{"reviewer_outputs": [path]}`. The state field is
  `Annotated[list[str], operator.add]`, so parallel writes are appended, not overwritten.
- **Missing reviewers:** `review/reviewers.py` lists every planned reviewer. One that isn't built, or an LLM
  reviewer when understanding is off or invalid, is not added to the graph. It goes in
  `ReviewResult.reviewers_skipped`, and its rules are `not_checked`.
- **A reviewer that crashes** writes its output with the error, and its rules become `not_checked`. The graph
  goes on.
- **`verify`** reads every output in the planned-reviewer order, so the result doesn't depend on which node
  finished first, and then:
  1. **drops** a finding whose evidence doesn't resolve: its dimension, symbol or note id doesn't exist on that
     page, its bbox is outside `page_size_pts`, its title-block field is unknown, its `rule_id` isn't in the
     rulebook, or a `pdf_text` quote isn't what the drawing says (a cited dimension or title-block field must
     read exactly the quote; quoted text must appear on the page). Each drop is kept with a reason in `review/rejected.json`, and the count goes in
     `ReviewResult.extra`.
  2. **merges duplicates** by finding id (same rule, same evidence; ADR 0008). The first one is kept and the
     reviewers are listed in its comment.
  3. **sets one `RuleStatus` per rule:**
     - a fail finding makes the rule `fail`, else a warning makes it `warning`
     - otherwise the status the reviewer gave: `not_applicable` or `not_checked`
     - otherwise `pass`
     - a rule outside `applies_to` is `not_applicable`; a rule whose check isn't built is `not_checked`
  4. writes `review/review_result.json` (a `ReviewResult`). `report` reads only that file.

## Consequences
- A4 builds the framework (registry, `ReviewContext`, runner, the `checks` node) together with the first
  consistency checks. After that, adding a rule's check is one function and its tests, with no graph change.
- Rules can be added or edited in YAML without code, as long as their check exists. `di rules` validates the
  params of every built check. An unknown check name is not an error: it shows as "not built", so a typo
  shows up in the coverage count.
- 135 of 174 rules cost $0 and are reproducible. LLM cost is three text-only calls per drawing.
- Until a check is built, its rule is `not_checked`, never silently `pass`. The report shows how much of the
  rulebook actually ran.
- **Open:** an `llm` rule with no finding is reported `pass`. Spike E found high recall (10/10), but that rests
  on a small sample. If A5b shows misses, report it as `not_checked` instead.
- This refines the stage-3 list in ADR 0001. The workflow-plus-agent decision there stands.

## Added while building the first slice (2026-10-23)
- **Title-block values come from stage 1, by position.** Each field is read from its template cell
  (`config/templates/*.yaml`), so title-block findings rest on exact `pdf_text` evidence and can fail. A sheet
  whose template labels are not where expected is a variant title block: no fields are read, and its title-block
  rules are `not_checked`.
- **CN-002 (`conflicting_values`) uses geometry first.** Two dimensions drawn the same length, where one matches
  the sheet's scale and the other doesn't, are flagged. An LLM "same feature" relation can be added later.
- **What stage 1 derives by code stays out of the understanding prompt** (title-block fields, tolerance-table
  rows, ordered limits, chain ids). Their raw text is in the prompt already, and the prompt stays the one ADR 0009
  chose the model on; a test checks it. Adding them would be a prompt change, to measure with `di eval
  understand` first.
- **Stacked limits are ordered by where they are printed** (`TextItem.limits`, upper first). The joined text
  keeps the PDF's storage order, which is not always upper first.
- **Session workspaces are no longer committed.** `data/sessions/` is git-ignored (a narrow exception to ADR
  0007: it is run history, not client data). `di eval review` runs its sessions in a temporary folder.
