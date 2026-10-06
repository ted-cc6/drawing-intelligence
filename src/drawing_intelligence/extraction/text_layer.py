"""Reading text lines and line segments from one PDF page, corrected for the page's /Rotate flag."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pymupdf

from drawing_intelligence.extraction.classify import Category
from drawing_intelligence.extraction.template import GlyphRemap, Rect

Segment = tuple[float, float, float, float]


@dataclass(eq=False)  # identity semantics: the cleanup steps track rows by object identity
class Row:
    """A working text item while the extraction pipeline cleans and classifies it."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float = 0.0
    is_reference: bool = False
    category: Category | None = None

    @property
    def bbox(self) -> Rect:
        return (self.x0, self.y0, self.x1, self.y1)


def remap_text(spans: list[dict[str, Any]], remaps: list[GlyphRemap]) -> str:
    # Swap mis-decoded symbol-font characters back to their real symbol.
    out = []
    for span in spans:
        text = span["text"]
        for r in remaps:
            if r.font_contains in span["font"]:
                text = text.replace(r.char, r.replace_with)
        out.append(text)
    return "".join(out)


def _inside_any(bbox: Rect, rects: list[Rect]) -> bool:
    x0, y0, x1, y1 = bbox
    return any(x0 >= ex0 and y0 >= ey0 and x1 <= ex1 and y1 <= ey1 for ex0, ey0, ex1, ey1 in rects)


def text_dict(page: pymupdf.Page) -> dict[str, Any]:
    """The page's text as PyMuPDF's nested dict (blocks -> lines -> spans)."""
    return cast(dict[str, Any], page.get_text("dict"))


def _lines(page: pymupdf.Page):
    rmat = page.rotation_matrix
    for block in text_dict(page)["blocks"]:
        for line in block.get("lines", []):
            r = pymupdf.Rect(line["bbox"]) * rmat
            yield line, (r.x0, r.y0, r.x1, r.y1)


def raw_rows(page: pymupdf.Page, exclude: list[Rect], remaps: list[GlyphRemap]) -> list[Row]:
    """Text lines outside the template regions, as working rows."""
    rows = []
    for line, bbox in _lines(page):
        if _inside_any(bbox, exclude):
            continue
        text = remap_text(line["spans"], remaps)
        if not text.strip():
            continue
        rows.append(Row(text, *bbox, font_size=line["spans"][0]["size"]))
    return rows


def all_text_lines(page: pymupdf.Page, remaps: list[GlyphRemap]) -> list[tuple[str, Rect]]:
    """Every text line on the page, nothing excluded, rounded to 0.1 pt."""
    out = []
    for line, (x0, y0, x1, y1) in _lines(page):
        text = remap_text(line["spans"], remaps).strip()
        if text:
            out.append((text, (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))))
    return out


def line_segments(page: pymupdf.Page) -> list[Segment]:
    """Every straight line on the page (outline, dimension and extension lines, hatching, borders)."""
    rmat = page.rotation_matrix
    segs = []
    for d in page.get_drawings():
        for item in d["items"]:
            if item[0] == "l":
                p1, p2 = item[1] * rmat, item[2] * rmat
                segs.append((p1.x, p1.y, p2.x, p2.y))
    return segs
