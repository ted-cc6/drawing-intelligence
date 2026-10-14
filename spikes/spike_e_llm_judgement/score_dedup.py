"""Deduplicated, labelled precision for Spike E (thinking OFF only), per the reviewer's labelling rules.

Findings are deduplicated to one per (base drawing, category, theme) - not per case x run - because one base
(e.g. B5) underlies several cases, so its pre-existing issues were otherwise counted many times. Each distinct
finding is then labelled by theme (fixed labels below) and precision is reported as a range:
- strict:  unclear counts as a false alarm
- lenient: unclear counts as a real issue
Out-of-scope themes (title-block/J3 text quality, and an understanding artefact) are reported separately and
excluded from the J5/J6 precision.

Run: python spikes/spike_e_llm_judgement/score_dedup.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict

from common import OUT, RESULTS
from score import expected, finding_matches_key

RUNS_FILE = OUT / "runs.jsonl"

# theme -> (label, scope). label in {real, unclear, false}; scope in {in, out}.
LABELS = {
    "PLANT": ("real", "in"),  # matched a planted error
    "A_junk_note": ("real", "out"),  # garbage note - J3, not J5/J6
    "B_ht_titleblock_vs_note": ("real", "in"),  # real consistency; severity Minor (model said Critical)
    "C_untoleranced_dia": ("unclear", "in"),  # IS 2102 general tol applies; "functional" is a guess
    "D_nonstandard_drill": ("false", "in"),  # Ø6.4/Ø8.4 are standard M6/M8 clearance holes
    "E_text_quality": ("real", "out"),  # misspelling / bad hardness string - J3
    "F_speculation": ("false", "in"),  # material/treatment speculation, no rule/evidence
    "G_gdt_symbol": ("unclear", "in"),
    "H_too_tight": ("false", "in"),  # "too tight" with no rule or functional evidence (sec 4.1)
    "Z1_bore_no_nominal": ("artefact", "out"),  # understanding dropped the Ø32 nominal; not a reviewer error
    "Z2_thread_relief_tapped": ("false", "in"),  # relief on an M5 tapped hole
    "Z_other": ("unclear", "in"),
}


def label_of(theme: str) -> tuple[str, str]:
    return ("real", "in") if theme.startswith("PLANT") else LABELS[theme]


def theme_of(f: dict) -> str:
    t = (f.get("reasoning", "") + " " + f.get("rule", "")).lower()
    ev = " ".join(f.get("evidence", [])).lower()
    if "yfyfgh" in t or "gibberish" in t:
        return "A_junk_note"
    if "heat_treatment" in t and ("---" in t or "n1" in t or "n5" in t or "note" in t):
        return "B_ht_titleblock_vs_note"
    if "nominal" in t and ("bore" in t or "d2" in ev or "+0.2" in t):
        return "Z1_bore_no_nominal"
    if "polyurethene" in t or "misspell" in t or "80u5" in t or "shore" in t:
        return "E_text_quality"
    if "standard" in t and ("drill" in t or "6.4" in t or "8.4" in t):
        return "D_nonstandard_drill"
    if ("relief" in t or "undercut" in t) and ("tap" in t or "m5" in t):
        return "Z2_thread_relief_tapped"
    if any(
        p in t
        for p in (
            "no tolerance",
            "without a tol",
            "no explicit tol",
            "carries no tol",
            "lacks a tol",
            "no fit",
        )
    ) and any(p in t for p in ("bore", "diameter", "⌀", "seat", "fit", "cylindrical")):
        return "C_untoleranced_dia"
    if "position tolerance" in t or "s6" in ev or "uncertain" in ev or "datum" in t:
        return "G_gdt_symbol"
    if (
        "too tight" in t
        or "tolerance band" in t
        or "general machining tolerance" in t
        or "general_tolerances" in ev
    ):
        return "H_too_tight"
    if any(
        p in t
        for p in (
            "izbp",
            "i.z.b.p",
            "passivation",
            "embrittle",
            "molded",
            "elastomer",
            "typically",
            "trivalent",
            "mild steel",
            "medium-carbon",
        )
    ):
        return "F_speculation"
    return "Z_other"


def main() -> None:
    runs = [json.loads(line) for line in RUNS_FILE.read_text(encoding="utf-8").splitlines()]
    off = [r for r in runs if r["setting"] == "off"]

    # distinct[(base, category, theme)] = representative row
    distinct: dict[tuple[str, str, str], dict] = {}
    for r in off:
        exp = expected(r["case"])
        base = exp["base"]
        keys = exp["keys"]
        for f in r["findings"]:
            # A matched planted error stays distinct per case (different planted errors can share a base and
            # category); only pre-existing issues collapse per base.
            matched = any(finding_matches_key(f, k) for k in keys)
            theme = f"PLANT:{r['case']}" if matched else theme_of(f)
            key = (base, f["category"], theme)
            distinct.setdefault(
                key,
                {
                    "base": base,
                    "category": f["category"],
                    "theme": theme,
                    "label": label_of(theme)[0],
                    "scope": label_of(theme)[1],
                    "example_case": r["case"],
                    "severity": f["severity"],
                    "reasoning": f.get("reasoning", "")[:120],
                },
            )

    rows = sorted(distinct.values(), key=lambda d: (d["scope"], d["theme"], d["base"]))
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "findings_labeled_dedup.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "scope",
                "label",
                "theme",
                "base",
                "category",
                "severity",
                "example_case",
                "reasoning",
            ],
        )
        w.writeheader()
        for d in rows:
            w.writerow({k: d[k] for k in w.fieldnames})

    # tally in-scope
    ins = [d for d in rows if d["scope"] == "in"]
    real = sum(1 for d in ins if d["label"] == "real")
    unclear = sum(1 for d in ins if d["label"] == "unclear")
    false = sum(1 for d in ins if d["label"] == "false")
    total = len(ins)
    strict = real / total if total else 0
    lenient = (real + unclear) / total if total else 0

    by_theme: dict[str, int] = defaultdict(int)
    for d in rows:
        by_theme[d["theme"]] += 1

    print("Deduplicated OFF findings (one per base x category x theme):")
    print(f"  in-scope J5/J6: {total}  (real={real}, unclear={unclear}, false={false})")
    print(f"  precision strict (unclear=false):  {strict:.0%}")
    print(f"  precision lenient (unclear=real):  {lenient:.0%}")
    print("  out-of-scope (reported separately):")
    for d in rows:
        if d["scope"] == "out":
            print(f"    [{d['label']:8s}] {d['theme']:24s} base={d['base']} ({d['example_case']})")
    print("\n  distinct findings by theme:")
    for th, n in sorted(by_theme.items()):
        lab, sc = label_of(th)
        print(f"    {th:26s} n={n}  label={lab:8s} scope={sc}")

    with (RESULTS / "precision_dedup.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["in_scope_distinct", total])
        w.writerow(["real", real])
        w.writerow(["unclear", unclear])
        w.writerow(["false", false])
        w.writerow(["precision_strict", f"{strict:.2f}"])
        w.writerow(["precision_lenient", f"{lenient:.2f}"])


if __name__ == "__main__":
    main()
