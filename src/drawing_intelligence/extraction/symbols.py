"""Symbols read from the PDF itself (Spike D): GD&T frames from the text layer, datum flags and finish
marks from vector geometry. Exact and free; the vision model finds almost none of them (0/9 datum flags, 0/32
finish marks).

- **GD&T feature control frames**: Solid Edge writes each frame as one text line whose first glyph is in the
  `SolidEdgeANSI1Symbols` font ("n 0.05 A" = perpendicularity 0.05 to datum A). The glyph map was decoded by
  rendering examples (Spike D, step 1).
- **Datum flags**: a single capital letter in a drawn box, next to a filled, roughly equilateral triangle, or
  against a GD&T frame with box strokes around it (the box shares the frame's lines).
- **Surface-finish marks**: clusters of stroked equilateral triangles (the "VV" machining marks), and an Ra
  value next to a drawn check mark ("√0.8"). A triangle with a digit inside is a revision mark (Δ1).
Anything inside the template's excluded regions (title block, tolerance table, borders) is left out.
"""

from __future__ import annotations

import itertools
import math
import re
from typing import Any, cast

import pymupdf

from drawing_intelligence.extraction.template import Rect, Template
from drawing_intelligence.schemas import SymbolItem

# Solid Edge symbol-font glyph -> GD&T characteristic.
GDT_GLYPHS = {
    "r": "flatness",
    "t": "straightness",
    "n": "perpendicularity",
    "i": "parallelism",
    "a": "concentricity",
    "d": "symmetry",
    "^": "circular_runout",
    "_": "total_runout",
    "l": "position",
    "h": "profile_of_line",
    "j": "cylindricity",
}
RA_VALUES = frozenset({"0.1", "0.2", "0.4", "0.8", "1.6", "3.2", "6.3", "12.5", "25", "50"})
SYMBOL_FONT = "Symbols"
TOL = 0.6  # pt: segment ends closer than this are the same point
_NUM = re.compile(r"\d+(?:\.\d+)?")
Seg = tuple[pymupdf.Point, pymupdf.Point]


def _d(p: pymupdf.Point, q: pymupdf.Point) -> float:
    return math.hypot(p.x - q.x, p.y - q.y)


def _vis(page: pymupdf.Page, r: pymupdf.Rect) -> Rect:
    """Unrotated PDF rect -> the visual page orientation the rest of stage 1 uses."""
    v = r * page.rotation_matrix
    v.normalize()
    return (round(v.x0, 1), round(v.y0, 1), round(v.x1, 1), round(v.y1, 1))


def _inside(r: Rect, regions: list[Rect]) -> bool:
    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    return any(a <= cx <= c and b <= cy <= d for a, b, c, d in regions)


def _lines(page: pymupdf.Page) -> list[dict[str, Any]]:
    raw = cast(dict[str, Any], page.get_text("rawdict"))
    return [ln for b in raw["blocks"] for ln in b.get("lines", [])]


def _strokes(page: pymupdf.Page) -> list[Seg]:
    return [
        (it[1], it[2]) for d in page.get_drawings() if d["type"] == "s" for it in d["items"] if it[0] == "l"
    ]


def gdt_frames(page: pymupdf.Page) -> list[dict[str, Any]]:
    """Feature control frames: characteristic, tolerance as printed, datum references, unrotated bbox."""
    out = []
    for line in _lines(page):
        first = line["spans"][0]
        if SYMBOL_FONT not in first["font"] or not first["chars"]:
            continue
        frame = parse_frame("".join(c["c"] for s in line["spans"] for c in s["chars"]))
        if frame is not None:
            out.append({**frame, "rect": line["bbox"]})
    return out


def parse_frame(raw: str) -> dict[str, Any] | None:
    """A frame's text as Solid Edge stores it ("n 0.05 A") -> characteristic, tolerance and datums."""
    if not raw or raw[0] not in GDT_GLYPHS:
        return None
    parts = raw[1:].strip().replace("O", "⌀").split()
    datums = [p for p in parts if len(p) == 1 and p.isalpha() and p.isupper()]
    tolerance = " ".join(p for p in parts if p not in datums)
    return {"characteristic": GDT_GLYPHS[raw[0]], "tolerance": tolerance, "datums": datums}


def _filled_triangles(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Filled, roughly equilateral triangles (datum flags). The corners come from the path's points, since a
    triangle may be stored with its third side implied by closing the path (2 line items) or drawn out (3)."""
    tris = []
    for d in page.get_drawings():
        items = d["items"]
        if d["type"] not in ("f", "fs") or not 2 <= len(items) <= 3 or any(i[0] != "l" for i in items):
            continue
        corners: list[pymupdf.Point] = []
        for it in items:
            for pt in (it[1], it[2]):
                if all(_d(pt, c) >= TOL for c in corners):
                    corners.append(pt)
        if len(corners) != 3:
            continue
        sides = sorted(_d(a, b) for a, b in itertools.combinations(corners, 2))
        if sides[2] / max(sides[0], 1e-6) < 1.3 and 3 <= sides[2] <= 12:
            tris.append(d["rect"])
    return tris


def _stroked_triangles(segs: list[Seg]) -> list[pymupdf.Rect]:
    """Equilateral triangles made of three separate short strokes that close up."""
    short = [(a, b) for a, b in segs if 3 <= _d(a, b) <= 15]
    by_point: dict[tuple[int, int], list[int]] = {}
    for i, (a, b) in enumerate(short):
        for p in (a, b):
            by_point.setdefault((round(p.x), round(p.y)), []).append(i)

    def near(p: pymupdf.Point) -> set[int]:
        return {
            k
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for k in by_point.get((round(p.x) + dx, round(p.y) + dy), [])
        }

    found: set[tuple[int, ...]] = set()
    for i, (a, b) in enumerate(short):
        for j in near(b) - {i}:
            c, d = short[j]
            far = d if _d(c, b) < TOL else c if _d(d, b) < TOL else None
            if far is None or _d(far, a) < TOL:
                continue
            for k in near(a) - {i, j}:
                p, q = short[k]
                if (_d(p, a) < TOL and _d(q, far) < TOL) or (_d(q, a) < TOL and _d(p, far) < TOL):
                    found.add(tuple(sorted((i, j, k))))
    tris = []
    for t in found:
        sides = sorted(_d(*short[x]) for x in t)
        if sides[2] / max(sides[0], 1e-6) >= 1.3:
            continue
        r = pymupdf.Rect(short[t[0]][0], short[t[0]][0])
        for x in t:
            r |= short[x][0]
            r |= short[x][1]
        tris.append(r)
    return tris


def _box_strokes(box: pymupdf.Rect, segs: list[Seg]) -> int:
    size = max(box.width, box.height)
    zone = pymupdf.Rect(box.x0 - size, box.y0 - size, box.x1 + size, box.y1 + size)
    return sum(1 for a, b in segs if a in zone and b in zone and 0.8 * size <= _d(a, b) <= 2.5 * size)


def _beside(box: pymupdf.Rect, other: pymupdf.Rect, direction: tuple[float, float], gap: float = 2) -> bool:
    """`other` follows or precedes `box` along the text's reading direction, within `gap`."""
    if abs(direction[0]) >= abs(direction[1]):  # horizontal text (in unrotated page space)
        return (
            min(abs(box.x0 - other.x1), abs(other.x0 - box.x1)) < gap
            and box.y0 < other.y1
            and other.y0 < box.y1
        )
    return (
        min(abs(box.y0 - other.y1), abs(other.y0 - box.y1)) < gap and box.x0 < other.x1 and other.x0 < box.x1
    )


def _touches(box: pymupdf.Rect, frame: pymupdf.Rect, gap: float = 6) -> bool:
    """The letter's box sits against one side of the frame (within `gap`) and overlaps it along that side."""
    overlaps_x = box.x0 < frame.x1 + 2 and frame.x0 - 2 < box.x1
    overlaps_y = box.y0 < frame.y1 + 2 and frame.y0 - 2 < box.y1
    near_y = min(abs(box.y0 - frame.y1), abs(frame.y0 - box.y1)) < gap
    near_x = min(abs(box.x0 - frame.x1), abs(frame.x0 - box.x1)) < gap
    return (near_y and overlaps_x) or (near_x and overlaps_y)


def datum_flags(page: pymupdf.Page, segs: list[Seg], frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    triangles = _filled_triangles(page)
    frame_rects = [pymupdf.Rect(f["rect"]) for f in frames]
    lines = _lines(page)
    # a single letter touching a number is part of a callout split into lines ("M" + "10" of an M10 thread)
    numbers = [
        pymupdf.Rect(ln["bbox"])
        for ln in lines
        if "".join(c["c"] for s in ln["spans"] for c in s["chars"]).strip()[:1].isdigit()
    ]
    # ... beside it along the reading direction, not merely above or below (a frame's "0.1" over a datum box)
    out = []
    for line in lines:
        text = "".join(c["c"] for s in line["spans"] for c in s["chars"]).strip()
        if len(text) != 1 or not text.isupper() or SYMBOL_FONT in line["spans"][0]["font"]:
            continue
        box = pymupdf.Rect(line["bbox"])
        if any(_beside(box, n, line["dir"]) for n in numbers):
            continue
        centre = (box.tl + box.br) / 2
        strokes = _box_strokes(box, segs)
        by_triangle = any(_d(centre, (t.tl + t.br) / 2) < 40 for t in triangles)
        under_frame = strokes >= 2 and any(_touches(box, f) for f in frame_rects)
        if strokes >= 4 or by_triangle or under_frame:
            out.append({"letter": text, "rect": line["bbox"]})
    return out


def finish_marks(page: pymupdf.Page, segs: list[Seg]) -> list[dict[str, Any]]:
    """ "VV" machining marks (stroked triangle clusters) and "√Ra" check marks."""
    digits = [
        pymupdf.Rect(ln["bbox"])
        for ln in _lines(page)
        if re.fullmatch(r"\d", "".join(c["c"] for s in ln["spans"] for c in s["chars"]).strip())
    ]
    clusters: list[pymupdf.Rect] = []
    for r in _stroked_triangles(segs):
        if any(r.contains((d.tl + d.br) / 2) for d in digits):
            continue  # a revision triangle (Δ1)
        for i, c in enumerate(clusters):
            if pymupdf.Rect(c.x0 - 12, c.y0 - 12, c.x1 + 12, c.y1 + 12).intersects(r):
                clusters[i] = c | r
                break
        else:
            clusters.append(pymupdf.Rect(r))
    out: list[dict[str, Any]] = [{"ra": None, "rect": (c.x0, c.y0, c.x1, c.y1)} for c in clusters]
    for line in _lines(page):
        text = "".join(c["c"] for s in line["spans"] for c in s["chars"]).strip()
        if text not in RA_VALUES:
            continue
        box = pymupdf.Rect(line["bbox"])
        size = max(box.width, box.height)
        m = 1.5 * size
        zone = pymupdf.Rect(box.x0 - m, box.y0 - m, box.x1 + m, box.y1 + m)
        near = [(a, b) for a, b in segs if (a in zone or b in zone) and 0.3 * size < _d(a, b) < 6 * size]
        if any(_check_mark(s1, s2) for s1, s2 in itertools.combinations(near, 2)):
            out.append({"ra": text, "rect": line["bbox"]})
    return out


def _angle(o: pymupdf.Point, a: pymupdf.Point, b: pymupdf.Point) -> float:
    u, v = a - o, b - o
    cos = (u.x * v.x + u.y * v.y) / max(abs(u) * abs(v), 1e-6)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _check_mark(s1: Seg, s2: Seg) -> bool:
    """Two strokes meeting at about 60 degrees, one at least 1.5x the other: the long arm of a √."""
    (a, b), (c, d) = s1, s2
    for o, p in ((a, b), (b, a)):
        q = c if _d(o, d) < TOL else d if _d(o, c) < TOL else None
        if q is None:
            continue
        la, lb = _d(o, p), _d(o, q)
        if 45 < _angle(o, p, q) < 75 and max(la, lb) >= 1.5 * min(la, lb):
            return True
    return False


_TABLE_TEXT = re.compile(
    r"UP TO|OVER \d|±|UNSPECIFIED|UNSP\.|LIMITS|DEBURR|SHARP EDGE|REQUIREMENT|Gen Tol|FOR (LINEAR|ANGULAR)",
    re.IGNORECASE,
)


def _masked(page: pymupdf.Page, template: Template) -> list[Rect]:
    """Template areas symbols cannot be in. The tolerance-table strip runs the full sheet height but the table
    fills only part of it, and a datum flag can sit above it: only the table's own text area is masked."""
    w, h = page.rect.width, page.rect.height
    regions = template.regions_for(w, h)
    masked = [regions[n] for n in template.exclude_from_dimensions if n != "tolerance_table"]
    strip = regions.get("tolerance_table")
    if strip is None:
        return masked
    rmat = page.rotation_matrix
    table = None
    for ln in _lines(page):
        if not _TABLE_TEXT.search("".join(c["c"] for s in ln["spans"] for c in s["chars"])):
            continue  # only the table's own text: not a note above it, not a single datum letter
        v = pymupdf.Rect(ln["bbox"]) * rmat
        v.normalize()
        if strip[0] <= (v.x0 + v.x1) / 2 <= strip[2] and strip[1] <= (v.y0 + v.y1) / 2 <= strip[3]:
            table = v if table is None else table | v
    if table is not None:
        masked.append((table.x0, table.y0, table.x1, table.y1))
    return masked


def read_symbols(page: pymupdf.Page, template: Template) -> list[SymbolItem]:
    """Every GD&T frame, datum flag and finish mark on the page, numbered S1, S2, ... in reading order."""
    skip = _masked(page, template)
    segs = _strokes(page)
    frames = gdt_frames(page)
    found: list[SymbolItem] = []
    for f in frames:
        datum = f" | {' | '.join(f['datums'])}" if f["datums"] else ""
        found.append(
            SymbolItem(
                id="",
                type="gdt",
                text=f"{f['characteristic'].replace('_', ' ')} {f['tolerance']}{datum}".strip(),
                characteristic=f["characteristic"],
                tolerance=f["tolerance"] or None,
                datums=f["datums"],
                bbox=_vis(page, pymupdf.Rect(f["rect"])),
                provenance="pdf_text",
            )
        )
    for d in datum_flags(page, segs, frames):
        found.append(
            SymbolItem(
                id="", type="datum", text=f"datum {d['letter']}", datums=[d["letter"]],
                bbox=_vis(page, pymupdf.Rect(d["rect"])), provenance="vector",
            )
        )  # fmt: skip
    for m in finish_marks(page, segs):
        found.append(
            SymbolItem(
                id="", type="surface_finish", text=f"Ra {m['ra']}" if m["ra"] else "machining mark",
                ra=m["ra"], bbox=_vis(page, pymupdf.Rect(m["rect"])),
                provenance="pdf_text" if m["ra"] else "vector",
            )
        )  # fmt: skip
    kept = [s for s in found if not _inside(s.bbox, skip)]
    kept.sort(key=lambda s: (round(s.bbox[1] / 15), s.bbox[0]))
    return [s.model_copy(update={"id": f"S{i}"}) for i, s in enumerate(kept, 1)]
