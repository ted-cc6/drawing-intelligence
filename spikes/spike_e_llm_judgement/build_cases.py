"""Build the Spike E test set: one planted change per case, plus clean and near-miss controls ($0, no LLM).

Each case folder gets base.json (the unmodified base used), case.json (the input the reviewer reads) and
expected.json (the answer key: category, evidence ids, severity, the rule and its citation). Answer keys are
written here, BEFORE any model runs, and must not be edited after seeing model output.

Run: python spikes/spike_e_llm_judgement/build_cases.py
Every case.json is validated against the real DrawingKnowledge schema so the planted edits stay well-formed.
"""

from __future__ import annotations

import copy

from common import BASES, CASES, read_json, write_json

from drawing_intelligence.schemas import DrawingKnowledge
from drawing_intelligence.schemas.knowledge import Dimension, Feature

# Allowed enum values in the current schema. Some saved baseline understandings predate the schema tightening
# and carry types like "distance"/"thickness"; coerce those to "other" so a reused base is valid input.
# (Recorded as a finding: the saved baselines do not all conform to the current schema.)
_FEATURE_TYPES = set(Feature.model_fields["type"].annotation.__args__)
_DIM_TYPES = set(Dimension.model_fields["type"].annotation.__args__)


def normalize(k: dict) -> dict:
    for f in k["features"]:
        if f["type"] not in _FEATURE_TYPES:
            f["type"] = "other"
    for d in k["dimensions"]:
        if d["type"] not in _DIM_TYPES:
            d["type"] = "other"
    return k


# --- citations (read 2026-10-13) -------------------------------------------------------------------------
G = {
    "DES11": "PARI PRD-GD-DES-11 (client guideline, WP Specific Guidelines/), read 2026-10-13",
    "DES12": "PARI PRD-GD-DES-12 (client guideline, WP Specific Guidelines/), read 2026-10-13",
    "US51_deep": "US-5.1 AC1 (01_discovery.md): hole depth > 10 x diameter -> warning",
    "US51_thread": "US-5.1 AC2 (01_discovery.md): thread to a shoulder without undercut -> warning",
    "US52_stock": "US-5.2 + DES-11 p.2 standard round-bar stock list (10,16,25,30,32,36,40,42,45,50,...)",
    "US61_note": "US-6.1 AC1 (01_discovery.md): a referenced heat-treatment note must exist, else fail",
    "US61_pair": "US-6.1 AC2 + DES-11: material paired with a treatment the guideline does not allow",
    "US62_fit": "US-6.2 AC1 (01_discovery.md): a fit/functional diameter with no tolerance -> warning",
    "DFM_corner": "DFM: a milling cutter is cylindrical, so the smallest internal radius = the cutter "
    "radius; a zero-radius internal corner cannot be milled. "
    "https://jlccnc.com/help/article/CNC-Machining-Design-Guideline , read 2026-10-13",
    "DFM_tol": "ISO 2768-1 general tolerance, fine class 6-30 mm = +/-0.1 mm; +/-0.003 mm is far below that "
    "and below normal milling (needs grinding/lapping). "
    "https://www.xometry.com/resources/certifications/iso-2768 , read 2026-10-13",
}


def new_dim(did: str, text: str, value: float, dtype: str, feature_id: str) -> dict:
    return {
        "id": did,
        "text": text,
        "value": value,
        "unit": "mm",
        "tolerance": None,
        "type": dtype,
        "is_reference": False,
        "view_id": None,
        "feature_id": feature_id,
        "source": "pdf_text",
        "bbox": None,
    }


def feat(k: dict, fid: str) -> dict:
    return next(f for f in k["features"] if f["id"] == fid)


def dim(k: dict, did: str) -> dict:
    return next(d for d in k["dimensions"] if d["id"] == did)


def note(k: dict, nid: str) -> dict:
    return next(n for n in k["notes"] if n["id"] == nid)


# --- planted edits: each takes the base dict and mutates it in place -------------------------------------
def j5_1_deep_hole(k: dict) -> None:  # B5
    k["dimensions"] += [
        new_dim("D14", "⌀ 4.2", 4.2, "diameter", "F4"),
        new_dim("D15", "50", 50.0, "linear", "F4"),
    ]
    f = feat(k, "F4")
    f["type"] = "hole"
    f["description"] = "Drilled hole Ø4.2, 50 deep (for M5 tap)"
    f["dimension_ids"] = ["D14", "D15"]


def j5_2_thread_relief(k: dict) -> None:  # B5
    k["features"].append(
        {
            "id": "F7",
            "type": "thread",
            "description": "External thread M20 running up to the shoulder, no undercut/relief groove",
            "dimension_ids": ["D6"],
            "view_id": None,
        }
    )


def j5_3_sharp_corner(k: dict) -> None:  # B1
    dim(k, "D7")["text"] = "R 0"
    dim(k, "D7")["value"] = 0.0
    feat(k, "F7")["description"] = "Zero-radius (sharp) internal corner at left top step"


def j5_4_tight_tol(k: dict) -> None:  # B4
    d = dim(k, "D1")
    d["text"] = "15 ±0.003"
    d["tolerance"] = "±0.003"


def j5_5_raw_stock(k: dict) -> None:  # B6
    k["notes"].append({"id": "N10", "text": "RAW MATERIAL : Ø66 BLACK ROUND BAR", "category": "material"})


def j6_1_mat_ht(k: dict) -> None:  # B5 (20MnCr5 is case-hardening only)
    note(k, "N1")["text"] = "HEAT TREATMENT NOTE:- 1) TO BE THROUGH HARDENED UPTO 50 HRC."


def j6_2_dangling_note(k: dict) -> None:  # B2 (C-45)
    k["drawing"]["heat_treatment"] = "REF NOTE"
    k["notes"] = [n for n in k["notes"] if n["id"] != "N1"]  # the HT note it points to


def j6_3_ht_out_of_range(k: dict) -> None:  # B6 (C45 through-hardening guideline is 24-32 HRC)
    note(k, "N5")["text"] = "HEAT TREATMENT :- 1) TO BE THROUGH HARDENED UPTO 55 HRC."


def j6_4_missing_fit(k: dict) -> None:  # B5 (Ø12 H7 bearing bore loses its fit)
    d = dim(k, "D3")
    d["text"] = "⌀ 12"
    d["tolerance"] = None


def j6_5_chrome_soft(k: dict) -> None:  # B1 (M.S., unhardened)
    k["drawing"]["surface_treatment"] = "HARD CHROME PLATING"


def nm_1_deep_ok(k: dict) -> None:  # B5: 8:1, within the 10x limit -> no finding
    k["dimensions"] += [
        new_dim("D14", "⌀ 5", 5.0, "diameter", "F4"),
        new_dim("D15", "40", 40.0, "linear", "F4"),
    ]
    f = feat(k, "F4")
    f["type"] = "hole"
    f["description"] = "Drilled hole Ø5, 40 deep"
    f["dimension_ids"] = ["D14", "D15"]


# --- case registry: (case_id, base_tag, edit_fn|None, answer-key fields) ----------------------------------
def key(category: str, evidence: list[str], severity: str, desc: str, rule: str) -> dict:
    return {
        "category": category,
        "evidence": evidence,
        "severity": severity,
        "description": desc,
        "rule": rule,
    }


PLANTED = [
    (
        "J5-1_deep_hole",
        "B5_pin_sleeve",
        j5_1_deep_hole,
        key(
            "manufacturability",
            ["F4", "D14", "D15"],
            "Major",
            "Blind hole depth 50 / Ø4.2 = 11.9x diameter, far over the 10x limit",
            G["US51_deep"],
        ),
    ),
    (
        "J5-2_thread_relief",
        "B5_pin_sleeve",
        j5_2_thread_relief,
        key(
            "manufacturability",
            ["F7"],
            "Major",
            "External thread runs to a shoulder with no undercut/relief groove",
            G["US51_thread"],
        ),
    ),
    (
        "J5-3_sharp_corner",
        "B1_cam_plate",
        j5_3_sharp_corner,
        key(
            "manufacturability",
            ["F7", "D7"],
            "Minor",
            "Zero-radius internal corner cannot be cut by a round tool",
            G["DFM_corner"],
        ),
    ),
    (
        "J5-4_tight_tol",
        "B4_pipe_clamp_block",
        j5_4_tight_tol,
        key(
            "manufacturability",
            ["D1"],
            "Major",
            "±0.003 mm on a milled block is below normal machining capability",
            G["DFM_tol"],
        ),
    ),
    (
        "J5-5_raw_stock",
        "B6_coupling_spacer",
        j5_5_raw_stock,
        key(
            "manufacturability",
            ["D1", "N10"],
            "Minor",
            "Ø66 bar is not a standard stock size and leaves no machining allowance on Ø66",
            G["US52_stock"],
        ),
    ),
    (
        "J6-1_mat_ht",
        "B5_pin_sleeve",
        j6_1_mat_ht,
        key(
            "design_intent",
            ["material", "N1"],
            "Critical",
            "20MnCr5 is a case-hardening steel; through-hardening to 50 HRC does not suit it",
            G["US61_pair"],
        ),
    ),
    (
        "J6-2_dangling_note",
        "B2_cylinder_rod",
        j6_2_dangling_note,
        key(
            "design_intent",
            ["heat_treatment"],
            "Critical",
            'Heat treatment says "REF NOTE" but no heat-treatment note exists',
            G["US61_note"],
        ),
    ),
    (
        "J6-3_ht_out_of_range",
        "B6_coupling_spacer",
        j6_3_ht_out_of_range,
        key(
            "design_intent",
            ["material", "N5"],
            "Major",
            "C45 through-hardening per DES-11 is 24-32 HRC; 55 HRC is out of range",
            G["US61_pair"],
        ),
    ),
    (
        "J6-4_missing_fit",
        "B5_pin_sleeve",
        j6_4_missing_fit,
        key(
            "design_intent", ["D3"], "Major", "Ø12 bearing bore has no tolerance or fit class", G["US62_fit"]
        ),
    ),
    (
        "J6-5_chrome_soft",
        "B1_cam_plate",
        j6_5_chrome_soft,
        key(
            "design_intent",
            ["surface_treatment", "heat_treatment"],
            "Major",
            "Hard chrome needs a hardened surface (>=45 HRC); this part (M.S.) is not hardened",
            G["DES12"],
        ),
    ),
]

CLEAN = [
    ("C1_clean_cam_plate", "B1_cam_plate"),
    ("C2_clean_cylinder_rod", "B2_cylinder_rod"),
    ("C3_clean_pipe_clamp_block", "B4_pipe_clamp_block"),
    ("C4_clean_hose_clamp", "B3_hose_clamp"),
]

NEAR_MISS = [
    (
        "NM-1_deep_but_ok",
        "B5_pin_sleeve",
        nm_1_deep_ok,
        "Hole 40 / Ø5 = 8x diameter, within the 10x limit - must NOT be flagged",
    ),
    (
        "NM-2_correct_ht",
        "B5_pin_sleeve",
        None,
        "20MnCr5 case-hardened 55-60 HRC is correct per DES-11 - must NOT be flagged",
    ),
]


def validate(case_id: str, k: dict) -> None:
    DrawingKnowledge.model_validate(k)  # raises if the planted edit broke the schema


def main() -> None:
    manifest = []
    for case_id, base_tag, edit, ans in PLANTED:
        base = normalize(read_json(BASES / f"{base_tag}.json"))
        case = copy.deepcopy(base)
        edit(case)
        validate(case_id, case)
        d = CASES / case_id
        write_json(d / "base.json", base)
        write_json(d / "case.json", case)
        write_json(d / "expected.json", {"kind": "planted", "base": base_tag, "keys": [ans]})
        manifest.append({"case": case_id, "kind": "planted", "base": base_tag, "n_keys": 1})

    for case_id, base_tag in CLEAN:
        base = normalize(read_json(BASES / f"{base_tag}.json"))
        validate(case_id, base)
        d = CASES / case_id
        write_json(d / "base.json", base)
        write_json(d / "case.json", base)
        write_json(d / "expected.json", {"kind": "clean", "base": base_tag, "keys": []})
        manifest.append({"case": case_id, "kind": "clean", "base": base_tag, "n_keys": 0})

    for case_id, base_tag, edit, why in NEAR_MISS:
        base = normalize(read_json(BASES / f"{base_tag}.json"))
        case = copy.deepcopy(base)
        if edit:
            edit(case)
        validate(case_id, case)
        d = CASES / case_id
        write_json(d / "base.json", base)
        write_json(d / "case.json", case)
        write_json(d / "expected.json", {"kind": "near_miss", "base": base_tag, "keys": [], "note": why})
        manifest.append({"case": case_id, "kind": "near_miss", "base": base_tag, "n_keys": 0})

    write_json(CASES / "manifest.json", manifest)
    print(f"built {len(manifest)} cases in {CASES}")
    for m in manifest:
        print(f"  {m['case']:28s} {m['kind']:10s} base={m['base']}")


if __name__ == "__main__":
    main()
