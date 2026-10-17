# Rulebook mapping

`rule_mapping.csv` is the triage behind the draft rulebook in [config/rules/](../../config/rules/) (task R). It has
one row for every rule in LatentView's *Drawing Check Rulebook* v0.2 (201) and *Missing Datums, Dimensions and
Points Detection Guide* (68), plus the PARI WP guideline items and team requirements that are not LatentView rules
(26). Each row says whether the rule is in the v1 rulebook and, if not, why. It opens in Excel (UTF-8 with BOM).

## Dispositions

| disposition | count | meaning |
|---|---|---|
| `v1` | 109 | In the rulebook as `repo_id` (89 LatentView, 13 PARI WP guidelines, 7 team requirements) |
| `merged` | 46 | A duplicate, folded into the rule in `merged_into` ("one rule, one finding") |
| `phase2_3d` | 35 | Needs the 3D model, native Solid Edge data, PDM or assembly data: LatentView's 3D phase |
| `other_family` | 62 | Sheet metal, castings / forgings / moulded parts, assemblies and BOM, machines and structures |
| `deferred` | 22 | A 2D drafting-quality check that needs geometry analysis (most LY and VW rules) |
| `needs_pari` | 16 | Can't be encoded until PARI gives a decision, list or profile; the `note` says what |
| `system` | 1 | A requirement on the system itself, met by design (RV-09: the rulebook version is stored) |
| `v1 via …` | 2 | A PARI guideline note handled by an existing v1 rule |
| `checker`, `guard` | 1 each | A reminder for the human checker, or a condition that is not a finding by itself |

## Columns

- `repo_id` … `note`: the rule as it appears in `config/rules/*.yaml` (for `v1` rows), the triage call and the
  reason for it. `supporting_reference` cites the engineering standards that back a rule (e.g. ISO 129).
- `lv_severity` … `lv_linked`: LatentView's own severity, check type (Rulebook: Auto / AI / Manual; Detection
  Guide: D deterministic, G geometric, L LLM, H human), rationale, verification method, guards and linked rules.
  The `Rule` schema has no fields for these, so the YAML keeps them as comments above each rule.

## Status

Everything is `status: draft`. Severities are LatentView's, except three lowered in triage (DM-002, MF-003,
TL-003; see their notes). The rules name 74 check functions and none is built yet. Until a rule's reviewer exists,
the rule should report `not_checked` (US-1.1).
