# Rulebook mapping

`rule_mapping.csv` is the triage behind the draft rulebook in [config/rules/](../../config/rules/) (task R). It has
one row for every rule in LatentView's *Drawing Check Rulebook* v0.2 (201) and *Missing Datums, Dimensions and
Points Detection Guide* (68), plus the PARI WP guideline items and team requirements that are not LatentView rules
(27), plus every rule found in six engineering books (547, see below). Each row says whether the rule is in the v1
rulebook and, if not, why. It opens in Excel (UTF-8 with BOM).

## Dispositions

| disposition | count | of which books | meaning |
|---|---|---|---|
| `v1` | 174 | 64 | In the rulebook as `repo_id` (89 LatentView, 13 PARI WP guidelines, 8 team, 64 books) |
| `merged` | 411 | 365 | Folded into the rule in `merged_into` ("one rule, one finding"). For a book row, the book is added to that rule's `supporting_reference` |
| `phase2_3d` | 38 | 3 | Needs the 3D model, native Solid Edge data, PDM or assembly data: LatentView's 3D phase |
| `other_family` | 84 | 22 | Sheet metal, castings / forgings / moulded parts, assemblies and BOM, machines and structures |
| `deferred` | 53 | 31 | A 2D drafting-quality check that needs geometry analysis (most LY and VW rules) |
| `needs_pari` | 49 | 33 | Can't be encoded until PARI gives a decision, list or profile; the `note` says what |
| `not_applicable` | 27 | 27 | Inch-only, obsolete, or specific to the book's own organisation (its numbering, release process, CAD files) |
| `system` | 1 | | A requirement on the system itself, met by design (RV-09: the rulebook version is stored) |
| `v1 via …` | 2 | | A PARI guideline note handled by an existing v1 rule |
| `checker` | 3 | 2 | A reminder for the human checker, not a finding |
| `guard` | 1 | | A condition that is not a finding by itself |

## The books

| prefix | book | candidates | new v1 rules |
|---|---|---|---|
| `ISO` | ISO 129:1985 *Technical drawings: Dimensioning, general principles* (the free preview: clauses 1 to 4.4.2 only) | 35 | 8 |
| `NASA` | NASA Goddard GSFC-X-673-64-1F *Engineering Drawing Standards Manual* (1994) | 139 | 17 |
| `HNF` | HNF-64101 Rev 00 *Preparation Standards for Engineering Drawings* (Hanford, US DOE, 2020) | 69 | 5 |
| `DSM` | NAAMS Global Standard Components, Section A *Design Drawing Standards and Tolerances* (2015) | 57 | 4 |
| `DTT` | *Dimensioning and Tolerancing* tutorial slides (author not stated; ASME Y14.5-1994) | 64 | 5 |
| `WST` | *Westermann Tables for the Metal Trade*, revised to Indian Standards (PARI's WP Specific Guidelines; a scan) | 183 | 25 |

ISO 129 is an ISO standard and the next four follow ASME and are partly inch-based, so their rules were kept only
where they hold for a metric drawing too. Westermann is the one PARI supplied: Indian Standards of the 1960s and
1970s (IS 696 drawing practice, IS 2102, IS 919 fits, IS threads, steel designations, IS 1956 heat treatment).
Its conventions that may be obsolete went to `needs_pari` or `not_applicable`. Its material candidates mostly
became published sources for existing rules (MF-01, MF-011, WPM-001, WPM-002) or PARI questions, because PARI
names materials as M.S., C-45 or EN grades rather than in the book's IS designations; the new rules from that part
check hardness values and heat-treatment notes. PARI's printed
general-tolerance table matches the book's IS 2102-1969 medium class (steps at 315 mm), so the IS 2102 lookup
table should come from that edition (WST-078).

Where several books state one rule, the fullest statement is kept and the others are merged into it. The simple
text rules were tried on the 1,175 client drawings. Rules that clash with PARI's own conventions, or depend on its
ISO vs ASME choice, went to `needs_pari` (e.g. PARI writes `MM` in capitals: 88 sheets), and kept rules got a note
on what not to flag. Each row's `note` records the call.

## Columns

- `repo_id` … `note`: the rule as it appears in `config/rules/*.yaml` (for `v1` rows), the triage call and the
  reason for it. `supporting_reference` cites the published sources that back a rule; 76 of the 110 rules from
  LatentView, PARI and the team now have one from the books.
- `lv_severity` … `lv_linked`: LatentView's own severity, check type (Rulebook: Auto / AI / Manual; Detection
  Guide: D deterministic, G geometric, L LLM, H human), rationale, verification method, guards and linked rules.
  The `Rule` schema has no fields for these, so the YAML keeps them as comments above each rule.
- `quote`: for book rows, a short extract from the book (at most 30 words) that supports the rule. `lv_id` holds
  the book candidate's id (e.g. `NASA-30`) and `source_section` its clause and page (for Westermann, the PDF page,
  left or right half of the scan, and the book's page).

## Status

Everything is `status: draft`. Severities are LatentView's, except three lowered in triage (DM-002, MF-003,
TL-003; see their notes); the severities of the PARI, team and book rules are the team's proposals. The rules name
130 check functions; 15 are built (`di rules` shows which). Until a rule's check or reviewer exists, the rule
reports `not_checked` (US-1.1, ADR 0010).
