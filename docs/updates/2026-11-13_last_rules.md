# Nov 13 (later): the last 11 rules, every code/lookup rule built (132 of 132)

On `main` (`a2fe00d`, docs `2277d98`). These were the rules planned for the AI reviewers (MX-012, DM-002, MD-002, SC-001, MX-009)
or split between AI and code (WST-206, MX-006, MP-012, MC-007, MC-008, WST-242). Each was run on the seeded (28)
and held-out (24) drawings, then on 30 fresh drawings never used for tuning (10 with keyways, 10 round parts
with thread reliefs, 10 random), and every new finding was read. Where the AI was wrong more often than right,
the rule moved to code or waits for an input. The per-rule table is in `docs/backlog/rules_to_build.md`.

| Now | Rules |
|---|---|
| AI rules | MX-012 (drawing_practice), SC-001 (design_intent); MX-006 has code candidates but waits for view geometry |
| Code, after the AI tries | MD-002 (exact symbols and tolerances, ±0.02 provisional), DM-002 (the same distance twice, from the dimension lines), MX-009 (call-out text) |
| Code on stage 1's graphics | MP-012 (ordinate origin marked 0 and on a datum) |
| Tagger + code | WST-206, MC-007, MC-008 (waits for PARI's ring standard), WST-242 |

What is new:
- **The dimension tagger** (ADR 0013). One vision call per page, inside the understand node, labels the
  dimensions the split checks need: fits on internal or external features, keyway, circlip-groove and undercut
  sizes. The checks do the table arithmetic and only warn. A text-only tagger labelled nothing on a keyway that
  only shows on a section, so it sees the images. It is reliable for fits; for undercuts and keyways it also
  picked chamfers and a shaft's own diameter, so the checks only use a tag whose size is plausible for its
  feature.
- **Candidates for AI rules**: code lists what a rule may judge (`params.candidates`); with none the rule is not
  sent. Used by MX-006.
- **What the AI got wrong, and moved to code**: as AI rules, MD-002 restated stage 1's facts and once read ±0.1 as
  tight, DM-002 was right on about 2 of 9 (equal values on different features), MX-009's two findings were a
  groove width and an Ra value, and MX-006 called coordinate-located patterns unlocated.

Results:
- Seeded, with the AI reviewers (cached): recall 19/22, 19/20 where a check is built, precision 93/99, no code
  false alarms on the clean drawings and 1 AI warning on them. The run before this batch was 20/22; adding SC-001
  to design_intent shifted that reviewer's answers, and P19 (TL-002), already noted as unstable on Oct 25, is
  missed. Code only: 19/22, 79/79.
- Fresh 30: DM-002 2 of 2 right, MD-002 1 (real by the rule), MP-012 1 (plausible), MC-007 2 (1 an across-flats
  taken for a keyway, 1 unclear), MX-012 5 (about 3 plausible).
- The answer keys record MD-002 on the cylinder rod (20±0.02, no datum) and on P15 (the planted 70±0.002) as
  pre-existing.

Tests: 659 unit and regression tests, ruff, format, pyright. Spend: about $4.95 of the $10 allowed.

Next:
- Redeploy the Space: it still runs the Nov 08 code, so none of today's 26 checks or the tagger are live.
- Send PARI the new questions (`docs/pari_questions.md` §1b and 3.1, 3.2, 3.6, 3.7).
- Read more of the ISO-029 / ISO-031 findings on the P23Y5 sheets before the Space shows them.
- View geometry (which feature a dimension is on) would open MX-006, MX-002 and DM-002 across views.
