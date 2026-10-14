"""Summarise out/coverage.csv into the small committed tables in results/ ($0, reads the CSV only).

Run: python spikes/spike_c_template_coverage/summarise.py
Writes results/summary_by_family_size.csv and results/failure_reasons.csv, and prints the headline rates.

Definitions used here:
- crash:            an exception was caught (error_type set).
- no_dimension:     extraction ran but found zero dimensions (question 2's "usable text layer").
- no_text_layer:    the PDF text layer is empty (words == 0) - a scanned/raster sheet, the worst case.
- tb_fail:          the title-block proxy status is not "ok" (empty / no_template / missing_values).
- size_mismatch:    page ISO size disagrees with the sheet size printed in the title block.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
COV = HERE / "out" / "coverage.csv"
SUMMARY = HERE / "results" / "summary_by_family_size.csv"
REASONS = HERE / "results" / "failure_reasons.csv"


def load() -> list[dict]:
    with COV.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _i(row: dict, key: str) -> int:
    v = row.get(key, "")
    return int(v) if str(v).strip() not in ("", "None") else 0


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "-"


def summarise(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["family"], r["iso_size"]), []).append(r)

    out = []
    for (family, iso), rs in sorted(groups.items()):
        n = len(rs)
        ok = [r for r in rs if not r["error_type"]]
        crashes = n - len(ok)
        no_dim = sum(1 for r in ok if _i(r, "dims") == 0)
        no_text = sum(1 for r in ok if _i(r, "words") == 0)
        tb_fail = sum(1 for r in ok if r["tb_status"] != "ok")
        mismatch = sum(1 for r in ok if _i(r, "size_mismatch"))
        dims = [_i(r, "dims") for r in ok]
        notes = [_i(r, "notes") for r in ok]
        out.append(
            {
                "family": family,
                "iso_size": iso,
                "n": n,
                "crash": crashes,
                "crash_rate": pct(crashes, n),
                "no_dimension": no_dim,
                "no_dim_rate": pct(no_dim, len(ok)),
                "no_text_layer": no_text,
                "tb_fail": tb_fail,
                "tb_fail_rate": pct(tb_fail, len(ok)),
                "size_mismatch": mismatch,
                "median_dims": int(statistics.median(dims)) if dims else 0,
                "median_notes": int(statistics.median(notes)) if notes else 0,
            }
        )
    return out


def totals_row(rows: list[dict]) -> dict:
    n = len(rows)
    ok = [r for r in rows if not r["error_type"]]
    return {
        "family": "ALL",
        "iso_size": "all",
        "n": n,
        "crash": n - len(ok),
        "crash_rate": pct(n - len(ok), n),
        "no_dimension": sum(1 for r in ok if _i(r, "dims") == 0),
        "no_dim_rate": pct(sum(1 for r in ok if _i(r, "dims") == 0), len(ok)),
        "no_text_layer": sum(1 for r in ok if _i(r, "words") == 0),
        "tb_fail": sum(1 for r in ok if r["tb_status"] != "ok"),
        "tb_fail_rate": pct(sum(1 for r in ok if r["tb_status"] != "ok"), len(ok)),
        "size_mismatch": sum(1 for r in ok if _i(r, "size_mismatch")),
        "median_dims": int(statistics.median([_i(r, "dims") for r in ok])) if ok else 0,
        "median_notes": int(statistics.median([_i(r, "notes") for r in ok])) if ok else 0,
    }


def failure_reasons(rows: list[dict]) -> list[dict]:
    """Every file that fails at least one check, grouped by a single reason label."""
    reasons: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for r in rows:
        if r["error_type"]:
            reason = f"crash:{r['error_type']}"
        elif _i(r, "words") == 0:
            reason = "no_text_layer (scanned?)"
        elif _i(r, "dims") == 0:
            reason = "no_dimension_found"
        elif r["tb_status"] == "empty":
            reason = "title_block_empty"
        elif r["tb_status"] == "no_template":
            reason = "title_block_other_template"
        elif r["tb_status"] == "missing_values":
            reason = "title_block_missing_values"
        elif _i(r, "size_mismatch"):
            reason = "page_size_vs_title_block_mismatch"
        else:
            continue
        reasons[reason] += 1
        examples.setdefault(reason, f"{r['family']}/{r['file']}")
    return [{"reason": k, "files": v, "example": examples[k]} for k, v in reasons.most_common()]


def main() -> None:
    rows = load()
    summary = summarise(rows)
    summary.append(totals_row(rows))
    reasons = failure_reasons(rows)

    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    with REASONS.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["reason", "files", "example"])
        w.writeheader()
        w.writerows(reasons)

    print(f"{'family':10s} {'size':13s} {'n':>5s} {'crash':>6s} {'noDim':>7s} {'tbFail':>7s} {'mism':>5s}")
    for s in summary:
        print(
            f"{s['family']:10s} {s['iso_size']:13s} {s['n']:5d} {s['crash_rate']:>6s} "
            f"{s['no_dim_rate']:>7s} {s['tb_fail_rate']:>7s} {s['size_mismatch']:>5d}"
        )
    print("\nfailure reasons:")
    for r in reasons:
        print(f"  {r['files']:4d}  {r['reason']:35s} e.g. {r['example']}")
    print(f"\nwrote {SUMMARY.name}, {REASONS.name}")


if __name__ == "__main__":
    main()
