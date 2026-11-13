# Nov 13: the 18 rules kept off the AI reviewers (106 -> 124 of 135 code/lookup rules)

On branch `feat/hard-checks`. The 29 rules left after Nov 12 were sorted by whether an AI reviewer could judge
them. The AI reviewers read stage 2's JSON and never see the sheet, so any rule about how something is drawn
(arrowheads, lines through text, which way a value reads, boxes, underlines) cannot go to them. Those 18 are
now code checks. The other 11 go to the AI reviewers next, or are split between AI and code (the backlog
lists which). The Space is not redeployed (still the Nov 08 code).

| Rules | What they check | Where |
|---|---|---|
| CN-003, ISO-023, ISO-025, ISO-027, ISO-029, ISO-030, ISO-031, DSM-023, DTT-002, WST-050 | dimension lines, arrowheads, text direction, lines through values, out-of-scale values, basic dimensions, radii on full circles | `review/checks/drafting.py` |
| MX-011, MD-013, MD-020 | basic dimensions for position, datum features of size, datum patterns | `review/checks/gdt.py` |
| NASA-100 | revision marks on the field against the revision table | `review/checks/title_block.py` |
| NASA-006 | "indicated area" notes have a leader or a marked area | `review/checks/consistency.py` |
| MX-026 | stitch welds give length and pitch (or the drawing has PARI's weld table) | `review/checks/threads.py` |
| MF-011 | carbon, alloy and tool steels are DES-11 grades | `review/checks/material.py` |
| MC-004 | a stated tap drill depth is at least 3 pitches past the thread | `review/checks/manufacturability.py` |

What changed in stage 1 (schema 2.3): `extraction/graphics.py` reads the drawing's graphics into
`PageExtraction.graphics`. For each dimension value it records the arrowheads and the dimension line or leader
the value sits on, the value's reading direction, whether it is boxed, underlined, crossed by a line or in a
table cell, and the radius of the arc a radius arrow lands on. It also reads full circles, revision triangles on
the field, datum triangles, and note lines a leader starts from. The field is kept out of the understanding
prompt, so the prompt and every cached reply are unchanged.

How PARI's PDFs draw things, which the reader relies on: every stroke is a separate straight segment (circles
and arcs are chains of short segments, never curves), every arrowhead is a filled triangle about 2.3 x 6.9 pt,
and Solid Edge strokes each arrowhead's legs as well. A text box is deeper than its characters, so a value's
own dimension line runs through its box without touching the characters.

The new checks follow the same lighter test bar as Nov 12: one passing and one failing unit test each
(`tests/test_checks_hard.py`), one sweep over the 137 client drawings with every finding read, and a check that
rests on a heuristic only warns. Sweep results are in the backlog's Status table. Findings on PARI's drawings
worth asking about are in `docs/pari_questions.md` §1b: angle values reading from the left (9 drawings), lines
through values (11), datum triangles in line with a dimension (3), an unmarked revision, and a steel that is
not a DES-11 grade.

Over all 1,171 client drawings (counted, sampled, not read one by one) the checks run without an error. Most of
their findings are on the P23Y5 sheets, an older drawing style none of the 137 use: ISO-029 on 231 drawings and
ISO-031 on 145. The sample read as real, but these two rules should be read with that in mind before the Space
shows them.

The answer keys changed in three ways:
- P14's planted, longer value now runs over a centre line. That is recorded as pre-existing.
- MF-011 and MF-013 entries now say warning, as their rules do. The key test now follows each rule's own
  `can_fail`.
- DSM-023 now catches P20 (R 0.2 drawn as R 8), so the recall floor is 19.

Tests: 648 unit and regression tests, ruff, format, pyright. `di eval review --no-understand`: recall 19/22 (19/19
where a check is built), precision 73/73, 0 false alarms on clean drawings. Spend: $0 (no model calls).
