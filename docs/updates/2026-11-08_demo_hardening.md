# Nov 08: web demo hardening before the in-office client demo

Branch `fix/demo-hardening` (local, not pushed; the Space is not redeployed yet). Found by testing every
feature of the live Space in a current Chrome (156) and by stress tests on 2026-11-08.

## Fixed

| Problem on the Space | Fix | Commit |
|---|---|---|
| **Q&A blanked the whole app** on the first question in current Chrome: the Ask pane's effect returned `scrollIntoView`'s new Promise, which React called as a cleanup | effects have block bodies; a test fails on any expression-bodied effect | `d3638be` |
| A demo drawing took 56 s to open while two uploads ran (one 2-thread pool) | separate pools for live uploads and demo replays | `77fa025` |
| Closing a drawing did not stop its review (kept spending, held a worker) | cancel flag: queued runs skipped, running ones stop at the next node | `77fa025` |
| A guideline PDF and a blank page were "reviewed"; a corrupt PDF showed a server path; no page limit | upload screen before any cost (PDF opens, ≤ 4 pages, text layer, PARI title block); reason shown in a dialog; turned-away files do not use the live allowance; default allowance 30 → 100 | `08f4dde` |
| Raw exception text on a failed review; stale "Reviewing ..." after closing a drawing | plain sentence (details in the server log); status bar says what happened | `8699e4c` |
| Coverage "3 failed" next to "9 fail" looked contradictory; the robot top plate listed 35 LY-005 rows; only the 3 px outline of a markup box took clicks | coverage rows say "Rules ..."; 3+ findings of one rule share an expandable row (sheet and Excel unchanged); whole box clickable | `e20fac5` |
| C01 "stays quiet" but shows 2 findings | note says both come from the original cam plate (verified: same dates, H7 bore, plating) | `cf1ba23` |
| Anti-back lever material read "20MnCr5 1" | revision marks (Δ1) in title-block cells are not part of the value; on the 1,160 client drawings 8 fields change, all losing a revision digit | `77c83b8` |
| The lever's critical F7 (note only) had no box; Q&A note citations not clickable | notes placed from the stage-1 text lines that make them up | `a8c5090` |

## Checked

589 unit tests, 76 regression tests, ruff, format and pyright clean; `di eval review --no-understand` unchanged
(code 71/71). Front end built and driven end to end in headless Chrome 156 against a local server: login, help,
rulebook (search and filters), reports, options, all four demos (cached, $0), findings, sheet boxes,
accept/reject, filters, zoom/pan, sort, review commands, Excel and annotated downloads, Q&A (suggested and
typed) with clickable citations, live upload (robot top plate, 187 s, $0.076) with Q&A, rejected uploads
(blank, guideline, corrupt, 10-page scan), close and reload. All four demo drawings still replay from the cache.

## Before the demo

- Redeploy the Space from this branch, then set the Space variable `DI_DEMO_MAX_LIVE_RUNS` to 100 (it is set
  to 30 on the Space; the code default does not override it). Restart the Space the day before.
- Open the Space about 10 minutes before the demo: `cpu-basic` sleeps after 48 h without traffic.
- Pick and time the live-upload drawing in advance: dense drawings take about 3 minutes (the robot top plate
  186 s, almost all in the vision step); the 40K spacer took 50 s.
