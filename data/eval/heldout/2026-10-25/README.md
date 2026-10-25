# Held-out validation, 2026-10-25

The review run on client drawings that nothing was built or tuned on, with every finding labelled. The planted-
error set measures recall; its precision is optimistic because the checks and the LLM reviewers were tuned on it.
This measures precision on unseen, real drawings.

## How the drawings were chosen

`di eval heldout --n 25 --seed 2026` (`src/drawing_intelligence/eval/heldout.py`): 25 drawings at random from
`data/client_set/`, leaving out the 368 drawings the development sweeps looked at (two random samples of 200, seeds
1 and 2) and the four sample drawings. One of the 25 turned out to be PARI's DES-12 guideline PDF, not a drawing (0
findings; left out of the numbers below). The pool now skips guideline and template folders, so the same seed
picks a different set today; this run's drawings are the ones listed in `findings.csv` plus that document.

Full review: understanding (`qwen3-vl-plus`, off), the code checks and lookup tables, the three LLM reviewers
(`qwen3.8-max`, off), verify. Cost $0.906 for 25 PDFs (~$0.036 each); about 2 minutes per drawing. Replies are
cached in `data/cache/`, so a re-run is free.

## Labels

`findings.csv`: one row per finding, with `label` = correct / incorrect / unsure and a reason.

**The labels are provisional:** made by Claude from the drawing text and the rendered sheets, not by an engineer.
The PARI proxy should confirm or overrule them (change `label`, and `labelled_by`).

- *correct* for a code finding means the drawing breaks the rule as written. Whether PARI wants that rule (LY-005
  decimals, TB-016 sign-off dates on released drawings) is a separate question, noted in the reason.
- *unsure* means the finding depends on how the part is used, which the drawing does not say (whether a shaft
  is turned between centres, whether a pin diameter mates with something).

## Results (24 drawings, 115 findings)

| | correct | incorrect | unsure | precision (correct of decided) |
|---|---|---|---|---|
| Code checks and lookups (60) | 58 | 0 | 2 | **100%** |
| LLM reviewers (55) | 14 | 25 | 16 | **36%** (25% if every unsure is wrong, 55% if every one is right) |
| All (115) | 72 | 25 | 18 | 74% |

3 of the 24 drawings use a variant title block (no title-block fields read; their title-block rules not checked).

By LLM rule:

| rule | correct | incorrect | unsure | what it raised |
|---|---|---|---|---|
| NM-008 notes copied from another drawing | 1 | 11 | 0 | PARI's standard notes: bilingual (French) copies, NDT and retapping notes, template note variants |
| WPS-004 plating allowance | 4 | 4 | 3 | right on H7 holes and tight bands; wrong on clearance holes and lengths |
| MF-005 heat treatment and its stage | 4 | 0 | 5 | right where the field says --- but a note specifies a treatment; unsure where only the stage is missing |
| TL-002 fits on mating features | 1 | 3 | 5 | right on a locating pin; wrong on clearance holes |
| MF-007 material suits the function | 1 | 4 | 0 | right on a title block contradicting the note; otherwise speculation |
| NM-002 notes contradict each other | 3 | 0 | 0 | |
| others (MC-003, MC-009, MX-015, WF-014, NASA-047) | 0 | 3 | 3 | |

## What it shows

1. **The code checks hold up on unseen drawings:** no incorrect finding in 60.
2. **The LLM reviewers are at Spike E's level (32–61%), below the 58% measured on the tuned set.** Most of the
   noise is two rules: NM-008 (11 of 12 wrong) and MF-007 (4 of 5 wrong). Without them, LLM precision on decided
   findings would be 12 of 22 (55%).
3. **PARI writes `#` in title-block fields to mean "see the notes"**: the notes then say `# MATERIAL: M.S`,
   `# FINISH: I.Z.B.P. (TRIVALENT)`. The lookup checks skip such drawings today (material not recognised); reading
   the `#` notes block would let them check most of the client set.
4. **Real issues found:** inverted limits (RQ-002), title-block scale against the drawn scale (TB-006), plating on
   H7 holes and tight bands (WPS-004), title-block heat-treatment field `---` against a note that specifies
   hardening (MF-005, NM-002), a title-block material contradicting the note (MF-007, NM-002), a locating pin with
   no fit (TL-002).

## After the fixes (same 24 drawings, re-run 2026-10-25)

Three changes, then `di eval heldout --drawings drawings.txt` on the same drawings (`findings_after_fixes.csv`;
labels carried over for unchanged findings, new ones labelled the same way; $0.212, only `design_intent` re-ran):
- title-block fields printed `#` are read from the `# MATERIAL:` / `# FINISH:` notes, so the material and
  treatment lookups now see these drawings;
- NM-008 is held back until PARI lists its standard notes;
- MF-007 may only be raised on a fact the drawing states (`only_when`).

| | correct | incorrect | unsure | precision |
|---|---|---|---|---|
| Code checks and lookups (66) | 58 | 0 | 8 | **100%** |
| LLM reviewers (41, was 55) | 17 | 13 | 11 | **57%** (was 36%) |
| All (107) | 75 | 13 | 19 | 85% |

- The 6 new code findings are all WPS-002, IZBP on alloy steel, now visible through the `#` notes. That is the
  open PARI question (unsure): on the 200-drawing development sample 39 of 141 comparable sheets do it, so it looks
  like accepted practice.
- The largest remaining LLM noise is WPS-004 (8 of 18 wrong): plating warnings on untoleranced diameters and on
  internal threads already covered by the "retapping after surface treatment" note. An `only_when` (a fit or a
  band under 0.1 mm; not threads covered by retapping) is the next fix to try.
