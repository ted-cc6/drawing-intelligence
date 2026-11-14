# Compare revisions, Mark as checked, Send to designer: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three PILOT placeholders in the web demo with a tested Compare revisions feature and two
browser-only mock-ups (Mark as checked, Send to designer).

**Architecture:** A pure Python function `compare(old, new)` diffs two session views (the dicts
`session_detail` already returns) and is served at `GET /api/compare`. The front end adds a Compare document
view with a picker, and two dialogs whose state lives only in React (`stamps` keyed by session id), shown as a
status-bar chip.

**Tech Stack:** Python 3 / FastAPI / pytest (backend); React 18 + TypeScript + Vite, lucide-react icons
(front end, no test runner).

**Spec:** `docs/superpowers/specs/2026-11-14-compare-signoff-send-design.md`

## Global Constraints
- No live model calls. API tests replay `data/cache` through the existing `client` fixture (`no_model` raises
  on a cache miss).
- No persistent storage, no email, no new backend endpoint other than `GET /api/compare`.
- Mock-up copy, verbatim: Mark as checked note "Demo: nothing is stored. In the pilot the sign-off is saved with
  the review and the drawing's status changes for everyone."; Send note "Demo: nothing is sent. In the pilot the
  address comes from the employee directory and the drawing's status becomes "Returned to designer"."
- pathlib only; match surrounding code style (comment density, plain-English UI copy, no dashes in copy).
- Done means: `python -m pytest` (unit + `-m regression`), `ruff check .`, `ruff format --check .`, `pyright`,
  and the front-end build all pass.
- Environment (WSL): `source ~/.venvs/drawing-intelligence/bin/activate` from the repo root
  `/mnt/d/Capstone/drawing-intelligence`; git is `"/mnt/c/Program Files/Git/cmd/git.exe"`. Front-end build:
  `rsync -a --delete --exclude node_modules --exclude dist web/ ~/di-webbuild/src_copy/ && (cd ~/di-webbuild/src_copy && npm ci && npm run build)`
  (npm does not run on /mnt/d).
- Work on branch `feat/demo-compare-signoff` from `main`; commit per task with the Co-Authored-By line; do not
  push or redeploy (Binjie's call).

## Review Focus
1. Comparing a drawing with itself (same session or same demo): everything `still_open`, nothing new or fixed,
   no notes. Test in Task 1.
2. A finding with no evidence (some AI warnings): matched by `location`, never crashes on `evidence == []`.
   Test in Task 1.
3. Two findings of the same rule on the same anchor (duplicates): each matched once, not collapsed. Test in
   Task 1.
4. Old drawing closed after the comparison ran: the Compare view still shows its result; clicking an old-only
   ("fixed") finding says the drawing is closed. Manual check in Task 3.
5. Send to designer with zero accepted findings, and Mark as checked with zero findings at all: prompt line
   message, no broken dialog. Manual checks in Tasks 4 and 5.

---

### Task 1: `compare()` in Python

**Files:**
- Create: `src/drawing_intelligence/api/compare.py`
- Test: `tests/test_compare.py`

**Interfaces:**
- Produces: `compare(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]`, inputs shaped like
  `session_detail` output (`id`, `name`, `title_block`, `findings`, `revision_rows`), output:
  ```
  {"old": {"id","name","number","revision"}, "new": {...},
   "findings": {"new": [F], "fixed": [F], "still_open": [F + {"was": str|None, "now": str|None}]},
   "title_block": [{"field","old","new"}], "revision_rows": {"added": [str], "removed": [str]},
   "notes": [str]}
  ```
  where `F` is the finding dict as given (unchanged keys, `no` refers to its own session).
- Also produces `anchor(f: dict[str, Any]) -> str` (exported for tests).

- [ ] **Step 1: Write the failing tests** in `tests/test_compare.py`, using a helper
  `_f(rule, ref=None, quote=None, zone=None, location="loc", no=1)` that builds a finding dict with
  `evidence=[{"ref": ref, "quote": quote, "zone": zone, ...}]` (or `[]` when ref and quote are both None) and
  `_view(findings, tb=None, rows=None, id="s", name="n")`.
  - `test_anchor_drops_the_tolerance_of_a_numbered_ref`: `anchor(_f("WPS-004", "D12", "⌀ 16 H7 (-0.018/0)", "D3"))`
    equals `anchor(_f("WPS-004", "D7", "⌀ 16 H7 (+0.018/0)", "D3"))`; `"±0.1"` style tails are dropped too
    (`"25 ±0.1"` and `"25 ±0.2"` anchor alike).
  - `test_a_named_ref_is_its_own_anchor`: `_f("TB-016", "checked_date", "01/10/2025")` and the same with quote
    `"02/11/2026"` share an anchor.
  - `test_no_evidence_falls_back_to_location`.
  - `test_findings_split_into_new_fixed_still_open`: old {A on D1, B on D2}, new {B on D5 (D-numbers shifted),
    C}: `new == [C]`, `fixed == [A]`, `still_open == [B]` with `was`/`now` set only when the quotes differ.
  - `test_a_changed_nominal_is_fixed_plus_new`: `"⌀ 16 H7"` → `"⌀ 18 H7"` gives one fixed and one new.
  - `test_duplicates_match_one_to_one`: two A on the same anchor in old, one in new → one still_open, one fixed.
  - `test_same_view_twice_is_all_still_open`: `compare(v, v)` → no new, no fixed, `notes == []`.
  - `test_title_block_and_revision_rows`: changed fields only, sorted by field name; rows added/removed as sets
    in their original order.
  - `test_notes`: different `number` → note containing both numbers; findings changed and same `revision` →
    exactly `"Both sheets say revision 00. The findings changed, so the drawing changed without a new revision."`;
    no note when the revision differs.

- [ ] **Step 2: Run** `python -m pytest tests/test_compare.py -q`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement `compare.py`.** `anchor`: key is `rule_id or category`; first evidence with a `ref`
  matching `^[DS]\d+$` → normalized quote (strip a trailing parenthesized group and anything from `±`, collapse
  spaces) + `zone`; other ref → the ref; no evidence → `location`. Matching is one-to-one: bucket old findings by
  anchor in lists, pop from the front as new findings match. Module docstring states the known limit (a changed
  nominal shows as fixed + new).

- [ ] **Step 4: Run** `python -m pytest tests/test_compare.py -q`. Expected: all pass.

- [ ] **Step 5: Commit** `Compare revisions: the diff of two reviews (new, fixed, still open)`.

### Task 2: `GET /api/compare` and `revision_rows` in the session view

**Files:**
- Modify: `src/drawing_intelligence/api/views.py` (`session_detail`, the `out.update` block)
- Modify: `src/drawing_intelligence/api/app.py` (new route after `get_session`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `compare(old, new)` from Task 1; existing `session_or_404`, `done_or_409`, `session_detail`.
- Produces: `GET /api/compare?old=<sid>&new=<sid>` → Task 1's output dict; 404 unknown session, 409 not done.
  `session_detail(...)["revision_rows"]: list[str]` (page 1's `revision_rows` texts).

- [ ] **Step 1: Write the failing tests** in `tests/test_api.py`, with a helper `_done(client, h, demo_id) -> str`
  that opens a demo and polls until `done` (factor it out of `test_a_review_session_end_to_end`'s loop and use
  it there too).
  - `test_compare_the_clean_and_the_seeded_cam_plate`: old = `cam-plate-clean`, new = `cam-plate-seeded`;
    `{f["rule_id"] for f in new} == {"RQ-002", "WST-207"}`, all their first quotes start with `"⌀ 16 H7"`;
    `fixed == []`; `still_open` rules `== {"TB-016", "WPS-004"}`; WPS-004 has `was` containing `"(+0.018/0)"`
    and `now` containing `"(-0.018/0)"`; `title_block == []`; the same-revision note is in `notes`. Reversed:
    two fixed, no new.
  - `test_compare_needs_two_finished_reviews`: unknown sid → 404.
  - In the end-to-end test, assert `isinstance(s["revision_rows"], list)`.

- [ ] **Step 2: Run** `python -m pytest tests/test_api.py -q -k compare`. Expected: FAIL (404 on the route).

- [ ] **Step 3: Implement** the route `compare_reviews(old: str, new: str) -> dict[str, Any]` (both sessions via
  `session_or_404` then `done_or_409`, views via `session_detail(sess, settings.config_path)`), and add
  `"revision_rows"` to `session_detail`.

- [ ] **Step 4: Run** `python -m pytest -q` and `python -m pytest -m regression -q`, ruff, format, pyright.
  Expected: all pass.

- [ ] **Step 5: Commit** `Compare revisions: GET /api/compare; revision rows in the session view`.

### Task 3: Compare view and picker (front end)

**Files:**
- Modify: `web/src/api.ts` (types + `api.compare`)
- Create: `web/src/components/CompareView.tsx` (the view and the picker dialog)
- Modify: `web/src/App.tsx` (`DocKind` gets `"compare"`; `Doc` gets `compare?: Comparison`), `web/src/components/Ribbon.tsx`
- Modify: `web/src/styles.css` (only if the existing `.docview`, `.dialog`, `.pilotnote` classes are not enough)

**Interfaces:**
- Consumes: Task 2's endpoint.
- Produces: `export interface Comparison` mirroring Task 1's output (`still_open` items are
  `Finding & { was: string | null; now: string | null }`); `api.compare(oldSid: string, newSid: string): Promise<Comparison>`;
  Ribbon prop `onCompare: () => void` (the button is enabled when `reviewDone`, no `pilot`).
  `<ComparePicker demos sessions current onPick(choice: {demoId?: string; sid?: string}) onClose />` and
  `<CompareView data={Comparison} onSelect(sid: string, no: number) />`.

- [ ] **Step 1: Picker.** Lists open, finished drawings other than the current one, then demo drawings not open;
  for a current session whose `demo_id` is `cam-plate-seeded`, `cam-plate-clean` is first. Title
  "Compare this drawing with…".
- [ ] **Step 2: Flow in App.** Picking an open session calls `api.compare(pick, current)`; picking a demo calls
  `openDemo`, keeps the current sid as the pending "new", waits for that session's `status === "done"` in the
  existing polling effect, then calls `api.compare` and opens a `compare` doc (tab label
  `Compare: <old name> → <new name>`, `GitCompare` icon). The result is stored in the doc and never re-fetched.
- [ ] **Step 3: View.** Header line with both names; notes in `.pilotnote` boxes; sections New, Fixed, Still open
  (rule, result, quote or `was → now`, zone, requirement), Title block (`field: old → new` or "no changes"),
  Revision table (added / removed or "no changes"), as in the spec's sketch. Clicking a New or Still open
  finding activates the new drawing's tab and selects it; a Fixed one activates the old drawing; if that session
  is no longer open, the prompt line says "<name> is closed."
- [ ] **Step 4: Build** (Global Constraints command). Expected: `tsc` and `vite build` succeed.
- [ ] **Step 5: Manual check** with the API on :8000 (`uv run uvicorn ... --factory`) serving the build in
  headless Chrome: open P13, Compare → C01: 2 new, 2 still open, the revision note; close C01, the view still
  shows; click a Fixed item of the reversed comparison after closing → "is closed" prompt (Review Focus 4).
- [ ] **Step 6: Commit** `Web demo: Compare revisions`.

### Task 4: Mark as checked (browser only)

**Files:**
- Create: `web/src/components/SignOff.tsx` (`SignOffDialog`, and the `Stamp` type)
- Modify: `web/src/App.tsx` (`stamps: Record<string, Stamp>` state), `web/src/components/Ribbon.tsx`,
  `web/src/components/Chrome.tsx` (`StatusInfo.stamp?: string`, one extra cell)

**Interfaces:**
- Produces: `export interface Stamp { kind: "checked" | "returned"; by: string; date: string; accepted: number; rejected: number; open: number }`
  (used by Task 5); `stampText(s: Stamp): string` giving
  `Checked by Demo checker · 14 Nov 2026 · 3 accepted, 1 rejected, 0 open` or
  `Returned to designer · 14 Nov 2026`; Ribbon props `stamped: boolean`, `onMarkChecked: () => void`
  (label becomes "Reopen" when `stamped`, and clicking it clears the stamp).

- [ ] **Step 1: Dialog** per the spec: checker text box ("Demo checker"), the three counts over all findings
  (`allFindings`, not the filtered list), the open-findings warning with **Next open finding** (closes the
  dialog, calls `nextOpen`) and **Sign off anyway**, the accepted-fails prompt with a button that opens Send to
  designer (Task 5 wires it; until then it is hidden), the demo note verbatim. With zero findings: no warnings,
  sign-off allowed (Review Focus 5).
- [ ] **Step 2: Stamp** set on sign-off, shown in the status bar for the active drawing, cleared by Reopen and
  when the session closes. Date format `14 Nov 2026` (`toLocaleDateString("en-GB", {day: "numeric", month: "short", year: "numeric"})`).
- [ ] **Step 3: Build.** Expected: success.
- [ ] **Step 4: Manual check:** P13 with no decisions → warning with 4 open; Accept all code fails, sign off
  anyway → chip; Reopen clears; C01 with zero accepted fails → no send suggestion.
- [ ] **Step 5: Commit** `Web demo: Mark as checked (demo, nothing stored)`.

### Task 5: Send to designer (browser only)

**Files:**
- Create: `web/src/components/SendToDesigner.tsx`
- Modify: `web/src/App.tsx`, `web/src/components/Ribbon.tsx`, `web/src/components/SignOff.tsx` (show the
  "send to the designer instead?" button)

**Interfaces:**
- Consumes: `Stamp`, `stampText` from Task 4; `download` and the existing report/annotated URLs.
- Produces: `buildMessage(s: SessionInfo, accepted: Finding[]): { to: string; subject: string; body: string }`
  (exported so the copy text and the preview share it); Ribbon prop `onSendDesigner: () => void`.

- [ ] **Step 1: Message** per the spec: To `Designer <drawn_by> (drawn by, from the title block)` (or
  `Designer (drawn by not read)` when missing); Subject
  `<number> rev <revision> (<title>): <n> correction(s) from the drawing check`; body one numbered line per
  accepted finding: requirement, `location`, recommended correction when present.
- [ ] **Step 2: Dialog:** the preview, attachments as links that call `download` for `report.xlsx` and
  `annotated/<page>.png`, **Copy text** (`navigator.clipboard.writeText`, prompt "Message copied."),
  **Send (demo)** (closes, prompt "Demo: not sent.", stamp `{kind: "returned"}`), the demo note verbatim. With
  zero accepted findings the dialog does not open and the prompt says
  "No accepted findings to send. Accept the findings the designer should fix first." (Review Focus 5).
- [ ] **Step 3: Build.** Expected: success.
- [ ] **Step 4: Manual check:** P13, accept RQ-002 and WST-207, Send → preview with 2 lines and
  `P24BSA064533 rev 00 (10K_CAM PLATE): 2 corrections…`; attachments download; Send (demo) → chip
  "Returned to designer"; then Mark as checked replaces it (last action wins).
- [ ] **Step 5: Commit** `Web demo: Send to designer (demo, nothing sent)`.

### Task 6: Docs and full verification

**Files:**
- Modify: `docs/adr/0012-web-demo.md` (an "Update 2026-11-14" section), `CLAUDE.md` only if its layout list
  needs `api/compare.py`
- Create: `docs/updates/2026-11-14_compare_signoff_send.md` (table like `2026-11-08_pilot_phase1.md`:
  feature, where, what it does, commit; then tests and "Still PILOT: confirm rules, edit rule, feedback
  analytics, run history across users")

- [ ] **Step 1: Write** the two docs.
- [ ] **Step 2: Run everything:** `python -m pytest -q`, `python -m pytest -m regression -q`, `ruff check .`,
  `ruff format --check .`, `pyright`, the front-end build, and `di eval review --no-understand` (unchanged).
  Expected: all pass, eval numbers as on main (19/22, 79/79).
- [ ] **Step 3: Commit** `Docs: compare revisions, sign-off and send to designer (demo)`.
