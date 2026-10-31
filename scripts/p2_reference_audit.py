"""P2 reference-data audit. No drawing evaluation, model calls or invented accuracy metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from drawing_intelligence.review.reference import load_reference
from drawing_intelligence.review.rulebook import load_rulebook
from drawing_intelligence.settings import PROJECT_ROOT

BASE_TABLES = {
    "materials",
    "plating_processes",
    "is919_fits",
    "is2102_general_tolerances",
    "iso_metric_threads",
}


def audit() -> dict:
    refs = load_reference()
    verified = []
    for name, table in refs.items():
        if name in BASE_TABLES - {"plating_processes"}:
            continue
        source = table.model_dump()["source"]
        path = PROJECT_ROOT / "data/client_set/WP Specific Guidelines" / source["document"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != source["sha256"]:
            raise ValueError(f"source content differs from the cited version: {name}")
        verified.append(name)
    heat = refs["material_heat_treatment"]
    stock = refs["raw_material_sizes_des11"]
    catalogue = refs["raw_material_catalogue"]
    statuses = json.loads((PROJECT_ROOT / "docs/reference/p2_reference_status.json").read_text())
    rulebook = load_rulebook()
    for row in statuses["rules"]:
        rulebook.get(row["rule_id"])
        if any(name not in refs for name in row["tables"]):
            raise ValueError(f"unknown reference table in coverage record: {row}")
    if len(statuses["rules"]) != 19 or len({r["rule_id"] for r in statuses["rules"]}) != 19:
        raise ValueError("P2 status record must cover all 19 rule IDs exactly once")
    return {
        "owner": "Zhetao Zhang",
        "deliverable": "cited reference tables, typed loaders and structure tests",
        "table_files_loaded": len(refs),
        "new_table_files": len(set(refs) - BASE_TABLES),
        "source_hashes_verified_for": verified,
        "des11": {
            "material_rows": len(heat.materials),
            "treatment_cells": sum(len(m.treatments) for m in heat.materials),
            "numeric_cells": sum(
                c.status == "tabulated" for m in heat.materials for c in m.treatments.values()
            ),
            "nil_cells": sum(c.status == "nil" for m in heat.materials for c in m.treatments.values()),
            "stock_material_rows": len(stock.materials),
            "stock_form_lists": sum(len(m.sizes_mm) for m in stock.materials),
            "market_size_entries": sum(len(s) for m in stock.materials for s in m.sizes_mm.values()),
            "source_anomalies": [a.model_dump() for a in stock.source_anomalies],
        },
        "stock_catalogue_2024": {
            "worksheets": len(catalogue.sheets),
            "nonempty_cells": sum(len(s.cells) for s in catalogue.sheets),
        },
        "reference_status_counts": dict(Counter(r["status"] for r in statuses["rules"])),
        "rules": statuses["rules"],
        "interpretation": "Reference-data readiness only. This does not assert drawing accuracy, "
        "implementation of the 19 checks, or completion of the separate fresh AI-reviewer evaluation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rules"}, indent=2))
