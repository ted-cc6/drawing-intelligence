# Design: Compare revisions, Mark as checked, Send to designer (demo)

Date: 2026-11-14. Status: draft, for Binjie's approval.

## Intent
Three of the six commands still marked PILOT in the web demo's ribbon (`web/src/components/Ribbon.tsx`) should
show, in a demo, how the checker's workflow would go: compare a new revision with the old one, sign a drawing
off, and send the accepted findings back to the designer. They need to look and click like the real thing for
the consultants and PARI; they do not need to store anything or send any email.

## Goals
- **Compare revisions**: pick two reviewed drawings, see which findings are new, which are gone and which stay,
  and what changed in the title block and the revision table. Real logic (it works on any two reviews), tested.
- **Mark as checked**: a sign-off dialog over the open review, then a visible "checked" status on it.
- **Send to designer**: a pre-filled message to the designer listing the accepted findings, with the Excel
  checklist and the annotated sheet attached, and a Send button that sends nothing.
- All three free to demo: the four demo drawings replay from cache, so C01 → P13 costs $0.

## Non-goals
- No persistent storage, user accounts, email, or notifications (that is the pilot's phase 0).
- No visual overlay of the two sheets (considered and dropped: a lot of work, and on C01/P13 the visible change
  is a few characters).
- The other three PILOT commands (Confirm rules, Edit rule, Feedback analytics) and run history stay as they are.

## Anti-goals
- Nobody in the audience should take the mock-ups for working features: Mark as checked and Send to designer
  each carry a plain "Demo: nothing is stored or sent" note.
- No fake backend endpoints that pretend to sign off or send (they would mislead whoever builds the pilot).
- No change to the review pipeline, the rules or the eval numbers.

## Constraints
- CLAUDE.md hard rules apply: no live model calls during development except by Binjie's OK (none are needed);
  pathlib only; all checks and tests pass (`pytest`, ruff, format, pyright, `npm run build`).
- The front end has no test runner; the API has `tests/test_api.py`, which already replays the P13 demo from
  cache. Logic worth testing goes in Python.
- Title-block names are employee numbers (e.g. drawn by `80152072`), not names or email addresses.
- The two cam-plate test drawings share the same title block, revision `00` included: the seeded P13 is C01
  with one planted error, not a new revision.

## Approaches (picked: C)
- **A. Front end only.** Compare fetches both sessions and diffs in the browser; the two others are dialogs.
  No Python change, but the matching logic would have no tests.
- **B. Backend endpoints for all three.** Compare plus sign-off and send endpoints returning a made-up "OK".
  Tested, but two endpoints would pretend to do something they don't.
- **C. Mixed (picked by Binjie).** Compare's diff in Python, with an endpoint and pytest tests; Mark as checked
  and Send to designer are browser-only mock-ups. Testing goes where the logic is worth keeping; the mock-ups
  are cheap to replace in the pilot.

## Design

### 1. Compare revisions
**Backend.** A new pure module `src/drawing_intelligence/api/compare.py`:
`compare(old: dict, new: dict) -> dict`, taking two session views as `session_view` builds them (the dicts the
UI already gets) and returning:
```
{ "old": {id, name, number, revision}, "new": {...},
  "findings": {"new": [...], "fixed": [...], "still_open": [...]},   # still_open items carry was/now quotes
  "title_block": [{"field", "old", "new"}],                          # changed fields only
  "revision_rows": {"added": [...], "removed": [...]},
  "notes": [...] }                                                    # plain-English remarks, e.g. same revision
```
- A finding's match key is `(rule_id or category, anchor)`. Same key in both → `still_open`; with a different
  first evidence quote it carries `was` and `now`. Only in new → `new`; only in old → `fixed`.
- The anchor (builder check, settled by Claude): dimension and symbol refs (`D{i}`, `S{i}`) are numbered by
  position on the sheet (`extraction/pipeline.py`, `symbols.py`), so adding one dimension renumbers the rest and
  they cannot be the anchor. For those, the anchor is the first evidence quote with its tolerance removed
  (e.g. `⌀ 16 H7 (-0.018/0)` → `⌀ 16 H7`) plus its zone. Named refs (title-block fields such as
  `checked_date`) are stable and are the anchor as they are. No evidence at all: the location string. Known
  limit, said in a code comment: a dimension whose nominal value changed shows as one fixed plus one new.
- If the drawing numbers differ, `notes` says so (the comparison still runs). If the findings changed but the
  revision number did not, `notes` says "Both sheets say revision 00": on a real drawing that is worth asking
  about, and on C01/P13 it is honest about the pair being a test edit.
- `revision_rows` needs the revision table lines in the session view: add `revision_rows: list[str]` (page 1's
  filled lines) to `session_view` in `api/views.py`.

Endpoint: `GET /api/compare?old=<sid>&new=<sid>` (auth like the others). 404 if a session is missing, 409 if
either review is not done.

Tests (`tests/test_api.py`, replaying the cache, $0): C01 → P13 gives new = {RQ-002, WST-207} on `⌀ 16 H7`,
still_open = {TB-016, WPS-004} (WPS-004 matched on `⌀ 16 H7` in its zone) with its quote changed `(+0.018/0)` → `(-0.018/0)`, fixed = {}, no title
block changes, and the same-revision note; P13 → C01 is the mirror (two fixed). Unit tests for `compare` on
small hand-built dicts: a dimension still matched after the D-numbers shift, a changed nominal (fixed + new),
matching by a named ref, by location when there is no evidence, the different-number note, 404/409.

**Front end.** "Compare revisions" (Home > Review) loses `pilot` and opens a picker when a review is done:
"Compare this drawing with…" listing the other demo drawings and any drawing reviewed in this browser session;
the open drawing is "new", the pick is "old". For the cam plate the picker puts C01 first.
Picking a drawing that is not open opens it as a normal tab (a demo drawing replays from cache in about a
second), waits for its review to finish, then runs the comparison; the user returns to the "new" drawing's tab
by clicking a finding or the tab strip. The Compare view fetches its result once and keeps it, so closing either
drawing afterwards does not break it (clicking a finding of a closed drawing just says it is closed). Settled by
Claude after the builder check: no hidden sessions, nothing to clean up behind the user's back. The result opens as
a document view (like the Rulebook and Run history pages):

```
 Compare revisions        C01 · Cam plate, clean  →  P13 · Cam plate, fit limits inverted
 ┌ i  Both sheets say revision 00. The findings changed, so the drawing changed without a new revision.
 New (2)            RQ-002  fail   ⌀16 H7 (-0.018/0)  D12   Limits of size in the right order
                    WST-207 fail   ⌀16 H7 (-0.018/0)  D12   H7 limits from IS 919
 Fixed (0)          —
 Still open (2)     TB-016  fail   checked_date 01/10/2025
                    WPS-004 warn   was ⌀16 H7 (+0.018/0) → now ⌀16 H7 (-0.018/0)
 Title block        no changes
 Revision table     no changes
```
Clicking a new or still-open finding returns to the open drawing with that finding selected.

### 2. Mark as checked (browser only)
"Mark as checked" (Review > Sign-off) loses `pilot`; enabled once a review is done. It opens a dialog:
- Checker: a text box, filled with "Demo checker".
- Counts from the open review: accepted, rejected, no decision yet.
- If some findings have no decision: "3 findings have no decision", with **Next open finding** (the existing
  command) and **Sign off anyway**. If there are accepted fails: "2 accepted fails: send to the designer
  instead?" with a button that opens Send to designer.
- Note: "Demo: nothing is stored. In the pilot the sign-off is saved with the review and the drawing's status
  changes for everyone."

On sign-off the status bar shows a chip `Checked by Demo checker · 14 Nov 2026 · 3 accepted, 1 rejected, 0 open`
and the button becomes **Reopen** (clears it). The state lives in React for the open session only.

### 3. Send to designer (browser only)
"Send to designer" (Review > Sign-off) loses `pilot`; enabled once a review is done. With no accepted findings
it says so in the prompt line and opens nothing. Otherwise a message preview:
```
 To:       Designer 80152072 (drawn by, from the title block)
 Subject:  P24BSA064533 rev 00 (10K_CAM PLATE): 2 corrections from the drawing check
 Body:     one numbered line per accepted finding: requirement, location (zone), recommended correction
 Attached: review_report.xlsx · annotated sheet (.png)       (links to the existing downloads)
 [Copy text]  [Send (demo)]
 i  Demo: nothing is sent. In the pilot the address comes from the employee directory and the drawing's
    status becomes "Returned to designer".
```
**Send (demo)** closes the dialog, puts "Demo: not sent" in the prompt line, and sets the status chip to
`Returned to designer · 14 Nov 2026`. **Copy text** copies the message (harmless and handy in a demo).
Sign-off and return share the one chip: the last action wins; Reopen clears either.

### Docs and deploy
- ADR 0012 update and a progress note in `docs/updates/`; the Nov 8 list of what is still PILOT shrinks to
  confirm rules, edit rule, feedback analytics and run history.
- The App's help text keeps "Commands marked PILOT are part of the pilot" (three remain).
- Redeploying the Space is a separate step, on Binjie's word.

## Left to the builder
- Component structure (one new view for Compare, two dialogs), styling within the existing ribbon look and
  `.pilotnote` boxes, and the picker's exact layout.
- How the API client fetches the comparison and where the session-only sign-off state sits in `App.tsx`.
- Wording of the plain-English notes, kept short and in the demo's existing tone.
