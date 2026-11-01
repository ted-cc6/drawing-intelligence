# P2 reference tables — Zhetao Zhang

This implements the reference-data responsibility: transcribe and cite tables, add typed loading, and add
structure tests following the supplied `tests/test_reference_tables.py`. The supplied test remains freely editable; no test pins its file hash.
The initial 200-PDF sweep was not a measure of this table contribution's completeness.

## Delivered

- DES-11 page 1: all 13 materials, six process columns per row, 21 numeric and 57 NIL cells. Original material
  names/equivalents, form and size selection, UTS/stress, applications, shared notes and exception policy are
  retained. Both source units and normalised case-depth units are available; 20–25 microns is 0.020–0.025 mm.
- DES-11 page 2: all six material rows, 11 stock-form lists, 251 market-size entries, buffer-stock lists and
  supply notes. The EN24 20-mm buffer/market discrepancy and page-1 preferred-diameter versus page-2 buffer-stock conflicts for EN24 and EN9 are recorded without silently changing either source.
- DES-12: all ten existing processes now include the input prerequisites, process constraints and remarks.
  QPQ's case-hardening advice remains a recommendation. Its preferred 30–50 HRC band applies to through-
  hardened steels only. Hard chrome has a >=45 HRC through-hardened-base alternative; Balzer requires
  residual hardness after tempering strictly >55 HRC.
- Stock workbook: the typed direct-lookup subset covers 22 numeric rows. The original 16-sheet workbook
  remains in `data/client_set`; an unused full catalogue copy has been removed. Graphical profile diagrams
  are not transcribed.
- US–India workbook: all 14 Sheet1 rows; the HE30 condition from K7 is retained. The printed 9SMn28k /
  Spring Steel pair remains visible but cannot be applied automatically because Sheet2 identifies AISI 1213.
- Westermann: full 34-row numeric hardness comparison (including both HB ball types, HRB and tensile strength),
  18 material specific weights, ten self-holding taper designations with source alpha/D/thread, twelve
  standard taper ratios, all taper-pin nominal diameters, fifteen ISO coarse-thread undercut rows with
  external/internal columns and angle conditions, centre-hole pilot lists, and both nominal key tables.
- Loaders integrate with `load_reference()`, and the existing rulebook version automatically includes the data.
  No shared prompts, baseline labels or drawing check functions are changed.

## Audit findings and source interpretation

1. C45/C55 appear in two DES-11 rows for different forms. A candidate lookup returns both unless form is known.
   The two 20MnCr5 rows have different PARI designations/applications; they are not collapsed into one row.
2. Page 1 prefers EN24 >32 mm and EN9 ≤32 mm, while page 2 lists EN24 buffer stock at 20/30 mm
   and EN9 buffer stock at 36–100 mm. Both source statements are preserved in `source_anomalies`;
   PARI must clarify selection policy rather than treating stock availability as an automatic substitution.
3. DES-11 note iii explicitly allows justified special selections. Its 13 preferred grades are not an exhaustive
   approved-material list. Blank mechanical-property cells remain null, not zero or NIL.
4. The EN24 raw note prints `= > 32 dia.`; its `>32` interpretation follows WPM-005 and is recorded explicitly.
5. UTS/stress units stay `Kg/mm² as printed`; no automatic conversion or kg/kgf reinterpretation is introduced.
6. The hardness table contains values outside its own testing footnotes (for example printed HRC 68, while
   the footnote says HRC use 20–67). Both the printed rows and footnote limitations are retained.
7. Metric 4 and Metric 6 print different alpha values; the table is transcribed as printed, not silently repaired.
8. The 2016 DES-11 stock table and the 2024 stock workbook remain distinct sources. No claim is made about
   present-day purchasing availability or compliance with newer standards editions.

## Remaining source gaps

### What MC-008's historical AI comment means

The comment `LatentView Rulebook v0.2 MC-08 (... their check: AI)` records the original rulebook's method.
The active project fields are `check_type: lookup`, `check: circlip_groove_standard` and
`params: {table: circlip_grooves}`. The source credit is not an ownership assignment. MC-008 remains in the
P2 backlog; the reference table still needs to be identified. Page 49 contains keys/keyways, pins and rivets,
and does not provide a retaining-ring/circlip-groove table.

### Page-49 transcription correction

The Woodruff option for a shaft over 8 up to 10 mm, key width 2.5 mm and height 3.7 mm, has shaft-keyslot
depth **2.9 mm**. An earlier transcription incorrectly recorded 2.1 mm. This is corrected, and a new
source-internal structure test checks all eleven Woodruff rows: the two printed depths sum to key height
plus 0.2 mm. This relation is a check on this table, not a universal keyway-clearance requirement.

`P2_REFERENCE_STATUS.md` covers every one of the 19 rules. Sixteen have source-ready inputs for the documented
scope; MF-011 and MC-007 have partial reference coverage; MC-008 still needs its source standard/table.

- MF-011: confirm/provide the full controlled approved-material list if the check must decide approval rather
  than recognise the DES-11 preferred subset.
- MC-007: nominal taper/Woodruff dimensions are transcribed, but applicable keyway tolerances and any required
  parallel-key standard still need an authoritative source.
- MC-008: identify PARI's retaining-ring standard and supply the associated groove/tolerance table. DES-11 does
  not contain it. No DIN/ISO/IS standard is chosen on the team's behalf.

These gaps are data/authority gaps, not errors to conceal with zero findings or fabricated dimensions.

## Validation and GitHub handoff

Run the commands from the project root:

```bash
uv sync --frozen
uv run pytest tests/test_reference_tables.py tests/test_reference_tables_des11.py tests/test_reference_tables_p2.py
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -m 'not live'
uv run python scripts/p2_reference_audit.py --out data/eval/p2_reference_tables/audit.json
```

The Colab notebook installs this contribution on its own clean task branch and downloads a patch/source ZIP.
Use the new notebook's workspace, not the earlier experimental P2 check workspace: the complete DES-11 schema
preserves more information. Submit one P2 reference-data PR to Binjie, explicitly retaining the three source
gaps above. This handoff is independent of the fresh AI-reviewer evaluation and requires no paid model calls.
