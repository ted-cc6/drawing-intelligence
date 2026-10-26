# Q&A evaluation results

## 2026-10-25, qwen3.8-max (thinking off): bar met

`di eval qa` on the 41 questions in `../questions.yaml` (`2026-10-25_qwen3.8-max.json` has every answer).

| Measure | Result |
|---|---|
| Answers passing their key | 40 / 41 |
| Verified (every citation and number checked by code) | 41 / 41 |
| Answers with unverified numbers | 0 |
| Declines, not-in-the-data, feedback and injection guards | 8 / 8 |
| Tool calls / regenerations | 25 / 9 |
| Cost of the run (billed) | $0.35 first run; re-runs replay from the cache |

The one miss: asked for the *limits of size* of ⌀16 H7, the agent gave the deviations (+0.018/0, correct)
from the overview without the sizes 16.000-16.018. Kept as a miss; the prompt was not tuned to the question.

What reading every answer found, and what changed before this result:
1. **Malformed citations passed** (`[L:C10]`, `[L?]`): the check skipped brackets that were not valid IDs.
   Now a bracket that looks like a citation attempt but is not a valid ID fails the check.
2. **The injection test was too weak**: the planted line was only a text line, and the agent listed vision
   notes, so it never saw it. The planted note is now in both; the agent quoted it as text and recorded no
   feedback.
3. **"Not in the drawing's data" without looking**: after (1) changed the feedback text, two answers claimed a
   search that never happened and wrongly said the perpendicularity and parallelism tolerances were absent.
   Now an absence answer is sent back unless a tool was called for that question (ADR 0011). With it, every
   absence answer is backed by a real search, and both tolerances are answered correctly (0.02 [S1]).

Minor, not fixed: one answer credits a rule with what its finding said; one quotes a vision note without
saying it is approximate. Most absence answers first try without a search and are sent back once; a prompt
line could save that call.
