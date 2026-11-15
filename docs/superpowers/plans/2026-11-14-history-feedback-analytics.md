# Run history across users and Feedback analytics: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Reports page's session-only list and the Feedback analytics PILOT placeholder with demo
pages fed by an in-memory ledger of every review and every accept/reject since the server started.

**Architecture:** A pure, thread-safe `Ledger` (`api/ledger.py`) owned by `SessionStore` records run rows and
feedback rows and builds two summaries; `GET /api/history` and `GET /api/feedback/summary` serve them. The
browser sends an anonymous `X-Demo-Visitor` id so the server can label "Visitor N". The front end rewrites
`ReportsView` and adds `FeedbackView`.

**Tech Stack:** Python 3 / FastAPI / pytest; React 18 + TypeScript + Vite (no front-end test runner).

**Spec:** `docs/superpowers/specs/2026-11-14-history-feedback-analytics-design.md`

## Global Constraints
- No live model calls; API tests replay `data/cache` (existing `client` fixture, `no_model`).
- Nothing new from an upload outlives its session: uploads appear as exactly `"Uploaded PDF"`; feedback rows
  never hold comments, quotes, or the requirement of a finding whose `rule_id` is None.
- No writes to `data/telemetry.db` or any other file by the ledger; no change to `feedback.jsonl` behaviour.
- Page notes, verbatim: Reports "Demo: kept in the server's memory since it started ({since}); a restart clears
  it. Uploaded drawings are listed as "Uploaded PDF": nothing about an upload outlives its session. In the pilot
  this history is stored and covers every user by name."; Feedback "Demo: decisions from the Accept/Reject
  buttons of every visitor since the server started; a restart clears them. In the pilot the rulebook owner
  reviews the most-rejected rules here."
- Empty states, verbatim: "No reviews yet. Open a demo drawing to start." / "No decisions yet. Accept or reject
  findings on a drawing."
- Done means: `python -m pytest -q` (includes regression), `ruff check .`, `ruff format --check .`, `pyright`,
  front-end build all pass; `di eval review --no-understand` unchanged (19/22, 79/79).
- Environment: `source ~/.venvs/drawing-intelligence/bin/activate` in `/mnt/d/Capstone/drawing-intelligence`;
  edit files with Python or the Edit tool (`sed -i` fails on /mnt/d). Front-end build:
  `rsync -a --delete --exclude node_modules --exclude dist web/ ~/di-webbuild/src_copy/ && (cd ~/di-webbuild/src_copy && npm run build)`.
  UI checks: server with `QWEN_API_KEY= OPENAI_API_KEY= DI_DEMO_PASSWORD=test DI_WEB_DIST=~/di-webbuild/src_copy/dist uvicorn drawing_intelligence.api.app:create_app --factory --port 8000`
  and Playwright from `C:\Temp\pwvenv` with `channel="chrome"` (scripts in `C:\Temp\diui`).
- Branch `feat/demo-history-feedback` from `main`; commit per task with the Co-Authored-By line; no push, no
  redeploy.

## Review Focus
1. Two visitors at once: rows labelled by first-seen order, `you` only on the caller's rows; a request without
   the header is "Visitor ?" and never `you`. Tests in Tasks 1 and 2.
2. A decision changed from accept to reject (or back) counts once, with the latest value. Tests in Tasks 1, 2.
3. A run that ends in `error` (no `result`): listed, `billed()` 0, excluded from averages, model from
   `sess.models` or None; never raises. Test in Task 1 (row values) and Task 2 (`_run` path via a failing upload
   is not needed; unit-level row building covers it).
4. Q&A asked after the drawing is closed is impossible, but Q&A asked before closing must still show on the
   row after closing. Test in Task 2.
5. Concurrent writes from the two worker pools: the ledger takes a lock; summaries are built from a copy.
   Covered by the lock in Task 1 (no stress test).

---

### Task 1: `Ledger`

**Files:**
- Create: `src/drawing_intelligence/api/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces:
  - `UPLOAD_LABEL = "Uploaded PDF"`
  - `class Ledger` with `since: str` (UTC ISO at construction) and:
    - `record_run(*, session_id: str, visitor: str | None, drawing: str, mode: str, status: str, findings: int, fails: int, seconds: float | None, cost_usd: float, model: str | None, cached: bool) -> None`
    - `add_qa_cost(session_id: str, usd: float) -> None` (no-op for an unknown id)
    - `record_feedback(*, session_id: str, visitor: str | None, finding_id: str, rule_id: str | None, requirement: str | None, category: str, source: str, reviewer: str, result: str, decision: str) -> None` (stores `requirement` only when `rule_id` is set)
    - `history(visitor: str | None) -> dict[str, Any]` and `feedback_summary() -> dict[str, Any]`, shaped as the spec's endpoint section.
  - `mode` values used by callers: `"Demo (cached)"`, `"Live upload"`, `"Batch"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ledger.py`, with a helper `_run(ledger, **overrides)`
  that calls `record_run` with defaults (`session_id="s1"`, `visitor="v-a"`, `drawing="P13"`,
  `mode="Demo (cached)"`, `status="done"`, `findings=4`, `fails=3`, `seconds=2.9`, `cost_usd=0.0`,
  `model="qwen3-vl-plus"`, `cached=True`) and `_fb(ledger, **overrides)` likewise.
  - `test_runs_newest_first_with_visitor_labels`: runs by `v-a`, `v-b`, `v-a`; `history("v-b")["runs"]` newest
    first; labels `Visitor 1` for v-a, `Visitor 2` for v-b; `you` True only on v-b's row; `visitors == 2`.
  - `test_a_request_without_a_visitor`: a run with `visitor=None` is labelled `"Visitor ?"`; `history(None)`
    marks no row `you`.
  - `test_qa_cost_lands_on_its_run`: `add_qa_cost("s1", 0.004)` twice → row `qa_cost_usd == 0.008`; unknown id
    is a no-op.
  - `test_model_summary_averages_live_done_runs_only`: one cached done run, one live done run (60 s, $0.03),
    one live error run (5 s, $0) on the same model → `runs == 3`, `live_runs == 2`,
    `avg_live_seconds == 60`, `avg_live_cost_usd == 0.03`, `total_cost_usd == 0.03`; a model with only cached
    runs has `avg_live_seconds is None`.
  - `test_a_changed_decision_counts_once`: accept then reject on the same `(session_id, finding_id)` →
    `decisions == 1`, `rejected == 1`.
  - `test_feedback_summary_groups_and_sorts`: rules A (2 rejected), B (1 rejected, 3 decisions), C (accepted)
    → `by_rule` ids in order `["A", "B", "C"]`; `rate` = accepted / decisions rounded to 3 places;
    `by_source` and `by_reviewer` totals add up to `decisions`.
  - `test_a_finding_without_a_rule`: `rule_id=None, requirement="Ø16 looks odd"` counts in `decisions` and
    `by_source`, is absent from `by_rule`, and the string `"Ø16 looks odd"` appears nowhere in
    `repr(ledger.__dict__)`.
  - `test_upload_rows_carry_no_file_name`: a run recorded with `drawing=UPLOAD_LABEL` → row drawing is
    `"Uploaded PDF"` (callers pass the label; Task 2 tests the caller).
- [ ] **Step 2: Run** `python -m pytest tests/test_ledger.py -q`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement `ledger.py`:** a `threading.Lock`, a dict of run rows by session id (insertion order),
  a dict of feedback rows keyed `(session_id, finding_id)`, a dict visitor id → number; summaries built under the
  lock from copies. Module docstring: demo only, in memory, nothing about uploads.
- [ ] **Step 4: Run** the tests, ruff, format, pyright on the two files. Expected: pass.
- [ ] **Step 5: Commit** `Run history and feedback analytics: the in-memory ledger`.

### Task 2: Wiring and endpoints

**Files:**
- Modify: `src/drawing_intelligence/api/runs.py` (`DemoSession` gets `visitor: str | None = None`,
  `batch: bool = False`; `SessionStore.__init__` makes `self.ledger = Ledger()`; `create(..., visitor: str | None = None)`;
  `add_batch` sets `batch = True` on its sessions; `_run`'s `finally` records the run unless cancelled; `ask`
  calls `ledger.add_qa_cost`; new `record_decision(sess, finding, decision)` wraps `ledger.record_feedback`)
- Modify: `src/drawing_intelligence/api/app.py` (a `Visitor = Annotated[str | None, Header(alias="X-Demo-Visitor")]`
  parameter on `open_demo`, `upload`, `start_batch` passed through `start_upload` to `create`; the feedback
  endpoint calls `the_store.record_decision`; new routes `GET /api/history` and `GET /api/feedback/summary`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1's `Ledger`, `UPLOAD_LABEL`.
- Produces: `GET /api/history` (caller's `X-Demo-Visitor` sets `you`), `GET /api/feedback/summary`, both behind
  the password. Run row building: `drawing = sess.name if sess.demo_id else UPLOAD_LABEL`;
  `mode = "Batch" if sess.batch else "Live upload" if sess.live else "Demo (cached)"`;
  `model = result.understanding[0].model if available else sess.models.get("model")`;
  `fails` = findings with `result == "fail"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_api.py`:
  - `test_history_across_two_visitors`: `_done` opens `cam-plate-seeded` with header `X-Demo-Visitor: a` and
    `cam-plate-clean` with `b` (extend `_done` with an optional `visitor` argument that adds the header); then
    `GET /api/history` as `b`: two runs, newest first, labels `{"Visitor 1", "Visitor 2"}`, `you` only on the
    clean cam plate's row, drawings are the demo titles, `mode == "Demo (cached)"`, `cost_usd == 0`.
  - `test_history_and_summary_need_the_password`: both routes 401 without the token.
  - `test_feedback_summary_counts_the_latest_decision`: on the seeded cam plate, accept then reject finding 1
    → summary `decisions == 1`, `rejected == 1`, its `rule_id` is in `by_rule`; after `DELETE` of the session
    the summary is unchanged.
  - `test_qa_cost_survives_closing`: the `client` fixture also exposes its store (`c.store = store` before
    `yield c`); open the seeded cam plate, set `sess.conversation` to a stub whose `ask(q)` returns an object with
    `cost_usd = 0.01`, call `store.ask(sess, "q")`, `DELETE` the session, then `/api/history` shows that run with
    `qa_cost_usd == 0.01`.
  - `test_an_upload_is_listed_without_its_name`: upload the P13 PDF's bytes as `secret_part_9.pdf` (its replies
    are cached, so it finishes with no model call); once done, `/api/history`'s row has
    `drawing == "Uploaded PDF"`, `mode == "Live upload"`, and `"secret_part_9"` is not in the response text.
- [ ] **Step 2: Run** `python -m pytest tests/test_api.py -q -k "history or summary or qa_cost or without_its_name"`.
  Expected: FAIL (404 routes / missing attributes).
- [ ] **Step 3: Implement** the wiring and routes as in the Files block.
- [ ] **Step 4: Run** `python -m pytest -q`, ruff, format, pyright. Expected: all pass.
- [ ] **Step 5: Commit** `Run history and feedback analytics: GET /api/history and /api/feedback/summary`.

### Task 3: Reports page and Feedback analytics (front end)

**Files:**
- Modify: `web/src/api.ts` (visitor id in `localStorage` key `di-visitor`, made with `crypto.randomUUID()` on
  first use, sent as `X-Demo-Visitor` in `call()`; types `HistoryRun`, `History`, `FeedbackSummary`;
  `api.history()`, `api.feedbackSummary()`)
- Modify: `web/src/components/DocViews.tsx` (`ReportsView` takes no props and fetches `/api/history` on mount
  and every 5 s; new `FeedbackView` likewise for the summary)
- Modify: `web/src/App.tsx` (`DocKind` gets `"feedback"`, added to `STATIC_DOCS` with the `Gauge` icon and label
  "Feedback analytics"; `<ReportsView />` without the `sessions` prop), `web/src/components/Ribbon.tsx`
  (Feedback analytics: `onClick={() => p.onDoc("feedback")}`, no `pilot`; `onDoc`'s type includes
  `"feedback"`), `web/src/styles.css` (only for the rate bar)

**Interfaces:**
- Consumes: Task 2's endpoints.
- Produces: nothing later tasks use.

- [ ] **Step 1: Reports page:** KPIs (reviews since `since` as local time HH:MM, visitors, live cost = sum of
  `cost_usd` + `qa_cost_usd`, average live review), the run table (columns as the spec's sketch; `Visitor N (you)`;
  time as local HH:MM), the per-model table, the note verbatim, the empty state verbatim.
- [ ] **Step 2: Feedback analytics page:** KPIs (decisions, accept rate, code accept rate = sources code and
  lookup together, AI accept rate = source llm), by-reviewer table, by-rule table with a rate bar, the note and
  empty state verbatim.
- [ ] **Step 3: Build.** Expected: success.
- [ ] **Step 4: Manual check** (two browser contexts = two visitors): context A opens P13 and accepts two
  findings, rejects one; context B opens C01 and rejects one. In B, Reports shows 2 runs, B's row "(you)",
  drawings by title; Feedback shows 4 decisions, rules listed with the rejected ones first; open in A: its row is
  "(you)". Restarting the server empties both pages (empty states shown).
- [ ] **Step 5: Commit** `Web demo: run history across visitors and feedback analytics`.

### Task 4: Docs and full verification

**Files:**
- Modify: `docs/adr/0012-web-demo.md` ("Update 2026-11-14 (later)"), `CLAUDE.md` layout line for `api/` if it
  should mention the ledger
- Create: `docs/updates/2026-11-14_history_feedback.md` (table as in `2026-11-14_compare_signoff_send.md`;
  still PILOT: Confirm rules, Edit rule; the `feedback.jsonl` question flagged as open)

- [ ] **Step 1: Write** the docs.
- [ ] **Step 2: Run everything** (Global Constraints "Done means"). Expected: all pass, eval unchanged.
- [ ] **Step 3: Commit** `Docs: run history and feedback analytics (demo)`.
