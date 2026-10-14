"""Spike A: count the items a checker must look at on real drawings (no LLM, no session, $0).

Run: uv run python spikes/spike_a_user_validation/item_counts.py
Writes results/item_counts.csv: the 4 samples plus 20 random prismatic and 20 random round client drawings.
"""

import csv
import random
import statistics
import warnings
from pathlib import Path

import pymupdf

from drawing_intelligence.extraction.pipeline import extract_pdf

ROOT = Path(__file__).resolve().parents[2] / "data"
OUT = Path(__file__).resolve().parent / "results" / "item_counts.csv"
FAMILIES = {
    "prismatic": ROOT / "client_set" / "Generic Prismatic Parts",
    "round": ROOT / "client_set" / "Generic Round Parts (Pins, Shafts)",
}
PER_FAMILY = 20
SEED = 13
FIELDS = ["family", "file", "pages", "page_pts", "dims", "notes", "views", "words", "error"]


def pdfs(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf")


def count(family: str, path: Path) -> dict:
    row = {"family": family, "file": path.name}
    try:
        ex = extract_pdf(path)  # no out_dir: no images, no session, no telemetry
        with pymupdf.open(path) as doc:
            words = sum(len(page.get_text("words")) for page in doc)
            rect = doc[0].rect
        row |= {
            "pages": ex.n_pages,
            "page_pts": f"{rect.width:.0f}x{rect.height:.0f}",
            "dims": sum(len(p.dimensions) for p in ex.pages),
            "notes": sum(len(p.notes) for p in ex.pages),
            "views": sum(len(p.view_labels) for p in ex.pages),
            "words": words,
            "error": "",
        }
    except Exception as e:  # a spike records failures instead of stopping
        row["error"] = type(e).__name__
    return row


def main() -> None:
    warnings.filterwarnings("ignore")
    rng = random.Random(SEED)
    picks = [("sample", p) for p in pdfs(ROOT / "raw")]
    for family, folder in FAMILIES.items():
        picks += [(family, p) for p in rng.sample(pdfs(folder), PER_FAMILY)]
    rows = [count(f, p) for f, p in picks]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    for family in ["sample", *FAMILIES]:
        ok = [r for r in rows if r["family"] == family and not r["error"]]
        summary = {k: statistics.median(r[k] for r in ok) for k in ("dims", "notes", "views", "words")}
        print(f"{family:10s} n={len(ok)} medians {summary}")
    print(f"errors: {sum(1 for r in rows if r['error'])}; wrote {OUT}")


if __name__ == "__main__":
    main()
