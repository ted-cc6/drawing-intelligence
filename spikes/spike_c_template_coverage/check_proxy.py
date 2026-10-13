"""Check the title-block proxy against the draft truth for the 4 samples before trusting it.

Run: python spikes/spike_c_template_coverage/check_proxy.py
(or `uv run python ...`). Reads data/labels/title_block_truth.json; writes nothing.

The proxy must reproduce the five key values (number, title, material, scale, sheet_size) for each of
the 4 samples, after normalising case and spacing. Prints a PASS/FAIL line per field so mismatches are
easy to see. Note: the truth file is a draft (`_verified: false`), so this checks agreement with a draft.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

from title_block import KEY_FIELDS, read_title_block

from drawing_intelligence.extraction.pipeline import extract_pdf

ROOT = Path(__file__).resolve().parents[2] / "data"
RAW = ROOT / "raw"
TRUTH = ROOT / "labels" / "title_block_truth.json"

# proxy field -> truth field
TRUTH_KEY = {
    "number": "number",
    "title": "title",
    "material": "material",
    "scale": "scale",
    "sheet_size": "sheet_size",
}


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


def main() -> None:
    warnings.filterwarnings("ignore")
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))

    total = ok = 0
    for pdf in sorted(RAW.glob("*.pdf")):
        stem = pdf.stem.strip()
        expected = truth.get(stem) or truth.get(pdf.stem)
        if expected is None:
            print(f"! no truth row for {stem!r}")
            continue
        read = read_title_block(extract_pdf(pdf).pages[0].title_block_text)
        print(f"\n{stem}  [status={read.status}, labels={read.labels_found}/{read.labels_total}]")
        for fld in KEY_FIELDS:
            got = _norm(read.values.get(fld))
            want = _norm(expected.get(TRUTH_KEY[fld]))
            hit = got == want
            total += 1
            ok += hit
            print(f"  {'PASS' if hit else 'FAIL'} {fld:11s} got={got!r:40s} want={want!r}")
    print(f"\n{ok}/{total} key values match the draft truth")


if __name__ == "__main__":
    main()
