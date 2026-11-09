# Nov 08: pilot phase 1 (four PILOT placeholders built)

On `main` after the demo-hardening work. Each item checked with unit tests and in headless Chrome 156
against a local server, then on the Space.

| Feature | Where | What it does | Commit |
|---|---|---|---|
| Model per role | Tools > Options | Model and thinking level per role (Understand, AI reviewers, Q&A), kept in the browser; validated by the server; models with no API key on the server are disabled (the Space has only the Qwen key) | `ee1011e` |
| Measure | Review > Measure | Two clicks on the sheet: distance on paper and at the title-block scale; Esc stops. A2 sheet width read 592 mm (594), A3 419 mm (420) | `0d2ffe0` |
| Rulebook (.xlsx) | Rulebook ribbon, Rulebook page | All 174 rules with category, severity, check type, whether a check runs today (115), status and source | `95c21b6` |
| Batch review | Home > Batch review | Up to 10 PDFs; each screened (turned-away files listed with the reason, free); accepted ones reviewed live two at a time; per-drawing table, open any drawing, reports.zip with a summary | `3764966` |

Tests: 598 unit tests, 76 regression tests, ruff, format, pyright; `di eval review --no-understand` unchanged.
Live spend while building: about $0.15 (two live uploads, one batch, Q&A).

Still PILOT, for the next phases: compare revisions, mark as checked, send to designer, confirm rules, edit
rule, feedback analytics, and run history across users. All but compare revisions need persistent storage and
user accounts (phase 0).
