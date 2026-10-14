"""Score the Spike E reviewer runs against the answer keys ($0, reads out/runs.jsonl + cases/).

Metrics per model setting (thinking off / on):
- recall:            planted keys matched / 10
- precision:         matched findings / all findings (needs the unmatched-finding labels, see below)
- false alarms:      findings per clean control
- near-miss errors:  findings on the 2 near-miss controls (should be 0)
- invalid citations: evidence ids not present in that case's input JSON
- stability:         fraction of findings that appear in both runs of a case (by category+evidence)
- cost / latency:    per call

Matching: a finding matches a key iff the category matches AND the evidence shares at least one expected id.
D/F/N/S ids match exactly; title-block field names match as normalised substrings (e.g. "drawing.material"
matches key "material").

Unmatched findings: this writes results/unmatched_findings.csv with a proposed label (real / false_alarm /
unclear) for every finding that did not match a key. A human confirms those labels; precision is then computed
from results/unmatched_labeled.csv if present, else from the proposed labels (and flagged as provisional).
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict

from common import CASES, OUT, RESULTS, read_json

RUNS_FILE = OUT / "runs.jsonl"
SETTINGS = ("off", "on")


def load_runs() -> list[dict]:
    return [json.loads(line) for line in RUNS_FILE.read_text(encoding="utf-8").splitlines()]


def ids_in_case(case: str) -> set[str]:
    """Every id / field name a finding could legitimately cite for this case."""
    k = read_json(CASES / case / "case.json")
    ids = {x["id"] for group in ("dimensions", "features", "symbols", "notes") for x in k[group]}
    ids |= set(k["drawing"])  # title-block field names
    ids |= {f"drawing.{f}" for f in k["drawing"]}
    return ids


def norm_ev(e: str) -> str:
    return e.strip().lower().removeprefix("drawing.")


def ev_match(finding_ev: list[str], key_ev: list[str]) -> bool:
    fe = {norm_ev(e) for e in finding_ev}
    for want in key_ev:
        w = norm_ev(want)
        if w in fe:
            return True
        # title-block field names (non D/F/N/S ids) match as substrings either way
        if not w[:1].isupper() and not w[0].isdigit() and any(w in e or e in w for e in fe):
            return True
    return False


def expected(case: str) -> dict:
    return read_json(CASES / case / "expected.json")


def finding_matches_key(f: dict, key: dict) -> bool:
    return f["category"] == key["category"] and ev_match(f.get("evidence", []), key["evidence"])


def score() -> None:
    runs = load_runs()
    manifest = read_json(CASES / "manifest.json")
    kind = {m["case"]: m["kind"] for m in manifest}

    per_setting: dict[str, dict] = {
        s: {
            "keys_total": 0,
            "keys_hit": 0,
            "findings_total": 0,
            "findings_matched": 0,
            "clean_findings": 0,
            "clean_cases": 0,
            "nearmiss_findings": 0,
            "invalid_citations": 0,
            "cost": 0.0,
            "latency": 0.0,
            "calls": 0,
            "invalid_json": 0,
        }
        for s in SETTINGS
    }
    unmatched_rows: list[dict] = []
    # stability bookkeeping: {(case, setting): {run: set(category|sorted-evidence)}}
    fsets: dict[tuple[str, str], dict[int, set[str]]] = defaultdict(dict)

    for r in runs:
        s = r["setting"]
        if s not in per_setting:
            continue
        agg = per_setting[s]
        agg["calls"] += 1
        agg["cost"] += r["cost_usd"]
        agg["latency"] += r["latency_s"]
        agg["invalid_json"] += 0 if r["valid"] else 1
        case = r["case"]
        exp = expected(case)
        valid_ids = ids_in_case(case)
        keys = exp["keys"]

        # recall is counted once per (case, run) over that case's keys
        for key in keys:
            agg["keys_total"] += 1
            if any(finding_matches_key(f, key) for f in r["findings"]):
                agg["keys_hit"] += 1

        fset = set()
        for f in r["findings"]:
            agg["findings_total"] += 1
            fset.add(f["category"] + "|" + ",".join(sorted(norm_ev(e) for e in f.get("evidence", []))))
            # invalid citations
            bad = [e for e in f.get("evidence", []) if norm_ev(e) not in {norm_ev(x) for x in valid_ids}]
            agg["invalid_citations"] += len(bad)
            matched_key = next((k for k in keys if finding_matches_key(f, k)), None)
            if matched_key is not None:
                agg["findings_matched"] += 1
            else:
                if kind[case] == "clean":
                    agg["clean_findings"] += 1
                elif kind[case] == "near_miss":
                    agg["nearmiss_findings"] += 1
                unmatched_rows.append(
                    {
                        "case": case,
                        "kind": kind[case],
                        "setting": s,
                        "run": r["run"],
                        "category": f["category"],
                        "severity": f["severity"],
                        "evidence": " ".join(f.get("evidence", [])),
                        "rule": f.get("rule", "")[:80],
                        "reasoning": f.get("reasoning", "")[:160],
                        "invalid_citation": bool(bad),
                        "proposed_label": _propose(kind[case], bool(bad)),
                        "final_label": "",
                    }
                )
        fsets[(case, s)][r["run"]] = fset
        if kind[case] == "clean":
            agg["clean_cases"] += 1

    # stability: findings present in BOTH runs / findings present in either (per case,setting), averaged
    stability: dict[str, list[float]] = {s: [] for s in SETTINGS}
    for (_case, s), byrun in fsets.items():
        if len(byrun) < 2:
            continue
        a, b = byrun.get(1, set()), byrun.get(2, set())
        union = a | b
        if union:
            stability[s].append(len(a & b) / len(union))

    _write_summary(per_setting, stability)
    _write_unmatched(unmatched_rows)


def _propose(kind: str, invalid: bool) -> str:
    if invalid:
        return "false_alarm"
    if kind == "clean":
        return "false_alarm"
    if kind == "near_miss":
        return "false_alarm"
    return "unclear"  # extra finding on a planted case: a human decides real vs false


def _write_summary(per_setting: dict, stability: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cols = [
        "setting",
        "recall",
        "keys_hit",
        "keys_total",
        "precision_provisional",
        "findings_matched",
        "findings_total",
        "false_alarms_per_clean",
        "nearmiss_findings",
        "invalid_citations",
        "stability",
        "avg_cost_usd",
        "avg_latency_s",
        "invalid_json",
        "calls",
    ]
    rows = []
    for s, a in per_setting.items():
        recall = a["keys_hit"] / a["keys_total"] if a["keys_total"] else 0
        precision = a["findings_matched"] / a["findings_total"] if a["findings_total"] else 0
        stab = sum(stability[s]) / len(stability[s]) if stability[s] else 0
        rows.append(
            {
                "setting": s,
                "recall": f"{recall:.0%}",
                "keys_hit": a["keys_hit"],
                "keys_total": a["keys_total"],
                "precision_provisional": f"{precision:.0%}",
                "findings_matched": a["findings_matched"],
                "findings_total": a["findings_total"],
                "false_alarms_per_clean": round(a["clean_findings"] / max(a["clean_cases"], 1), 2),
                "nearmiss_findings": a["nearmiss_findings"],
                "invalid_citations": a["invalid_citations"],
                "stability": f"{stab:.0%}",
                "avg_cost_usd": round(a["cost"] / max(a["calls"], 1), 4),
                "avg_latency_s": round(a["latency"] / max(a["calls"], 1), 1),
                "invalid_json": a["invalid_json"],
                "calls": a["calls"],
            }
        )
    with (RESULTS / "scores_by_setting.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("scores_by_setting.csv:")
    for r in rows:
        print(
            f"  {r['setting']:3s} recall={r['recall']:>4s} ({r['keys_hit']}/{r['keys_total']}) "
            f"prec*={r['precision_provisional']:>4s} FA/clean={r['false_alarms_per_clean']} "
            f"nearmiss={r['nearmiss_findings']} invalid_cite={r['invalid_citations']} "
            f"stab={r['stability']:>4s} ${r['avg_cost_usd']} {r['avg_latency_s']}s"
        )


def _write_unmatched(rows: list[dict]) -> None:
    out = RESULTS / "unmatched_findings.csv"
    cols = [
        "case",
        "kind",
        "setting",
        "run",
        "category",
        "severity",
        "evidence",
        "rule",
        "reasoning",
        "invalid_citation",
        "proposed_label",
        "final_label",
    ]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} unmatched findings -> {out} (label 'final_label' then re-run score.py)")


if __name__ == "__main__":
    score()
