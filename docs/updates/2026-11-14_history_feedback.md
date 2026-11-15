# Nov 14 (later): run history across visitors and feedback analytics (two PILOT placeholders built)

On branch `feat/demo-history-feedback` (design `docs/superpowers/specs/2026-11-14-history-feedback-analytics-design.md`,
plan `docs/superpowers/plans/2026-11-14-history-feedback-analytics.md`). Both are demo features: kept in the
server's memory, cleared when the Space restarts, and they say so on screen. Clicked through in Chrome with two
browser contexts (two visitors) against a local server with the API keys blanked.

| Feature | Where | What it does | Commit |
|---|---|---|---|
| Run history across visitors | Reports > Run history, Cost & latency | Every review since the server started, by anyone: time, Visitor N (you), drawing (demo title, or "Uploaded PDF"), mode, status, findings, fails, review time, review and Q&A cost, model; KPIs; cost and latency per model (live runs only in the averages). Refreshes every 5 s | `7a2037d`, `b301c7f`, `f87d790` |
| Feedback analytics | Reports > Feedback analytics | Decisions from the Accept/Reject buttons of every visitor: accept rate overall, code vs AI, by reviewer, and by rule with the most rejected first | `7a2037d`, `b301c7f`, `f87d790` |

Privacy: nothing new about an upload outlives its session. Uploads appear only as "Uploaded PDF"; feedback rows
keep the rule and the decision, and a finding with no rule (an AI finding whose requirement the model wrote) is
counted without its text. Open question, unchanged by this work: `data/feedback/feedback.jsonl` keeps comments,
and the Q&A tool's file names and quotes, after sessions end.

Tests: 13 new (8 for the ledger; 5 API tests replaying the cache: two visitors, the password, a changed decision,
Q&A cost after closing, an upload listed without its name). Spend: $0.

Still PILOT: confirm rules, edit rule. The Space still runs `3924c24`; redeploy after merging.
