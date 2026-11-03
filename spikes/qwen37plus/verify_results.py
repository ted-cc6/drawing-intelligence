"""Offline integrity and completion checks for the published, redacted Plus audit evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "data/eval/heldout/2026-11-03_qwen37plus_virginia_global_same24"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_file(data: bytes, expected: str, name: str) -> None:
    if digest(data) != expected:
        raise ValueError(f"Published evidence changed: {name}")


def verify(result: Path = RESULT) -> dict:
    mapping = json.loads((result / "provenance/redaction_map.json").read_text(encoding="utf-8"))
    for name, record in mapping.items():
        validate_file((result / name).read_bytes(), record["published_sha256"], name)
    state = json.loads((result / "full/run_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((result / "full/manifest.json").read_text(encoding="utf-8"))
    # The original hash intentionally points to the unredacted source, not a falsely resumable ledger.
    if state["manifest_sha256"] != mapping["full/manifest.json"]["original_sha256"]:
        raise ValueError("Original manifest linkage differs")
    rows_hash = digest(json.dumps(state["rows"], sort_keys=True, ensure_ascii=False).encode())
    if state["rows_sha256"] != rows_hash:
        raise ValueError("Prediction rows differ")
    latest = {a["drawing"]: a for a in state["attempts"]}
    if manifest["n"] != 24 or len(latest) != 24 or not state["complete"]:
        raise ValueError("Expected a complete 24-drawing run")
    if set(latest) != {e["path"] for e in manifest["drawings"]}:
        raise ValueError("Attempt sample differs")
    calls = []
    for attempt in latest.values():
        if attempt["status"] != "ok" or attempt["errors"]:
            raise ValueError("A drawing is not successful")
        reviews = [c for c in attempt["calls"] if c["node"].startswith("review:")]
        if {c["node"] for c in reviews} != {
            "review:drawing_practice",
            "review:manufacturability",
            "review:design_intent",
        } or len(reviews) != 3:
            raise ValueError("Missing reviewer call")
        for call in reviews:
            if call["status"] != "ok" or call["model"] != "qwen3.7-plus":
                raise ValueError("Wrong model or failed reviewer")
        for reviewer in ("drawing_practice", "manufacturability", "design_intent"):
            output = json.loads(
                (result / "full" / attempt["report"] / (reviewer + ".json")).read_text(encoding="utf-8")
            )
            if output.get("error"):
                raise ValueError("Reviewer report contains an error")
        calls.extend(reviews)
    by_source = Counter(row["checked_by"] for row in state["rows"])
    summary = json.loads((result / "summary.json").read_text(encoding="utf-8"))
    if len(state["rows"]) != summary["findings"] or dict(by_source) != summary["by_source"]:
        raise ValueError("Summary differs from raw rows")
    if any(row["label"] or row["labelled_by"] for row in state["rows"]):
        raise ValueError("Original unlabelled rows were overwritten")
    if len(calls) != 72 or sum(not c["cached"] for c in calls) != 63:
        raise ValueError("Review call counts differ")
    return summary


if __name__ == "__main__":
    summary = verify()
    print(f"PASS: 24/24, 72 reviewer calls, {summary['findings']} findings. Human validation pending.")
