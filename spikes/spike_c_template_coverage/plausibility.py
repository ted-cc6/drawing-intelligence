"""Grade the title-block field values in out/coverage.csv: real / placeholder / missing / implausible ($0).

Run: python spikes/spike_c_template_coverage/plausibility.py
Reads out/coverage.csv (no re-extraction); writes results/field_plausibility.csv and prints the breakdown.

Why: the proxy in title_block.py finds a cell *value*, but a found value is not a real one. Material is the
placeholder "#" on most sheets; scale is sometimes truncated ("1 :"); the number is garbage ("B", "T+S") on a
few variant blocks. This pass classifies each key field so the findings separate "a cell value was found" from
"a usable value was read".

Grades:
- missing:     empty (the proxy found nothing).
- placeholder: a fill-in-later marker - "#", "-", "--", "---", "NA", "N/A", "NONE".
- implausible: present but fails a field-specific shape check (see below).
- real:        present, not a placeholder, passes the shape check.

Shape checks:
- scale:       d+(.d+)? : d+(.d+)?  (so "1 : 1" and "1.5 : 1" pass; "1 :" fails).
- sheet_size:  A0..A9.
- number:      looks like a drawing number (letters then >= 2 digits then alnum, len >= 8). Extra check:
               when the file name itself looks like a part code, the number must be a prefix of it. Many
               client files use a descriptive name instead (like the 4 samples), so the prefix check is
               skipped there and only the shape check applies.
- material/title: no format; real unless placeholder/missing.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
COV = HERE / "out" / "coverage.csv"
OUT = HERE / "results" / "field_plausibility.csv"

FIELDS = ("number", "title", "material", "scale", "sheet_size")
GRADES = ("real", "placeholder", "missing", "implausible")
COL = {  # proxy field -> coverage.csv column
    "number": "tb_number",
    "title": "tb_title",
    "material": "tb_material",
    "scale": "tb_scale",
    "sheet_size": "tb_sheet_size",
}

SCALE_RE = re.compile(r"\d+(\.\d+)?\s*:\s*\d+(\.\d+)?")
SHEET_RE = re.compile(r"A\d")
CODE_RE = re.compile(r"[A-Z]{1,4}\d{2}[A-Z0-9]{3,}")  # a drawing-number / part-code shape


def _ph(value: str) -> bool:
    return re.sub(r"[.\s]", "", value).upper() in {"#", "-", "--", "---", "NA", "N/A", "NONE"}


def variant_of(labels: str) -> str:
    n = int(labels) if str(labels).isdigit() else 0
    if n >= 16:
        return "standard(16)"
    if n >= 12:
        return "variant(12-13)"
    return "other(<12)"


def grade(field: str, value: str, file: str) -> str:
    v = (value or "").strip()
    if not v:
        return "missing"
    if _ph(v):
        return "placeholder"
    if field == "scale":
        return "real" if SCALE_RE.fullmatch(v) else "implausible"
    if field == "sheet_size":
        return "real" if SHEET_RE.fullmatch(v.upper()) else "implausible"
    if field == "number":
        compact = re.sub(r"\s", "", v).upper()
        if not CODE_RE.fullmatch(compact) or len(compact) < 8:
            return "implausible"
        stem = re.sub(r"\s", "", Path(file).stem).upper()
        if CODE_RE.fullmatch(stem) and not stem.startswith(compact):
            return "implausible"  # file name is a part code but disagrees with the number read
        return "real"
    return "real"  # material, title: real unless placeholder/missing


def tally(rows: list[dict], keyfn) -> dict[tuple[str, str], dict[str, int]]:
    out: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: dict.fromkeys(GRADES, 0))
    for r in rows:
        if r["error_type"]:
            continue
        group = keyfn(r)
        for field in FIELDS:
            out[(group, field)][grade(field, r[COL[field]], r["file"])] += 1
    return out


def rows_for(scope: str, tallied: dict[tuple[str, str], dict[str, int]]) -> list[dict]:
    out = []
    for (group, field), g in sorted(tallied.items()):
        total = sum(g.values())
        out.append(
            {
                "scope": scope,
                "group": group,
                "field": field,
                "total": total,
                **g,
                "real_pct": f"{100 * g['real'] / total:.1f}%" if total else "-",
            }
        )
    return out


def main() -> None:
    with COV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    out_rows = []
    out_rows += rows_for("all", tally(rows, lambda r: "all"))
    out_rows += rows_for("family", tally(rows, lambda r: r["family"]))
    out_rows += rows_for("variant", tally(rows, lambda r: variant_of(r["tb_labels_found"])))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = ["scope", "group", "field", "total", *GRADES, "real_pct"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    head = f"{'scope':8s} {'group':16s} {'field':11s} {'tot':>5s} "
    print(head + f"{'real':>5s} {'plc':>5s} {'miss':>5s} {'impl':>5s} {'real%':>7s}")
    for r in out_rows:
        print(
            f"{r['scope']:8s} {r['group']:16s} {r['field']:11s} {r['total']:5d} "
            f"{r['real']:5d} {r['placeholder']:5d} {r['missing']:5d} "
            f"{r['implausible']:5d} {r['real_pct']:>7s}"
        )
    print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
