"""Build the Spike D answer key: what symbols are really on each page. No API cost.

Three sources, merged per page:
1. GD&T feature control frames - EXACT, from the text layer. Solid Edge writes each frame as one text line
   whose first glyph is in the `SolidEdgeANSI1Symbols` font ("i 0.05 A" = parallelism 0.05 to datum A).
2. Datum flags and surface-finish marks - CANDIDATES from vector geometry. A datum flag is a single capital
   letter in a drawn box or next to a filled, roughly equilateral triangle. A finish mark is a cluster of
   stroked equilateral triangles (the old-style "VV" marks) or an Ra value next to a drawn check mark
   ("√0.8"). The template regions (title block, tolerance table, borders) are skipped.
3. Manual corrections in results/manual_labels.json - removals of false candidates and additions (e.g. "√"
   finish symbols and weld symbols, which have no reliable vector signature). Each change has a reason.

Writes out/answer_key/<drawing>_p<n>.png (overlays with numbered boxes, for human review),
results/answer_key.json (every symbol with type, page, bbox, source) and results/answer_key_counts.csv.

Run:
    python spikes/spike_d_symbols/answer_key.py
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import math
from collections import Counter

import pymupdf
from common import DRAWINGS, OUT, RESULTS, SYMBOL_TYPES
from PIL import Image, ImageDraw

from drawing_intelligence.extraction.template import load_template

# Solid Edge symbol-font glyph -> GD&T characteristic (decoded by rendering examples; see the findings doc).
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
TOL = 0.6  # pt: endpoints closer than this are the same point
COLOURS = {"gdt": "magenta", "datum": "blue", "surface_finish": "red", "weld": "darkorange"}
Rect = tuple[float, float, float, float]


def _vis(page: pymupdf.Page, r: pymupdf.Rect) -> Rect:
    """Unrotated PDF rect -> visual page orientation (the coordinates extraction and the model use)."""
    v = r * page.rotation_matrix
    v.normalize()
    return (round(v.x0, 1), round(v.y0, 1), round(v.x1, 1), round(v.y1, 1))


def _inside(r: Rect, regions: list[Rect]) -> bool:
    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    return any(a <= cx <= c and b <= cy <= d for a, b, c, d in regions)


def gdt_frames(page: pymupdf.Page) -> list[dict]:
    out = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            first = line["spans"][0]
            if "Symbols" not in first["font"] or not first["chars"]:
                continue
            glyph = first["chars"][0]["c"]
            if glyph not in GDT_GLYPHS:
                continue
            rest = "".join(c["c"] for s in line["spans"] for c in s["chars"])[1:].strip().replace("O", "⌀")
            parts = rest.split()
            datums = [p for p in parts if len(p) == 1 and p.isalpha() and p.isupper()]
            value = " ".join(p for p in parts if p not in datums)
            out.append(
                {
                    "type": "gdt",
                    "value": f"{GDT_GLYPHS[glyph]} {value}".strip(),
                    "datum": "".join(datums) or None,
                    "bbox": _vis(page, pymupdf.Rect(line["bbox"])),
                    "source": "text_layer",
                }
            )
    return out


def _triangles(page: pymupdf.Page, filled: bool) -> list[tuple[pymupdf.Rect, list[float]]]:
    """Triangles drawn on the page: filled 3-line paths, or 3 separate stroked segments that close up."""
    if filled:
        tris = []
        for d in page.get_drawings():
            items = d["items"]
            if d["type"] == "f" and len(items) == 3 and all(i[0] == "l" for i in items):
                sides = sorted(math.dist(i[1], i[2]) for i in items)
                tris.append((d["rect"], sides))
        return tris
    segs = []
    for d in page.get_drawings():
        if d["type"] != "s":
            continue
        for it in d["items"]:
            if it[0] == "l" and 3 <= math.dist(it[1], it[2]) <= 15:
                segs.append((it[1], it[2]))
    by_point: dict[tuple[int, int], list[int]] = {}
    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            by_point.setdefault((round(p.x), round(p.y)), []).append(i)

    def near(p: pymupdf.Point) -> set[int]:
        return {
            k
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for k in by_point.get((round(p.x) + dx, round(p.y) + dy), [])
        }

    found = set()
    for i, (a, b) in enumerate(segs):
        for j in near(b) - {i}:
            c, d = segs[j]
            far = d if math.dist(c, b) < TOL else c if math.dist(d, b) < TOL else None
            if far is None or math.dist(far, a) < TOL:
                continue
            for k in near(a) - {i, j}:
                p, q = segs[k]
                if (math.dist(p, a) < TOL and math.dist(q, far) < TOL) or (
                    math.dist(q, a) < TOL and math.dist(p, far) < TOL
                ):
                    found.add(tuple(sorted((i, j, k))))
    tris = []
    for t in found:
        r = pymupdf.Rect(segs[t[0]][0], segs[t[0]][0])
        for x in t:
            r |= segs[x][0]
            r |= segs[x][1]
        tris.append((r, sorted(math.dist(*segs[x]) for x in t)))
    return tris


def _equilateral(sides: list[float]) -> bool:
    return sides[2] / max(sides[0], 1e-6) < 1.3


def _boxed(box: pymupdf.Rect, segs: list[tuple[pymupdf.Point, pymupdf.Point]]) -> bool:
    """A letter is boxed when >= 4 stroked segments of about box size lie just around it (any rotation)."""
    size = max(box.width, box.height)
    zone = pymupdf.Rect(box.x0 - size, box.y0 - size, box.x1 + size, box.y1 + size)
    near = [
        (a, b) for a, b in segs if a in zone and b in zone and 0.8 * size <= math.dist(a, b) <= 2.5 * size
    ]
    return len(near) >= 4


def datum_flags(page: pymupdf.Page, skip: list[Rect]) -> list[dict]:
    triangles = [r for r, s in _triangles(page, filled=True) if _equilateral(s) and 3 <= s[2] <= 12]
    segs = [
        (it[1], it[2]) for d in page.get_drawings() if d["type"] == "s" for it in d["items"] if it[0] == "l"
    ]
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if len(text) != 1 or not text.isupper() or "Symbols" in line["spans"][0]["font"]:
                continue
            box = pymupdf.Rect(line["bbox"])
            c = (box.tl + box.br) / 2
            if not _boxed(box, segs) and not any(math.dist(c, (t.tl + t.br) / 2) < 30 for t in triangles):
                continue
            bbox = _vis(page, box)
            if not _inside(bbox, skip):
                out.append(
                    {
                        "type": "datum",
                        "value": f"datum {text}",
                        "datum": text,
                        "bbox": bbox,
                        "source": "vector",
                    }
                )
    return out


def finish_marks(page: pymupdf.Page, skip: list[Rect]) -> list[dict]:
    tris = [r for r, s in _triangles(page, filled=False) if _equilateral(s)]
    clusters: list[pymupdf.Rect] = []
    for r in tris:  # group the 2-3 triangles of one mark (and its grade text) into one symbol
        for i, c in enumerate(clusters):
            if pymupdf.Rect(c.x0 - 12, c.y0 - 12, c.x1 + 12, c.y1 + 12).intersects(r):
                clusters[i] = c | r
                break
        else:
            clusters.append(pymupdf.Rect(r))
    out = []
    for c in clusters:
        bbox = _vis(page, c)
        if not _inside(bbox, skip):
            out.append(
                {
                    "type": "surface_finish",
                    "value": "machining mark",
                    "datum": None,
                    "bbox": bbox,
                    "source": "vector",
                }
            )
    return out


RA_VALUES = {"0.1", "0.2", "0.4", "0.8", "1.6", "3.2", "6.3", "12.5", "25", "50"}


def _angle(o: pymupdf.Point, a: pymupdf.Point, b: pymupdf.Point) -> float:
    u, v = a - o, b - o
    cos = (u.x * v.x + u.y * v.y) / max(abs(u) * abs(v), 1e-6)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def check_marks(page: pymupdf.Page, skip: list[Rect]) -> list[dict]:
    """ "√" roughness symbols: an Ra value in the text layer next to a check mark - two strokes that meet at
    about 60 degrees, one at least 1.5x the other (the long arm of the √)."""
    segs = [
        (it[1], it[2]) for d in page.get_drawings() if d["type"] == "s" for it in d["items"] if it[0] == "l"
    ]
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text not in RA_VALUES:
                continue
            box = pymupdf.Rect(line["bbox"])
            size = max(box.width, box.height)
            m = 1.5 * size
            zone = pymupdf.Rect(box.x0 - m, box.y0 - m, box.x1 + m, box.y1 + m)
            near = [
                (a, b)
                for a, b in segs
                if (a in zone or b in zone) and 0.3 * size < math.dist(a, b) < 6 * size
            ]
            found = False
            for (a, b), (c, d) in itertools.combinations(near, 2):
                for o, p, q in (
                    (a, b, c if math.dist(a, d) < TOL else d),
                    (b, a, c if math.dist(b, d) < TOL else d),
                ):
                    if min(math.dist(o, c), math.dist(o, d)) > TOL:
                        continue
                    la, lb = math.dist(o, p), math.dist(o, q)
                    if 45 < _angle(o, p, q) < 75 and max(la, lb) >= 1.5 * min(la, lb):
                        found = True
            bbox = _vis(page, box)
            if found and not _inside(bbox, skip):
                out.append(
                    {
                        "type": "surface_finish",
                        "value": f"Ra {text}",
                        "datum": None,
                        "bbox": bbox,
                        "source": "vector",
                    }
                )
    return out


def overlay(page: pymupdf.Page, symbols: list[dict], path) -> None:
    dpi = 110 if max(page.rect.width, page.rect.height) < 1300 else 80
    z = dpi / 72
    img = Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB")
    draw = ImageDraw.Draw(img)
    for s in symbols:
        x0, y0, x1, y1 = (v * z for v in s["bbox"])
        draw.rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), outline=COLOURS[s["type"]], width=3)
        draw.text((x1 + 6, y0 - 12), s["id"], fill=COLOURS[s["type"]])
    img.save(path)


def main() -> None:
    template = load_template()
    manual = json.loads((RESULTS / "manual_labels.json").read_text(encoding="utf-8"))
    (OUT / "answer_key").mkdir(parents=True, exist_ok=True)
    key: dict[str, dict[str, list[dict]]] = {}
    rows = []
    for name, pdf in DRAWINGS.items():
        key[name] = {}
        with pymupdf.open(pdf) as doc:
            for page in doc:
                n = page.number + 1
                skip = template.excluded_rects(page.rect.width, page.rect.height)
                auto = (
                    gdt_frames(page)
                    + datum_flags(page, skip)
                    + finish_marks(page, skip)
                    + check_marks(page, skip)
                )
                for i, s in enumerate(auto, 1):
                    s["id"] = f"K{i}"
                edits = manual.get(name, {}).get(str(n), {})
                removed = set(edits.get("remove", {}))
                symbols = [s for s in auto if s["id"] not in removed]
                for i, s in enumerate(edits.get("add", []), 1):
                    symbols.append({"id": f"M{i}", "datum": None, "source": "manual", **s})
                key[name][str(n)] = symbols
                overlay(page, symbols, OUT / "answer_key" / f"{name}_p{n}.png")
                counts = Counter(s["type"] for s in symbols)
                rows.append({"drawing": name, "page": n, **{t: counts[t] for t in SYMBOL_TYPES}})
    (RESULTS / "answer_key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    with (RESULTS / "answer_key_counts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
