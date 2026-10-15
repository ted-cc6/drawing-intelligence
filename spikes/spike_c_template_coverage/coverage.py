"""Spike C: run stage-1 extraction across the whole client set and record one CSV row per file ($0).

Run:
    python spikes/spike_c_template_coverage/coverage.py --trial     # 4 samples + 10 client files
    python spikes/spike_c_template_coverage/coverage.py             # the full set (1,171 + 4)
(or `uv run python ...`). Writes out/coverage.csv (git-ignored). Never writes into data/.

Rows are written as the run proceeds, so a crash or Ctrl-C keeps partial results. Every exception is
caught per file (type, message, last traceback line) and the run keeps going.
"""

from __future__ import annotations

import argparse
import csv
import random
import time
import traceback
import warnings
from pathlib import Path

import pymupdf
from title_block import read_title_block

from drawing_intelligence.extraction.pipeline import extract_pdf

ROOT = Path(__file__).resolve().parents[2] / "data"
OUT = Path(__file__).resolve().parent / "out" / "coverage.csv"
FAMILIES = {
    "prismatic": ROOT / "client_set" / "Generic Prismatic Parts",
    "round": ROOT / "client_set" / "Generic Round Parts (Pins, Shafts)",
}
TRIAL_PER_FAMILY = 5
SEED = 13

# ISO A series in points (72 pt/in), portrait; we match either orientation within a tolerance.
ISO_SIZES = {
    "A0": (2384, 3370),
    "A1": (1684, 2384),
    "A2": (1191, 1684),
    "A3": (842, 1191),
    "A4": (595, 842),
}
ISO_TOL = 25  # points (~9 mm): tolerates a border/bleed; far below the sqrt(2) gap between ISO sizes

FIELDS = [
    "family",
    "file",
    "pages",
    "page_w_pt",
    "page_h_pt",
    "iso_size",
    "tb_sheet_size",
    "size_mismatch",
    "words",
    "dims",
    "notes",
    "views",
    "tb_lines",
    "tb_labels_found",
    "tb_status",
    "tb_number",
    "tb_title",
    "tb_material",
    "tb_scale",
    "n_warnings",
    "first_warning",
    "seconds",
    "error_type",
    "error_msg",
    "error_where",
]


def pdfs(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf")


def iso_for(w: float, h: float) -> str:
    lo, hi = sorted((w, h))
    for name, (a, b) in ISO_SIZES.items():
        if abs(lo - a) <= ISO_TOL and abs(hi - b) <= ISO_TOL:
            return name
    return "non-standard"


def process(family: str, path: Path) -> dict:
    row = dict.fromkeys(FIELDS, "")
    row["family"], row["file"] = family, path.name
    t0 = time.perf_counter()
    try:
        ex = extract_pdf(path)  # no out_dir: no images, no session, no telemetry
        with pymupdf.open(path) as doc:
            words = sum(len(page.get_text("words")) for page in doc)
        p0 = ex.pages[0]
        w, h = p0.page_size_pts
        iso = iso_for(w, h)
        if any(iso_for(*p.page_size_pts) != iso for p in ex.pages):
            iso = "mixed"
        tb = read_title_block(p0.title_block_text)
        all_warnings = list(ex.warnings) + [w for p in ex.pages for w in p.warnings]
        tb_sheet = tb.values.get("sheet_size") or ""
        row.update(
            pages=ex.n_pages,
            page_w_pt=f"{w:.0f}",
            page_h_pt=f"{h:.0f}",
            iso_size=iso,
            tb_sheet_size=tb_sheet,
            size_mismatch=int(bool(tb_sheet) and iso != "mixed" and tb_sheet.upper() != iso),
            words=words,
            dims=sum(len(p.dimensions) for p in ex.pages),
            notes=sum(len(p.notes) for p in ex.pages),
            views=sum(len(p.view_labels) for p in ex.pages),
            tb_lines=len(p0.title_block_text),
            tb_labels_found=tb.labels_found,
            tb_status=tb.status,
            tb_number=tb.values.get("number") or "",
            tb_title=tb.values.get("title") or "",
            tb_material=tb.values.get("material") or "",
            tb_scale=tb.values.get("scale") or "",
            n_warnings=len(all_warnings),
            first_warning=all_warnings[0] if all_warnings else "",
        )
    except Exception as exc:  # a spike records failures instead of stopping
        tb_last = traceback.extract_tb(exc.__traceback__)[-1]
        row.update(
            error_type=type(exc).__name__,
            error_msg=str(exc)[:200],
            error_where=f"{Path(tb_last.filename).name}:{tb_last.lineno}",
        )
    row["seconds"] = f"{time.perf_counter() - t0:.2f}"
    return row


def picks(trial: bool, limit: int | None) -> list[tuple[str, Path]]:
    out = [("sample", p) for p in pdfs(ROOT / "raw")]
    if trial:
        rng = random.Random(SEED)
        for family, folder in FAMILIES.items():
            out += [(family, p) for p in rng.sample(pdfs(folder), TRIAL_PER_FAMILY)]
    else:
        for family, folder in FAMILIES.items():
            out += [(family, p) for p in pdfs(folder)]
    return out[:limit] if limit else out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trial", action="store_true", help="4 samples + 5 per family (seed 13)")
    ap.add_argument("--limit", type=int, default=None, help="process at most N files")
    args = ap.parse_args()

    warnings.filterwarnings("ignore")
    work = picks(args.trial, args.limit)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    errors = 0
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for i, (family, path) in enumerate(work, 1):
            row = process(family, path)
            writer.writerow(row)
            fh.flush()
            errors += bool(row["error_type"])
            if args.trial or i % 25 == 0 or i == len(work):
                dt = time.perf_counter() - t0
                print(f"[{i:4d}/{len(work)}] {dt:6.1f}s  errors={errors}  {family}/{path.name[:45]}")
    print(f"\ndone: {len(work)} files, {errors} errors, {time.perf_counter() - t0:.1f}s -> {OUT}")


if __name__ == "__main__":
    main()
