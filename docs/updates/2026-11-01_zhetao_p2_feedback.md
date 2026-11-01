# P2 review corrections — Zhetao Zhang

The four requested data corrections are applied: HV 390 has tensile strength 132 kgf/mm²;
hard chrome's >=45 HRC limit applies only to the through-hardened-base alternative; Balzer's
residual hardness after tempering is strictly >55 HRC; the printed 9SMn28k / Spring Steel pair is
retained with automatic substitution disabled and the Sheet2/AISI 1213 conflict recorded.

Hardness limits now carry their state and operator in `hardness_limits`, rather than an unconditional
`min_base_hrc` field. Future checks must use the specified state. QPQ's preferred 30–50 HRC range is
explicitly through-hardened-only. HE30 retains the Sheet1 K7 condition. DES-11's page-1 selection versus
page-2 EN24/EN9 buffer-stock conflicts are recorded separately from the EN24 20-mm market-list omission.

The brittle test-file-hash assertion and the unused raw-material-catalogue YAML/model/test are removed.
The original 2024 workbook remains in `data/client_set`, and the 22-row numeric lookup subset remains.
Explanatory DES-12 material and pattern-order comments are restored without changing process matching.

Readiness remains **16 reference_ready / 2 reference_partial / 1 source_needed**, covering all 19 P2 rules.
MF-011 still needs the controlled approved-material list; MC-007 still needs tolerances/parallel-key
authority; MC-008 needs PARI to identify the retaining-ring/circlip standard and provide its groove table.
No unconfirmed standard or fabricated dimension is introduced.

Validation against main `b3ee904`: 571 tests passed, including all 74 regression tests; Ruff, format check
and Pyright passed. The reference audit verifies all cited source hashes. No paid API calls were made,
and no cached replies, shared prompts, drawing checks, baseline labels or model configuration were changed.

Apply the feedback patch to PR #7's branch, run CI on GitHub, then squash-merge under the current team rule.
Local checks do not constitute a claim that remote CI has already run or that the PR was merged.
