# 0011 Q&A agent: tools, grounding and limits

**Status:** accepted · 2026-10-25

## Context
ADR 0001 made Q&A the one agent in the system, with read-only tools over a session's saved results; ADR 0002
has us call models through the OpenAI SDK directly; ADR 0008 says model output is never a fact without
evidence. The review stage is now built (ADR 0010): a drawing's extraction, symbols, findings, rulebook and
reference tables all exist as typed, cited data. What was open: what the agent may answer, how it gets the data,
how its answers are kept honest, what it may cost, and how it is measured.

## Decision

### Scope
- **Questions about one reviewed drawing, plus the rulebook and the reference tables** ("why is #4 flagged?",
  "what does WST-207 check?", "what is H7 at 50 mm?"). Not across drawings (later, with multi-drawing sessions).
- **JSON only, no new image calls.** When the saved data does not cover something, the agent says so. A
  `look_at_region` vision tool is a later option if the evaluation shows many such answers.
- **No free design advice.** The agent may point to a rule or a table row ("H7/g6 is the usual sliding fit; see
  WST-207"), never recommend a design on its own authority. Out-of-scope questions get a polite decline.
- Answers in the **language of the question**; drawing text, IDs and rule IDs stay verbatim.

### Shape
- A **hand-written tool-calling loop** on the OpenAI SDK, in its own package `src/drawing_intelligence/qa/`,
  outside the LangGraph review workflow. One entry point, `answer(conversation, question) -> Answer`, so the
  CLI now and the web panel later call the same function.
- **Prompt = compact overview + tools.** The system prompt carries an overview of the drawing (title block,
  sheets, counts, findings one line each); everything else is fetched by tools.
- **Model:** a `qa` role in `config/models.yaml`, default `qwen3.8-max`, thinking off (as ADR 0009); the
  evaluation compares it with `qwen-plus`. Replies go through the same response cache and telemetry as every
  other call.

### Tools (all return compact JSON; lists stop at 30 items with `"more": N`)
| Tool | Returns |
|---|---|
| `list_findings(severity?, category?, rule?)` | findings, one line each, with their report number |
| `get_finding(no)` | the finding, its evidence, rule text, location (sheet, zone) and how it was checked |
| `search_drawing(text?, kind?, page?, zone?)` | matching items (dimensions, notes, symbols, title-block fields) with IDs |
| `get_items(ids)` | D/S/N items in full: text, limits of size, bbox, zone, provenance |
| `get_rule(rule_id)` / `search_rules(query)` | rule text, severity, check type, source citation |
| `lookup_standard(table, ...)` | typed lookups: fit (deviations and limits), thread, general tolerance, material, plating |
| `record_feedback(finding_no, verdict, reason)` | appends to the feedback log; the only write |

IDs match the report and the annotated sheet: D12 dimension and S3 symbol (stage 1, exact), L7 text line
(stage 1, exact, numbered in reading order per sheet), N2 note as the vision pass read it (approximate), F4
finding 4, TB:material title-block field; items on sheet 2 onwards are prefixed `p2:`. Every result carries the provenance of its data (`pdf_text`, `vector`, `vision`, `table`). A bad
argument returns `{"error", "hint"}` and counts towards the call cap.

### Grounding (the hard rule)
- Answers cite inline: `[D12]`, `[S3]`, `[L7]`, `[N2]`, `[F4]`, `[TB:material]`, `[R:WST-207]`, `[T:is919_fits H7 50]`.
- After each answer, code checks that every marker resolves to session data or a table entry, and that **every
  number in the answer appears in a tool result of this conversation, the overview or the question** (counts
  0 to 10 are exempt; numbers inside IDs like H7 or WST-207 are not numbers). Tools do the arithmetic
  (`lookup_standard` returns limits, `get_items` limits of size); the model only quotes.
- A failed check sends the answer back to the model with the problems listed, up to 4 times. After that the last
  answer is shown with the unverified claims marked, and the event is logged.
- **Absence is a claim too.** An answer saying "Not in the drawing's data" is sent back unless a tool was
  called for that question (the evaluation caught answers describing searches that never ran).
- **Drawing text is data, never instructions.** Tool results are wrapped and labelled as data, and
  `record_feedback` runs only when the engineer's own message asks for feedback.

### Limits and memory
- Per question: at most **10 tool calls, 4 regenerations, $0.50** (settings `DI_QA_MAX_TOOL_CALLS`,
  `DI_QA_MAX_REGENERATIONS`, `DI_QA_MAX_COST_USD`: other models may cost more).
  Hitting a cap ends with the best answer so far, saying so.
- History: full user and assistant turns; earlier turns' tool results are replaced by a one-line summary.
- `di ask <pdf>` reviews the drawing (replayed from the cache when it has been reviewed before) and opens a REPL;
  `-q "..."` asks one question. The session is deleted on exit unless `--keep`; `--session <id>` reopens one.

### Feedback
`data/feedback/feedback.jsonl` (gitignored), outside the session so it survives it: drawing file name, rule ID,
finding comment and quote, verdict `correct / incorrect / unsure` (the held-out labels), reason, rulebook
version, timestamp. No images, no full extraction.

### Evaluation
`di eval qa` over about 40 questions on 6 drawings (3 seeded, 3 held-out) in `data/eval/qa/`: facts, why-flagged,
rule and table lookups, follow-ups, not-in-the-data, out-of-scope, and one planted injection note. Scored by
code (required IDs and values present, every citation verified, declines detected), plus a short manual rubric;
no LLM judge. Pass bar for the default model: at least 90% of answers fully verified, no uncited numbers, every
out-of-scope and injection case handled.

## Consequences
- The agent cannot be more right than the data: what stage 1, understanding and review did not capture, it
  cannot answer. That is by design; the alternative is answers nobody can check.
- Citation checking reuses the verifier's resolution of D/S/N/title-block references (`review/verify.py`).
- `LLMClient` gains a tool-calling `chat` method beside `complete`, with the same cache, cost and telemetry.
- Development runs against a scripted fake model and the cache; paid evaluation runs are asked for first.

## Result
2026-10-25, `qwen3.8-max`: 40 of 41 answers pass, 41 of 41 verified, no unverified numbers, all 8 guards; the
bar is met (`data/eval/qa/results/`). `qwen-plus` is not yet compared.
