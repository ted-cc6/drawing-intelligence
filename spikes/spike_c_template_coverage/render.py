"""Render the first page (and a title-block crop) of given PDFs to out/png/ for hand inspection ($0).

Run: python spikes/spike_c_template_coverage/render.py <file-or-stem> [<file-or-stem> ...]
A bare stem is searched for under data/raw and data/client_set. Writes only into out/png/ (git-ignored).

With --notes, draws a red box around every item stage 1 classified as a note, so the A2 "notes" question
can be judged by eye (are these real notes or body text?).
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pymupdf

from drawing_intelligence.extraction.pipeline import extract_pdf
from drawing_intelligence.extraction.template import load_template

ROOT = Path(__file__).resolve().parents[2] / "data"
OUT = Path(__file__).resolve().parent / "out" / "png"
SEARCH = [ROOT / "raw", *((ROOT / "client_set").iterdir())]
LONG_SIDE_PX = 1700


def resolve(token: str) -> Path:
    p = Path(token)
    if p.is_file():
        return p
    for folder in SEARCH:
        if not folder.is_dir():
            continue
        for cand in folder.glob("*"):
            if cand.suffix.lower() == ".pdf" and cand.stem.strip() == token.strip():
                return cand
    raise FileNotFoundError(token)


def render(path: Path, mark_notes: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    template = load_template()
    with pymupdf.open(path) as doc:
        page = doc[0]
        w, h = page.rect.width, page.rect.height
        zoom = LONG_SIDE_PX / max(w, h)
        mat = pymupdf.Matrix(zoom, zoom)

        if mark_notes:
            ex = extract_pdf(path)
            shape = page.new_shape()
            for item in ex.pages[0].notes:
                shape.draw_rect(pymupdf.Rect(*item.bbox))
            shape.finish(color=(1, 0, 0), width=1.0)
            shape.commit()

        stem = path.stem.strip().replace(" ", "_")
        page.get_pixmap(matrix=mat).save(OUT / f"{stem}__full.png")

        tb = template.regions_for(w, h).get("title_block")
        if tb:
            clip = pymupdf.Rect(*tb)
            page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip).save(OUT / f"{stem}__tb.png")
    print(f"rendered {path.name} -> {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tokens", nargs="+", help="PDF path(s) or bare stem(s)")
    ap.add_argument("--notes", action="store_true", help="box every item classified as a note")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    for token in args.tokens:
        render(resolve(token), args.notes)


if __name__ == "__main__":
    main()
