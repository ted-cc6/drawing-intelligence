# Design: Run history across users and Feedback analytics (demo)

Date: 2026-11-14. Status: draft, for Binjie's approval.

## Intent
Two of the four commands still marked PILOT (Reports > Run history / Cost & latency, and Reports > Feedback
analytics) should show in a demo what the pilot would give the rulebook owner and the team lead: every review
anyone ran, what it cost and how long it took per model, and how often engineers accept or reject each rule's
findings. Demo only: kept in the server's memory, lost when the Space restarts (Binjie accepted this).

## Goals
- **Run history across users:** one row per finished review by anyone using this server since it started:
  time, visitor, drawing, mode, status, findings, fails, review time, review cost, Q&A cost, model. "Across users"
  means across browsers: everyone shares one password, so each browser is an anonymous "Visitor N".
- **Cost & latency per model:** from the same rows, per understanding model.
- **Feedback analytics:** accept/reject counts and rates overall, code vs AI, per reviewer, and per rule (most
  rejected first).
- Free to demo: opening the four cached demo drawings and deciding a few findings fills both pages, $0.

## Non-goals
- No database, no persistence across restarts, no accounts or sign-in per person.
- The other two PILOT commands (Confirm rules, Edit rule) stay PILOT.
- No change to the review pipeline, telemetry schema, rules or eval.
- The existing feedback log (`data/feedback/feedback.jsonl`, written by the Accept/Reject endpoint and by the Q&A
  agent's `record_feedback` tool, gitignored, kept after sessions end) is left as it is: changing what it keeps is
  a separate question about ADR 0003 (builder check, settled by Claude: out of scope, flagged to Binjie).

## Anti-goals
- **Nothing new from an upload outlives its session** (ADR 0003, CLAUDE.md hard rule 4): an uploaded drawing is
  listed as "Uploaded PDF", never by file name; demo drawings (committed, public) show their catalogue title.
  Feedback rows carry rule id, category, source, reviewer, result and decision only, never comments or quotes.
- No rows added to the committed `data/telemetry.db` by this feature.
- Both pages say plainly that they are a demo kept in memory since the server started.

## Constraints
- CLAUDE.md hard rules (no live model calls in tests, pathlib only, all checks pass).
- The demo API has one shared password and one token for everyone (`api/app.py`), so the server cannot tell
  browsers apart without help from the browser.
- `DemoSession` (`api/runs.py`) already has what a row needs: `demo_id`, `live`, status, `seconds` (from
  `started`/`finished`), `billed()`, `qa_cost`, `cached()`, the model, and `data.findings` for feedback.

## Approaches (picked: A)
- **A. In the server's memory (picked by Binjie).** The session store keeps a run ledger and a feedback ledger
  for the life of the process; two read-only endpoints summarise them. Means exactly "since the Space started",
  adds nothing about uploads to disk, touches no committed file. The pilot swaps the ledger for a database
  behind the same small interface.
- **B. New tables in `data/telemetry.db`.** Closer to the long-term design (PROJECT.md plans feedback there),
  but that file is committed, so local demo runs would end up in git, its old local rows would need filtering
  to mean "since start", and the schema changes.
- (Front end only was ruled out: it cannot see other browsers.)

## Design

### Visitors
The browser makes a random id once and keeps it in `localStorage` (`di-visitor`); `api.ts`'s `call()` sends it
on every request as `X-Demo-Visitor`. The server numbers ids in the order it first sees them: "Visitor 1",
"Visitor 2"… (in memory). Responses mark the caller's own rows `you: true`, and the UI shows "Visitor 2 (you)".
A request without the header counts as "Visitor ?" (e.g. the CLI or tests).

### Ledgers (`src/drawing_intelligence/api/ledger.py`, new)
A small thread-safe class `Ledger`, owned by `SessionStore`:
- `record_run(sess, visitor)` when a session's review ends `done` or `error` (not `cancelled`). Row: `session_id`,
  `at` (UTC ISO time), `visitor` (id), `drawing` (the demo's title, or "Uploaded PDF" when `demo_id` is None),
  `mode` ("Demo (cached)" / "Live upload" / "Batch" for batch members), `status`, `findings`, `fails`,
  `seconds`, `cost_usd` (`billed()`), `qa_cost_usd`, `model`, `cached`.
- `add_qa_cost(session_id, usd)` after each answered question, so Q&A cost shows on the run's row even after the
  session is closed.
- `record_feedback(session_id, visitor, finding, decision)`: keyed by (session, finding id), so a changed
  decision replaces the old one. Row: `rule_id`, `requirement`, `category`, `source` (code / lookup / llm),
  `reviewer`, `result`, `decision`, `at`. The requirement text is the rulebook's, not the drawing's.
  A finding with no rule (`rule_id` None, an AI finding whose requirement is model-written and may quote the
  drawing) is recorded without its requirement: it counts in the totals, `by_source` and `by_reviewer`, not in
  `by_rule` (builder check, settled by Claude).
- Only the Accept/Reject buttons feed the analytics; verdicts given in the Q&A chat do not (they use another
  vocabulary and live in the `qa/` package). The page says "decisions from the Accept/Reject buttons" (builder
  check, settled by Claude).
- `history(visitor) -> dict` and `feedback_summary() -> dict` build the two responses (below).
The visitor of a session is remembered at creation (`POST /api/sessions`, `/upload`, `/batches` read the header)
and stored on `DemoSession` as `visitor: str | None`.

### Endpoints (`api/app.py`)
- `GET /api/history` →
  `{"since": iso, "runs": [row + {"visitor": "Visitor 2", "you": bool}] newest first,
    "models": [{"model", "runs", "live_runs", "avg_live_seconds", "avg_live_cost_usd", "total_cost_usd",
                "qa_cost_usd"}], "visitors": n}`.
  `avg_live_*` average only live (not cached) runs that finished `done`; null when there are none. A run that
  ended in `error` is listed in the history with its status, counts toward `runs`, and is left out of the
  averages; its model is the one the user chose (`sess.models["model"]`) or null for the default (builder check,
  settled by Claude).
- `GET /api/feedback/summary` →
  `{"since", "decisions", "accepted", "rejected",
    "by_source": [{"source", "decisions", "accepted", "rate"}],
    "by_reviewer": [{"reviewer", "decisions", "accepted", "rate"}],
    "by_rule": [{"rule_id", "requirement", "source", "decisions", "accepted", "rejected", "rate"}]}`,
  `by_rule` sorted by rejected (desc), then decisions (desc), then rule id.
Both need the demo password like the other endpoints.

### Front end
- **Reports page** (`ReportsView` in `DocViews.tsx`), opened by Run history and Cost & latency as today, now
  fetches `/api/history` on open and every 5 s while open:
  ```
  [ 7 reviews since 14:02 ] [ 3 visitors ] [ $0.06 live cost ] [ 1m 52s average live review ]
  Run history
   Time   Visitor         Drawing                    Mode           Status Findings Fails Time  Cost   Q&A    Model
   14:31  Visitor 2 (you) P13 · Cam plate, fit lim…  Demo (cached)  done   4        3     2.9 s $0.000 $0.004 qwen3-vl-plus
   14:20  Visitor 1       Uploaded PDF               Live upload    done   9        5     1m 52s $0.031 $0.000 qwen3-vl-plus
  Cost and latency per model
   Model          Runs  Live  Avg live review  Avg live cost  Review cost  Q&A cost
  i Demo: kept in the server's memory since it started (14:02); a restart clears it. Uploaded drawings are
    listed as "Uploaded PDF": nothing about an upload outlives its session. In the pilot this history is stored
    and covers every user by name.
  ```
- **Feedback analytics** (Reports > Quality) loses `pilot` and opens a new doc kind `feedback` with
  `FeedbackView` (new): KPIs (decisions, accept rate, code accept rate, AI accept rate), a by-reviewer table, and
  a by-rule table (rule, requirement, source, decisions, accepted, rejected, accept rate as a small bar), plus a
  note: "Demo: decisions from every visitor since the server started; a restart clears them. In the pilot the
  rulebook owner reviews the most-rejected rules here." Refreshes like the Reports page.
- Empty states: "No reviews yet. Open a demo drawing to start." / "No decisions yet. Accept or reject findings
  on a drawing."

### Tests
- `tests/test_ledger.py` (unit, no server): run rows (demo title vs "Uploaded PDF", cancelled not recorded,
  Q&A cost added after the fact), visitor numbering and `you`, model summary (live-only averages, null when
  none), feedback replace-on-change, summary sorting and rates, and that no row holds an upload's file name.
- `tests/test_api.py`: two visitors (two header values) open demo drawings; `/api/history` lists both runs with
  "Visitor 1"/"Visitor 2" and `you` set for the caller; a decision then a changed decision shows once in
  `/api/feedback/summary` with the latest value; both endpoints need the password.

### Docs and deploy
ADR 0012 update and a progress note; still PILOT afterwards: Confirm rules, Edit rule. No Space redeploy unless
Binjie asks.

## Left to the builder
- Ledger internals (lists vs dicts, the lock), exact column widths and styling within the existing `.kpis`,
  `table.grid` and `.pilotnote` looks, the bar in the rate column.
- Where exactly in `_run`/`ask`/`record_feedback` the ledger calls go, as long as the rows match the above.
