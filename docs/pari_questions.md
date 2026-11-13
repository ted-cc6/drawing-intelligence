# Questions for PARI

Every open question for PARI in one place, so they can be asked together. Most important first. Each answer
changes a rule in `config/rules/` (its `result: warning` is removed, a threshold is filled in, or a parked rule
is built or dropped). When PARI answers, record it next to the question and update the rule.

Last updated 2026-11-13.

## 1. Findings from the new checks on PARI's own drawings (2026-11-12)

These came up when the new heat-treatment and plating checks ran over the 137 client drawings. Each is either a
real issue on the drawing or a PARI practice the rule should allow.

| # | Question | Example drawing | Rule |
|---|---|---|---|
| 1.1 | Should threads be masked during IZBP plating? PARI's drawings never say so, so the masking check covers only hard chrome, flash chrome, hard anodizing, ENP and Balzer. | any IZBP part with tapped holes | MF-006 |
| 1.2 | EN24 parts say "TO BE HARDENED UPTO 32-35 HRC". DES-11 gives EN24 toughening 24-32 HRC or through hardening 50-55 HRC. Is 32-35 HRC intended, and which process is meant? | PRP80C021016001, PRN85B602007002 | WPM-002 |
| 1.3 | 20MnCr5 parts are case hardened to 55-60 HRC and 40-45 HRC; DES-11 says 56-60 HRC. Are these accepted deviations? | 45K_TCP_PIN_SLEEVE, PAY27L112022001 | WPM-002 |
| 1.4 | A 20MnCr5 part is induction hardened, where DES-11 prints NIL. Is that accepted? | 20K_MODULE PALLET ANTI BACK LEAVER_01 | WPM-001 |
| 1.5 | Chrome-plated parts carry chamfers (0.5 x 45°). DES-12 asks for edges blended by a radius. Are chamfers accepted on flash chrome? | PRJ93A040170001 and 7 others | WPS-005 |
| 1.6 | Chains of dimensions close on an overall with no link marked as reference (28.5 + 16.5±0.1 = 45). Does PARI accept this under general tolerances, or should one link be a reference? | 40K_LM RAIL ADAPTAR PLATE and 7 others | DM-003 |
| 1.7 | "ZINK BLACK PASSIVATION" is written on one drawing. Is it IZBP (trivalent)? Should the drawing use DES-12's name? | PRR74A055037005 | WPS-001 |
| 1.8 | A portrait sheet has none of the template's standard notes (UNSP. RADII, UNSP. CHF, Gen Tol). Is that template still in use? | PRT84F150002001 | NM-001 |
| 1.9 | Two drawings ask for "USE STD. DIA.35g6 En-8(D) BRIGHT BAR". DES-11 selects EN24 above Ø32, and Ø35 is not on the EN8 raw-material list (nearest Ø36). Is the Ø35 En-8(D) bright bar intended? | PRF83A104011002, PRF83A106004002 | WPM-005, MF-003 |
| 1.10 | "M50 x 1.5 x 30 DEEP" in 20MnCr5 is 0.6 × D of thread. Is a fine-pitch thread shorter than 1 × D accepted? | PRV59J200037001 | MC-006 |
| 1.11 | Three sheets leave PART CLASS. empty. Is the class required on every part? | 45K_DUNNAGE DOOR LM BLK MTG PLT, 05015NB02996/7 | SC-002 |
| 1.12 | Datum A is placed on the M65 x 2 thread with no MD / PD / LD qualifier. Which diameter is meant? | PRR74A055037005 | MD-021 |

## 1b. Findings from the drafting checks on PARI's own drawings (2026-11-13)

From the checks that read how dimensions are drawn (arrowheads, lines, text direction). All are warnings.

| # | Question | Example drawing | Rule |
|---|---|---|---|
| 1b.1 | Angle values (20°, 25°, 30°) read from the left, top to bottom. ISO 129 asks for values readable from the bottom or the right. Is Solid Edge's default placement accepted? | PRS85A281021001, PRE93A203014001 and 7 others | ISO-031 |
| 1b.2 | Hatching, centre and extension lines run through values (15°, 45°, Ø6.6, 35±0.1, R 6). Should lines be broken around a value? | PAV14B041607002, PRE93B305014003 and 9 others | ISO-029 |
| 1b.3 | A datum triangle sits on the extension line exactly where a dimension's arrow lands (datum A with 20, 90, 170). Under ASME Y14.5 that makes the datum the feature of size, not the face. Which is meant? | PRC89A200079001, PAB87S010051001, 40K_LM RAIL ADAPTAR PLATE_RH_02 | MD-013 |
| 1b.4 | Revision 2 is in the revision table but no Δ2 marks where it changed the drawing. Does PARI mark every revision on the field? | PRR74A055037005 | NASA-100 |
| 1b.5 | SAE4140 / 41CrMo4 is not one of DES-11's grades. Is it approved for this part? | PRQ93C123008001 | MF-011 |

## 2. Rules that only warn until PARI confirms the convention

| # | Question | Rule |
|---|---|---|
| 2.1 | Must a thread insert call-out name the insert (make, type, length)? | MX-029 |
| 2.2 | Are only the preferred scales allowed (1:2, 1:5, 1:10, 1:20, 1:50; 2:1, 5:1 ...)? | DSM-012 |
| 2.3 | Must a paint or powder-coat colour be given by code (RAL 7035) rather than a name? | MF-013 |
| 2.4 | Must a revised drawing quote its change reference (the CAR. NO. column)? | RV-003 |

## 3. Needed before the next checks can be built (medium tier)

| # | Question | Rule |
|---|---|---|
| 3.1 | When does a part need datums? For example: any tolerance tighter than some value, or any GD&T frame. | MD-002 |
| 3.2 | Above what part mass must lifting points and their rated capacity be shown? | SC-001 |
| 3.3 | Is there an approved or preferred materials list? Sheet 2 of the US-India file is not one. Built 2026-11-13 with DES-11 as the list for carbon, alloy and tool steels; is that right, and which list covers mild steel, stainless, cast iron, aluminium and plastics (DES-11 also prints SS304, FG260 and FG300)? | MF-011 |
| 3.4 | What do the PART CLASS. values in the title block mean (T+S, A, B, C)? Which classes count as safety critical? Is "WELD CLASS : B" the weld quality level (e.g. ISO 5817 B)? | SC-002, WF-007 |
| 3.5 | Tapped holes are called out as "M6 x 12 DEEP" with no drill depth. Should the drill depth (about 3 pitches deeper) be stated, or is it left to the shop? Built 2026-11-13: a stated drill depth is judged; a missing one is not a finding (`report_missing: false`) until PARI answers. | MC-004 |

## 4. Standing project questions

These are from `docs/01_discovery.md` §8 and are still open:
- O1 Who does the last point check today, and how.
- O2 The severity levels and their definitions.
- O3 Who writes and confirms the rulebook.
- O4 Which model providers may receive drawings, and in which regions.
- O5 Where the system runs: on a checker's machine or as a hosted service.
- O6 Which WP guidelines are in scope.
- O7 The false-alarm rate a checker will tolerate.
- O8 What `#` means in MATERIAL / SURFACE TREATMENT, and where the material is defined.
- O9 Whether `---` or REF NOTE in the HEAT TREATMENT field is accepted when the notes give the treatment.

## 5. Conventions behind rules parked as `needs_pari`

49 rules in `docs/rulebook/rule_mapping.csv` wait on one of these. Answering a group settles all its rules.

- **ISO or ASME practice?** Drafting standard stated (LY-06), datum on a centre line (MD-06), alphabetical datum
  order (NASA-108), surface texture symbols (NASA-119, WST-018, WST-019), unidirectional text (NASA-067, DSM-22,
  DTT-26), the envelope principle (DTT-58), position tolerancing on basic dimensions (NASA-125), basic-hole fits
  (WST-210), fit written with deviations (WST-211), third-angle projection (WST-016).
- **Lists only PARI has:** approved abbreviations (LY-11), glossary (NM-04), register of standards cited
  (NM-03), gauge capability (TL-15), WP profiles (TB-11, MF-12, MP-15, NM-09, NM-10, NM-11).
- **Lettering and language:** which languages are allowed on bilingual sheets (LY-12), upper case (NASA-066,
  HNF-12), abbreviation punctuation (HNF-10), unit symbols in capitals (HNF-60), upright text (HNF-65).
- **Template and practice:** material grade with its standard (MF-01), "UNLESS OTHERWISE SPECIFIED" heading
  (NASA-031), coatings in notes (NASA-021), one part per drawing (NASA-086), tabulated drawings (NASA-095),
  altered bought-out parts (HNF-07), used-on field (HNF-43), sheet orientation and title block size (WST-002,
  WST-008), pipe thread notation (WST-223), pin finishes (WST-232), brazing (WST-140), implied symmetry (MX-07),
  critical-to-function marking (TL-08), 5 mm grid, change balloons, weldment datums, balloon sizes, tooling studs
  (DSM-20, DSM-28, DSM-32, DSM-43, DSM-44).
