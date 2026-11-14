# Nov 14: compare revisions, mark as checked, send to designer (three PILOT placeholders built)

On branch `feat/demo-compare-signoff` (design `docs/superpowers/specs/2026-11-14-compare-signoff-send-design.md`,
plan `docs/superpowers/plans/2026-11-14-compare-signoff-send.md`). Compare revisions is real and tested; the two
sign-off commands are demo mock-ups that store and send nothing, and say so on screen. Each was clicked through
in Chrome against a local server with the API keys blanked (so nothing could be billed).

| Feature | Where | What it does | Commit |
|---|---|---|---|
| Compare revisions | Home > Review | Pick the old revision (open drawings, or a demo drawing it opens); a Compare tab lists findings new, fixed and still open (was → now when the quote changed), title-block and revision-table changes, and notes. C01 → P13: 2 new (RQ-002, WST-207 on ⌀16 H7), 2 still open, "Both sheets say revision 00" | `f69bc13`, `5b2968f`, `cdb20c3` |
| Mark as checked | Review > Sign-off | Checker name, accepted / rejected / open counts, a warning for open findings (Next open finding, Sign off anyway) and for accepted fails (send instead); then a "Checked by … · date" chip in the status bar, and Reopen | `1dda4a5` |
| Send to designer | Review > Sign-off | Message preview to the drawn-by number with one line per accepted finding (requirement, where, correction), the Excel checklist and annotated sheet as working downloads, Copy text, Send (demo) → "Returned to designer" chip | `82e15f0` |

Matching findings across revisions: rule plus an anchor. Dimension and symbol refs (D12, S3) are positions in
the page's list, so a new dimension renumbers the rest; for those the anchor is the quote without its
tolerance plus the zone. A dimension whose nominal value changed shows as one fixed and one new finding.

Tests: 11 new (9 for the diff, 2 API tests replaying the cache: the cam-plate pair both ways, 404 and 409).
Spend: $0.

Still PILOT: confirm rules, edit rule, feedback analytics, run history across users (they need persistent
storage and user accounts). The Space still runs `3924c24`; redeploy after merging.
