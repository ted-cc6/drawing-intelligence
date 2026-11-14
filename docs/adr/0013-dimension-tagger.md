# 0013 The dimension tagger: AI finds the feature, code checks the table

**Status:** accepted · 2026-11-13

## Context
After the Nov 13 drafting checks, 11 code/lookup rules were left. They were sorted by whether an AI could judge
them: five as AI rules (MX-012, DM-002, MD-002, SC-001, MX-009) and six split between AI and code (WST-206,
MX-006, MP-012, MC-007, MC-008, WST-242). The split rules compare a dimension with a standard table (a keyway's
width for its shaft, a thread undercut's diameter), but stage 1 cannot say which dimension is a keyway's width,
and stage 2's understanding linked only 82 of 978 dimensions to a feature on the seeded and held-out drawings,
and named no keyway, groove or undercut at all.

## Decision
- **A tagger** (`understanding/tagging.py`, prompt `prompts/tag.md`): one call per page, inside the `understand`
  node right after the understanding call, so the workflow graph and the web demo's stage list do not change.
  It sees the page images and stage 2's dimensions and labels the ones that play a role a check needs
  (`internal_fit` / `external_fit`, keyway width / depth / bottom, circlip groove diameter / width, undercut
  width / diameter / radius) with `of`, the shaft, bore or thread they belong to. A text-only first version
  labelled nothing on a drawing whose keyway is only visible on a section, so it uses the images, on the
  understanding model (qwen3-vl-plus, about $0.005 a page).
- **Tags are checked like citations**: a tag naming a dimension the page does not have, or misquoting it, is
  dropped (`TagResult.dropped`). They are saved in `UnderstandingResult.tagging` and reach the checks as
  `ReviewContext.tags`. `UnderstandingResult.billed_usd` counts their cost wherever understanding cost is summed.
- **The checks stay pure** (ADR 0010): `review/checks/features.py` reads the tags and does the arithmetic. Every
  such rule only warns, and a tag is used only when it is plausible for its feature (a keyway width 0.15-0.5 d,
  an undercut diameter 0.7-1.1 d, never a chamfer or count call-out, never on a blind tapped hole): on unseen
  drawings the tagger also labelled chamfers, a shaft's own diameter and tolerance fragments. Without the
  tagger (no understanding) these rules are not checked.
- **Candidates for the AI reviewers** (`llm_reviewer.CANDIDATE_FINDERS`, a rule's `params.candidates`): code
  lists the items a rule may judge and the rule is sent with them; with none on a drawing it is not sent and is
  `not_applicable`. Used by MX-006 (pattern call-outs), which then waits for view geometry.

## Measured, and what changed because of it
Seeded (28) and held-out (24) drawings, then 30 fresh drawings never used for tuning, every new finding read:
- **MD-002** as an AI rule only restated stage 1's facts (and once read ±0.1 as tight): now code on the exact
  symbols and tolerances.
- **DM-002** as code candidates judged by the AI: about 2 of 9 right, the rest equal values on different
  features. Now code: the same distance twice, from stage 1's dimension lines (4 of 6 right on the 137 client
  drawings, 2 of 2 on the fresh set). Duplicates across views are not checked.
- **MX-009** as an AI rule: its two findings were a groove width and an Ra value. Now code on the call-out text.
- **MX-006** as AI: it called patterns unlocated that are located by coordinates; it cannot tie the coordinates
  to the pattern without view geometry, so it waits for geometry like MX-002.
- **MX-012** stays an AI rule, in drawing_practice: about 4 of its 6 findings on unseen drawings are plausible.
  Placed first in design_intent beside TL-002, it changed that reviewer's answers (P19 lost, 5 more false
  alarms), so it moved. **SC-001** stays an AI rule in design_intent and raised nothing; its presence there still
  shifts design_intent slightly (seeded with AI: 19/22, design_intent 13/19, was 20/22 and 13/17).
- **The tagger** is reliable for fits (H7 on holes) and found the one keyway width on the held-out set;
  undercut and circlip tags were mostly wrong before the plausibility guards.

## Consequences
- Every code/lookup rule has a check (132 of 132, 127 check functions, with MD-002, DM-002 and MX-009 back in
  code); 42 rules are AI-reviewed (MX-012, SC-001 and MX-006 added, MX-006 waiting for geometry). MC-008 is built but not checked until PARI names the retaining-ring standard.
- One more model call per page (about $0.005 and 10-15 s); a cached run is still free.
- The tags are an AI judgement: findings from them are warnings and should be read as leads.
