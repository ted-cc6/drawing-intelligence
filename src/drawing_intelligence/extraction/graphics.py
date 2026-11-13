"""How each dimension value is drawn, read from the PDF's vector paths: the arrowheads, the line or leader the
value sits on, the direction the value reads in, and whether it is boxed, underlined or crossed by a line.
Also the full circles on the sheet and the revision marks (Δ) on the field. Exact and free, like `symbols`.

PARI's Solid Edge PDFs draw every stroke as a separate straight segment (circles and arcs are chains of short
segments, never curves) and every arrowhead as a small filled triangle about 2.3 x 6.9 pt. Everything here is
in the visual (rotation-corrected) page coordinates the rest of stage 1 uses.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from typing import Any

import pymupdf

from drawing_intelligence.extraction.symbols import _filled_triangles, revision_marks
from drawing_intelligence.extraction.template import Rect
from drawing_intelligence.extraction.text_layer import Row, Segment
from drawing_intelligence.schemas import (
    ArrowheadItem,
    CircleItem,
    DimensionGraphics,
    FieldRevisionMark,
    PageGraphics,
)

Point = tuple[float, float]
TOL = 0.8  # pt: points closer than this are the same point


def _dist(p: Point, q: Point) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _r(v: float) -> float:
    return round(v, 1)


@dataclass(frozen=True)
class Arrow:
    tip: Point
    axis: Point  # unit vector from the base to the tip
    length: float
    style: str  # filled | closed | open
    base: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))  # the two base corners


def _triangle_arrow(corners: list[Point], style: str) -> Arrow | None:
    """A slender isosceles triangle (long sides 2-5x the base, 4-16 pt long) is an arrowhead; its tip is the
    corner opposite the base. A datum flag's triangle is about equilateral and is left out."""
    pairs = [(corners[i], corners[(i + 1) % 3], corners[(i + 2) % 3]) for i in range(3)]
    a, b, tip = min(pairs, key=lambda t: _dist(t[0], t[1]))  # the base is the shortest side
    base = _dist(a, b)
    legs = (_dist(a, tip), _dist(b, tip))
    if base < 0.5 or not 4 <= max(legs) <= 16 or not 2 <= min(legs) / base <= 5.5:
        return None
    if abs(legs[0] - legs[1]) > 0.15 * max(legs):
        return None
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    length = _dist(mid, tip)
    return Arrow(tip, ((tip[0] - mid[0]) / length, (tip[1] - mid[1]) / length), length, style, (a, b))


def _corners(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if all(_dist(p, c) >= TOL / 2 for c in out):
            out.append(p)
    return out


def read_arrowheads(drawings: list[dict[str, Any]], rmat: pymupdf.Matrix, segs: list[Segment]) -> list[Arrow]:
    """Filled triangles, stroked closed triangles and open arrowheads (two strokes meeting at a sharp tip
    with a line running back from the tip between them)."""
    out: list[Arrow] = []
    for d in drawings:
        items = d["items"]
        if d["type"] in ("f", "fs") and 2 <= len(items) <= 4 and all(i[0] == "l" for i in items):
            pts = [(p.x, p.y) for it in items for p in (it[1] * rmat, it[2] * rmat)]
            c = _corners(pts)
            if len(c) == 3 and (a := _triangle_arrow(c, "filled")):
                out.append(a)
    short = [s for s in segs if 3 <= math.dist(s[:2], s[2:]) <= 16]
    by_point: dict[tuple[int, int], list[tuple[Point, Point]]] = {}
    for x0, y0, x1, y1 in short:
        for p, q in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
            by_point.setdefault((round(p[0]), round(p[1])), []).append((p, q))
    seen: set[tuple[int, int]] = set()
    for key, legs in by_point.items():
        for (tip, f1), (tip2, f2) in itertools.combinations(legs, 2):
            if _dist(tip, tip2) > TOL or _dist(f1, f2) < 0.5:
                continue
            closed = any(
                (_dist(f1, p) < TOL and _dist(f2, q) < TOL) or (_dist(f2, p) < TOL and _dist(f1, q) < TOL)
                for p, q in ((s[:2], s[2:]) for s in short)
            )
            a = _triangle_arrow([f1, f2, tip], "closed" if closed else "open")
            if a is None or key in seen:
                continue
            if not _shaft(a, segs):
                continue  # two strokes meeting are a corner or two chords of an arc, unless a line ends there
            seen.add(key)
            out.append(a)
    return _dedupe(out)


def _dedupe(arrows: list[Arrow]) -> list[Arrow]:
    """One arrow per tip and direction. Solid Edge strokes a filled arrowhead's outline as well, so the same
    arrow is found filled and again as strokes: the filled one is kept."""
    rank = {"filled": 0, "closed": 1, "open": 2}
    kept: list[Arrow] = []
    for a in sorted(arrows, key=lambda a: rank[a.style]):
        if not any(
            _dist(a.tip, k.tip) < 1.0 and a.axis[0] * k.axis[0] + a.axis[1] * k.axis[1] > 0.95 for k in kept
        ):
            kept.append(a)
    return kept


def _shaft(a: Arrow, segs: list[Segment]) -> bool:
    """A straight line at least twice the arrow's length that ends at its tip and runs back along its axis
    (a dimension line). Two short segments of a curve drawn as a chain never have one."""
    for s in segs:
        for end, other in ((s[:2], s[2:]), (s[2:], s[:2])):
            if _dist(end, a.tip) > TOL or math.dist(end, other) < 2 * a.length or not _parallel(s, a.axis):
                continue
            back = (other[0] - a.tip[0]) * a.axis[0] + (other[1] - a.tip[1]) * a.axis[1]
            if back < 0:
                return True
    return False


def _parallel(s: Segment, u: Point, tol: float = 0.03) -> bool:
    dx, dy = s[2] - s[0], s[3] - s[1]
    n = math.hypot(dx, dy)
    return n > 0 and abs(dx * u[1] - dy * u[0]) / n < tol


def _across(p: Point, s: Segment) -> float:
    """Distance from `p` to the infinite line through the segment."""
    x0, y0, x1, y1 = s
    n = math.hypot(x1 - x0, y1 - y0)
    return abs((p[0] - x0) * (y1 - y0) - (p[1] - y0) * (x1 - x0)) / n if n else _dist(p, (x0, y0))


def _on_segment(p: Point, s: Segment, tol: float) -> bool:
    """`p` lies on the segment (within `tol` across it and along it)."""
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    n2 = dx * dx + dy * dy
    if n2 == 0:
        return _dist(p, (x0, y0)) <= tol
    t = ((p[0] - x0) * dx + (p[1] - y0) * dy) / n2
    n = math.sqrt(n2)
    if t < -tol / n or t > 1 + tol / n:
        return False
    return abs((p[0] - x0) * dy - (p[1] - y0) * dx) / n <= tol


def _seg_rect_gap(s: Segment, r: Rect) -> float:
    """Distance from a segment to a rectangle (0 when they touch or cross)."""
    if _crosses(s, r) or _inside(s[:2], r) or _inside(s[2:], r):
        return 0.0
    corners = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    edges = [(*corners[i], *corners[(i + 1) % 4]) for i in range(4)]
    return min(
        min(_point_seg(p, s) for p in corners),
        min(_point_seg(s[:2], e) for e in edges),
        min(_point_seg(s[2:], e) for e in edges),
    )


def _point_seg(p: Point, s: Segment) -> float:
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    n2 = dx * dx + dy * dy
    t = 0.0 if n2 == 0 else max(0.0, min(1.0, ((p[0] - x0) * dx + (p[1] - y0) * dy) / n2))
    return _dist(p, (x0 + t * dx, y0 + t * dy))


def _inside(p: Point, r: Rect) -> bool:
    return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


def _crosses(s: Segment, r: Rect) -> bool:
    """The segment passes through the rectangle (Liang-Barsky clipping)."""
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


# --- circles ----------------------------------------------------------------------------------------------


def read_circles(segs: list[Segment], min_sides: int = 12) -> list[tuple[Point, float]]:
    """Full circles: closed chains of short segments whose points sit at one distance from their centre."""
    short = [s for s in segs if 0.2 <= math.dist(s[:2], s[2:]) <= 30]
    key = lambda p: (round(p[0] * 2), round(p[1] * 2))  # noqa: E731 - 0.5 pt grid
    adj: dict[tuple[int, int], list[int]] = {}
    for i, s in enumerate(short):
        for p in (s[:2], s[2:]):
            adj.setdefault(key(p), []).append(i)
    used: set[int] = set()
    out: list[tuple[Point, float]] = []
    for start in range(len(short)):
        if start in used:
            continue
        chain, pts = [start], [short[start][:2]]
        used.add(start)
        cur = short[start][2:]
        while True:
            nxt = [j for j in adj.get(key(cur), []) if j not in used]
            if len(nxt) != 1:
                break
            j = nxt[0]
            used.add(j)
            chain.append(j)
            pts.append(cur)
            s = short[j]
            cur = s[2:] if key(s[:2]) == key(cur) else s[:2]
        if len(chain) < min_sides or _dist(cur, pts[0]) > 1.0:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        radii = [_dist(p, (cx, cy)) for p in pts]
        r = sum(radii) / len(radii)
        if r > 1 and max(abs(x - r) for x in radii) <= max(0.5, 0.03 * r):
            out.append(((cx, cy), r))
    return out


def _fit_circle(pts: list[Point]) -> tuple[Point, float] | None:
    """Least-squares circle through the points (Kasa's fit): solve x² + y² + Dx + Ey + F = 0."""
    n = len(pts)
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    syy = sum(p[1] * p[1] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    z = [p[0] * p[0] + p[1] * p[1] for p in pts]
    sz = sum(z)
    sxz = sum(p[0] * zi for p, zi in zip(pts, z, strict=True))
    syz = sum(p[1] * zi for p, zi in zip(pts, z, strict=True))
    a = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, float(n)]]
    b = [-sxz, -syz, -sz]

    def det(m: list[list[float]]) -> float:
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    d0 = det(a)
    if abs(d0) < 1e-9:
        return None
    sol = []
    for col in range(3):
        m = [row[:] for row in a]
        for r in range(3):
            m[r][col] = b[r]
        sol.append(det(m) / d0)
    dd, ee, ff = sol
    cx, cy = -dd / 2, -ee / 2
    r2 = cx * cx + cy * cy - ff
    return ((cx, cy), math.sqrt(r2)) if r2 > 0 else None


def _chain(
    start: int, segs: list[Segment], ends: dict[tuple[int, int], list[int]], limit: int = 80
) -> list[int]:
    """The unbranched run of short segments through `start`, followed both ways."""
    out = [start]
    for end in (segs[start][:2], segs[start][2:]):
        cur, at = start, end
        for _ in range(limit):
            kx, ky = round(at[0]), round(at[1])
            nxt = {
                j
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for j in ends.get((kx + dx, ky + dy), [])
                if j != cur
                and j not in out
                and (_dist(segs[j][:2], at) < TOL or _dist(segs[j][2:], at) < TOL)
            }
            if len(nxt) != 1:
                break
            j = nxt.pop()
            if math.dist(segs[j][:2], segs[j][2:]) >= 15:
                break
            out.append(j)
            cur = j
            at = segs[j][2:] if _dist(segs[j][:2], at) < TOL else segs[j][:2]
    return out


def _arc_radius(
    tip: Point, axis: Point, segs: list[Segment], ends: dict[tuple[int, int], list[int]], skip: set[int]
) -> float | None:
    """The radius of the arc an arrow lands on: the unbranched chain of short segments through its tip, fitted
    with a circle. A radius arrow points along the radius, so the fit counts only when the arrow's axis runs
    through the arc's centre (within 15 degrees). None when the tip is on no such chain, or the chain is too
    straight or too short to fit."""
    start = [
        j
        for j, s in enumerate(segs)
        if j not in skip and math.dist(s[:2], s[2:]) < 15 and _on_segment(tip, s, 0.8)
    ]
    for j in start:
        chain = _chain(j, segs, ends)
        if len(chain) < 3:
            continue
        pts = _corners([p for k in chain for p in (segs[k][:2], segs[k][2:])])
        fit = _fit_circle(pts)
        if fit is None:
            continue
        c, r = fit
        if not 10 <= r <= 2000 or len(pts) < 5 or max(abs(_dist(p, c) - r) for p in pts) > max(0.4, 0.02 * r):
            continue
        angles = sorted(math.atan2(p[1] - c[1], p[0] - c[0]) for p in pts)
        span = max(angles) - min(angles)
        to_centre = (c[0] - tip[0], c[1] - tip[1])
        n = math.hypot(*to_centre)
        aligned = n > 0 and abs(axis[0] * to_centre[0] + axis[1] * to_centre[1]) / n >= math.cos(
            math.radians(15)
        )
        if math.degrees(min(span, 2 * math.pi - span)) >= 20 and aligned:
            return r
    return None


# --- dimensions -------------------------------------------------------------------------------------------


def _arrowed_lines(arrows: list[Arrow], segs: list[Segment]) -> dict[int, list[int]]:
    """Segment index -> the arrows on it: the tip on the segment and the arrow pointing along it."""
    out: dict[int, list[int]] = {}
    for ai, a in enumerate(arrows):
        for si, s in enumerate(segs):
            if math.dist(s[:2], s[2:]) < 1.5 or not _parallel(s, a.axis, 0.2):
                continue
            corners = (a.tip, *a.base)
            if all(any(_dist(e, c) < TOL for c in corners) for e in (s[:2], s[2:])):
                continue  # the arrowhead's own outline (Solid Edge strokes its legs too)
            if _on_segment(a.tip, s, 0.7):
                out.setdefault(si, []).append(ai)
    return out


def _ends_index(segs: list[Segment]) -> dict[tuple[int, int], list[int]]:
    out: dict[tuple[int, int], list[int]] = {}
    for i, s in enumerate(segs):
        for x, y in (s[:2], s[2:]):
            out.setdefault((round(x), round(y)), []).append(i)
    return out


def _connected(
    start: int, segs: list[Segment], ends: dict[tuple[int, int], list[int]], limit: int = 3
) -> set[int]:
    """Segments sharing an end with `start`, up to `limit` hops (a leader's shoulder, a dimension line's two
    halves when the value breaks it), and on along any unbranched chain (an angle's arc, drawn as many short
    segments)."""

    def joined(i: int) -> list[int]:
        out = []
        for p in (segs[i][:2], segs[i][2:]):
            kx, ky = round(p[0]), round(p[1])
            for j in {j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in ends.get((kx + dx, ky + dy), [])}:
                s = segs[j]
                if j != i and (_dist(s[:2], p) < TOL or _dist(s[2:], p) < TOL):
                    out.append(j)
        return out

    found = {start}
    frontier = {start}
    for _ in range(limit):
        new = {j for i in frontier for j in joined(i)} - found
        if not new:
            break
        found |= new
        frontier = new
    # follow unbranched chains of short segments (arcs) from what was found
    stack = [i for i in found if math.dist(segs[i][:2], segs[i][2:]) < 15]
    steps = 0
    while stack and steps < 400:
        i = stack.pop()
        nxt = [j for j in joined(i) if j not in found]
        if len(nxt) == 1 and math.dist(segs[nxt[0]][:2], segs[nxt[0]][2:]) < 15:
            found.add(nxt[0])
            stack.append(nxt[0])
        steps += 1
    return found


def _bounds(segs: list[Segment]) -> Rect:
    xs = [v for s in segs for v in (s[0], s[2])]
    ys = [v for s in segs for v in (s[1], s[3])]
    return (min(xs), min(ys), max(xs), max(ys))


def _box_around(r: Rect, segs: list[Segment], margin: float) -> bool:
    """A drawn rectangle framing the value: a horizontal stroke above and below and a vertical one left and
    right, each within `margin` of the value, meeting at four corners. Extension lines and a dimension line
    around a value pass close on four sides too, but they do not meet at corners."""
    x0, y0, x1, y1 = r
    hs = [
        s for s in segs if abs(s[1] - s[3]) < 0.3 and min(s[0], s[2]) <= x0 + 1 and max(s[0], s[2]) >= x1 - 1
    ]
    vs = [
        s for s in segs if abs(s[0] - s[2]) < 0.3 and min(s[1], s[3]) <= y0 + 1 and max(s[1], s[3]) >= y1 - 1
    ]
    tops = [s for s in hs if 0 <= y0 - s[1] <= margin]
    bottoms = [s for s in hs if 0 <= s[1] - y1 <= margin]
    lefts = [s for s in vs if 0 <= x0 - s[0] <= margin]
    rights = [s for s in vs if 0 <= s[0] - x1 <= margin]

    def ends(s: Segment, horizontal: bool) -> tuple[float, float]:
        return tuple(sorted((s[0], s[2]) if horizontal else (s[1], s[3])))  # type: ignore[return-value]

    for t, bo, le, ri in itertools.product(tops, bottoms, lefts, rights):
        tx, bx = ends(t, True), ends(bo, True)
        ly, ry = ends(le, False), ends(ri, False)
        corners_x = all(abs(a - le[0]) <= 1.5 for a in (tx[0], bx[0])) and all(
            abs(a - ri[0]) <= 1.5 for a in (tx[1], bx[1])
        )
        corners_y = all(abs(a - t[1]) <= 1.5 for a in (ly[0], ry[0])) and all(
            abs(a - bo[1]) <= 1.5 for a in (ly[1], ry[1])
        )
        if corners_x and corners_y:
            return True
    return False


def _in_cell(r: Rect, h_lines: list[Segment], v_lines: list[Segment]) -> bool:
    """Ruled on all four sides: a line above and below spanning the value, one left and one right spanning
    its height (a hole table, a coordinate table, a parts list)."""
    x0, y0, x1, y1 = r
    h = y1 - y0
    reach = max(40.0, 6 * h)  # a row can be several lines deep when a hole's description wraps

    def spans_x(s: Segment) -> bool:
        return min(s[0], s[2]) <= x0 + 1 and max(s[0], s[2]) >= x1 - 1

    def spans_y(s: Segment) -> bool:
        return min(s[1], s[3]) <= y0 + 1 and max(s[1], s[3]) >= y1 - 1

    above = any(spans_x(s) and 0 <= y0 - s[1] <= reach for s in h_lines)
    below = any(spans_x(s) and 0 <= s[1] - y1 <= reach for s in h_lines)
    left = any(spans_y(s) and 0 <= x0 - s[0] <= 4 * reach for s in v_lines)
    right = any(spans_y(s) and 0 <= s[0] - x1 <= 4 * reach for s in v_lines)
    return above and below and left and right


def _line_ends_at(r: Rect, direction: Point, segs: list[Segment], reach: float) -> bool:
    """A line along the value's reading direction ending just before or after it (an ordinate value)."""
    x0, y0, x1, y1 = r
    horizontal = abs(direction[0]) >= abs(direction[1])
    # work along the reading direction: (along, across) coordinates of the box and of each segment
    a0, a1, c0, c1 = (x0, x1, y0, y1) if horizontal else (y0, y1, x0, x1)
    centre = (c0 + c1) / 2
    for s in segs:
        if math.dist(s[:2], s[2:]) < 8:
            continue
        p0, q0, p1, q1 = (s[0], s[1], s[2], s[3]) if horizontal else (s[1], s[0], s[3], s[2])
        in_line = abs(q0 - q1) < 0.3 and abs(q0 - centre) <= 0.5 * (c1 - c0)
        ends_near = min(abs(p0 - a0), abs(p1 - a0), abs(p0 - a1), abs(p1 - a1)) <= reach
        outside = max(p0, p1) <= a0 + 1 or min(p0, p1) >= a1 - 1
        if in_line and ends_near and outside:
            return True
    return False


def _underlined(r: Rect, direction: Point, segs: list[Segment], arrowed: set[int]) -> bool:
    """A stroke along the value's baseline, about as long as the value and with no arrowhead: the
    not-to-scale underline (a dimension line under the value runs on past it and carries arrowheads)."""
    x0, y0, x1, y1 = r
    horizontal = abs(direction[0]) >= abs(direction[1])
    w = (x1 - x0) if horizontal else (y1 - y0)
    for i, s in enumerate(segs):
        if i in arrowed:
            continue
        if horizontal and abs(s[1] - s[3]) < 0.3:
            a, b = sorted((s[0], s[2]))
            if 0 <= s[1] - y1 <= 2.5 and a >= x0 - 2 and b <= x1 + 2 and b - a >= 0.6 * w:
                return True
        if not horizontal and abs(s[0] - s[2]) < 0.3:
            a, b = sorted((s[1], s[3]))
            # text reading up has its baseline on the right; reading down, on the left
            off = (s[0] - x1) if direction[1] < 0 else (x0 - s[0])
            if 0 <= off <= 2.5 and a >= y0 - 2 and b <= y1 + 2 and b - a >= 0.6 * w:
                return True
    return False


def _crossing(r: Rect, direction: Point, segs: list[Segment], skip: set[int]) -> list[Segment]:
    """Strokes running right through the value: across the middle of its characters, in on one side and out
    on the other. A line that stops at the text (an extension line), a stroke inside it (a glyph drawn as
    vectors) and short strokes (arrowheads, a revision triangle beside it) are not crossings."""
    x0, y0, x1, y1 = r
    horizontal = abs(direction[0]) >= abs(direction[1])
    height = (y1 - y0) if horizontal else (x1 - x0)
    # the characters' middle band: more is trimmed on the baseline side, where the box holds the descenders
    if horizontal:
        h, trim = y1 - y0, 0.15 * (x1 - x0)
        inner = (x0 + trim, y0 + 0.25 * h, x1 - trim, y1 - 0.4 * h)
    else:
        w, trim = x1 - x0, 0.15 * (y1 - y0)
        up = direction[1] < 0  # reading upward: the baseline is on the right
        inner = (x0 + (0.25 if up else 0.4) * w, y0 + trim, x1 - (0.4 if up else 0.25) * w, y1 - trim)
    outer = (x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)
    out = []
    for i, s in enumerate(segs):
        if i in skip or math.dist(s[:2], s[2:]) < 2 * height or not _crosses(s, inner):
            continue
        if _inside(s[:2], outer) or _inside(s[2:], outer):
            continue
        out.append(s)
    return out


class _Leaders:
    """Every arrowed segment with the strokes joined to it (its line or leader), and their bounds."""

    def __init__(self, arrows: list[Arrow], segs: list[Segment]) -> None:
        self.segs = segs
        self.on = _arrowed_lines(arrows, segs)
        ends = _ends_index(segs)
        self.ends = ends
        self.groups = {si: _connected(si, segs, ends) for si in self.on}
        self.bounds = {si: _bounds([segs[j] for j in g]) for si, g in self.groups.items()}

    def nearest(self, r: Rect, reach: float, direction: Point | None = None) -> tuple[int, set[int]] | None:
        """The arrowed line or leader closest to `r`, if one comes within `reach`. With the text's reading
        direction, a line along it on the text's baseline side (below a horizontal value, right of one
        reading upward) is preferred: in a stack of parallel dimensions a value sits between two lines, and
        its own is the one under it."""
        best: tuple[float, int, set[int]] | None = None
        for si, group in self.groups.items():
            b = self.bounds[si]
            if b[0] - reach > r[2] or b[2] + reach < r[0] or b[1] - reach > r[3] or b[3] + reach < r[1]:
                continue
            gaps = {j: _seg_rect_gap(self.segs[j], r) for j in group}
            gap = min(gaps.values())
            if gap > reach:
                continue
            # judged on the group's stroke nearest the text: a leader's shoulder, or the dimension line
            closest = min(gaps, key=lambda j: gaps[j])
            score = gap if direction is None or _under(self.segs[closest], r, direction) else gap + reach
            if best is None or score < best[0]:
                best = (score, si, group)
        return (best[1], best[2]) if best else None


def _under(s: Segment, r: Rect, direction: Point) -> bool:
    """The segment runs along the reading direction on the text's baseline side."""
    if not _parallel(s, direction, 0.05):
        return False
    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    mx, my = (s[0] + s[2]) / 2, (s[1] + s[3]) / 2
    # the baseline side: the reading direction turned 90 degrees clockwise on the page (y down)
    nx, ny = -direction[1], direction[0]
    depth = abs((r[2] - r[0]) * nx) + abs((r[3] - r[1]) * ny)  # the box's size across the reading direction
    return (mx - cx) * nx + (my - cy) * ny > -0.3 * depth  # a line through the box's middle counts too


def _reach(r: Rect) -> float:
    return max(3.0, 0.9 * min(r[2] - r[0], r[3] - r[1]))  # about one text height, whichever way it reads


def _slanted_leader(r: Rect, segs: list[Segment]) -> bool:
    """A slanted line (not a table or underline stroke) starting at the text and running away from it: a
    leader drawn without an arrowhead."""
    reach = 2.5 * _reach(r)  # it may start at the end of the note's underline
    for s in segs:
        if math.dist(s[:2], s[2:]) < 20 or abs(s[0] - s[2]) < 2 or abs(s[1] - s[3]) < 2:
            continue
        for end, other in ((s[:2], s[2:]), (s[2:], s[:2])):
            near = _point_rect(end, r) <= reach
            if near and _point_rect(other, r) > 20:
                return True
    return False


def _point_rect(p: Point, r: Rect) -> float:
    dx = max(r[0] - p[0], 0.0, p[0] - r[2])
    dy = max(r[1] - p[1], 0.0, p[1] - r[3])
    return math.hypot(dx, dy)


def read_leadered_text(lines: list[tuple[str, Rect]], leaders: _Leaders, skip: list[Rect]) -> list[Rect]:
    """Body text lines an arrowed leader reaches (a note pointing at the area it means)."""
    out = []
    for text, r in lines:
        if len(text.strip()) < 4 or any(_inside(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), k) for k in skip):
            continue
        if leaders.nearest(r, _reach(r)) is not None or _slanted_leader(r, leaders.segs):
            out.append(r)
    return out


def read_dimension_graphics(
    rows: list[Row],
    dim_ids: dict[int, str],
    segs: list[Segment],
    arrows: list[Arrow],
    leaders: _Leaders,
    circles: list[tuple[Point, float]],
) -> list[DimensionGraphics]:
    arrowed = leaders.on
    arrowed_set = set(arrowed)
    h_lines = [s for s in segs if abs(s[1] - s[3]) < 0.3 and abs(s[0] - s[2]) > 5]
    v_lines = [s for s in segs if abs(s[0] - s[2]) < 0.3 and abs(s[1] - s[3]) > 5]
    out = []
    for row in rows:
        did = dim_ids.get(id(row))
        if did is None:
            continue
        r = row.bbox
        h = min(r[2] - r[0], r[3] - r[1])
        reach = _reach(r)
        best = leaders.nearest(r, reach, row.direction)
        g = DimensionGraphics(dimension_id=did, direction=(_r(row.direction[0]), _r(row.direction[1])))
        if best is not None:
            si, group = best
            on = sorted({a for j in group for a in arrowed.get(j, [])})
            tips = [arrows[a].tip for a in on]
            line = segs[si]
            g.line = (_r(line[0]), _r(line[1]), _r(line[2]), _r(line[3]))
            g.arrowheads = len(on)
            g.arrow_tips = [(_r(t[0]), _r(t[1])) for t in tips]
            g.line_arrowheads = sum(
                1 for a in on if _parallel(line, arrows[a].axis, 0.05) and _across(arrows[a].tip, line) <= 1.0
            )
            if len(on) == 2:
                a, b = (arrows[i] for i in on)
                opposed = a.axis[0] * b.axis[0] + a.axis[1] * b.axis[1] < -0.99  # facing apart or together
                if opposed and all(_across(t.tip, line) <= 1.0 for t in (a, b)):
                    g.span_pts = _r(_dist(a.tip, b.tip))
            g.tip_on_circle = any(
                abs(_dist(t, c) - rad) <= max(0.8, 0.03 * rad) for t in tips for c, rad in circles
            )
            if re.match(r"\s*(?:\d+\s*[xX×]\s*)?R\s*\d", row.text) and len(on) == 1:
                g.arc_radius_pts = _arc_radius(tips[0], arrows[on[0]].axis, segs, leaders.ends, {si})
                if g.arc_radius_pts is not None:
                    g.arc_radius_pts = _r(g.arc_radius_pts)
        g.boxed = _box_around(r, segs, margin=max(2.0, 0.6 * h))
        g.in_table = best is None and _in_cell(r, h_lines, v_lines)
        g.ordinate = best is None and not g.in_table and _line_ends_at(r, row.direction, segs, reach)
        g.underlined = _underlined(r, row.direction, segs, arrowed_set)
        # not its own line or leader: a text box is deeper than its characters (the descender space on the
        # baseline side), so the line the value sits on runs through the box but not through the characters
        skip = set(best[1]) if best else set()
        g.crossed_by = [
            (_r(s[0]), _r(s[1]), _r(s[2]), _r(s[3])) for s in _crossing(r, row.direction, segs, skip)
        ]
        out.append(g)
    return out


def read_field_revision_marks(
    segs: list[Segment], lines: list[tuple[str, Rect]], skip: list[Rect]
) -> list[FieldRevisionMark]:
    """Revision triangles on the drawing field: a short label (1, 2, A) inside three strokes that close up."""
    found: dict[Rect, tuple[float, str]] = {}  # triangle -> (label's distance from its centre, label)
    short = [s for s in segs if 3 <= math.dist(s[:2], s[2:]) <= 60]
    for text, r in lines:
        t = text.strip()
        if not (1 <= len(t) <= 2 and t.isalnum()):
            continue
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        if any(a <= cx <= c and b <= cy <= d for a, b, c, d in skip):
            continue
        size = max(r[2] - r[0], r[3] - r[1])
        zone = (r[0] - 3 * size, r[1] - 3 * size, r[2] + 3 * size, r[3] + 3 * size)
        near = [s for s in short if _inside(s[:2], zone) and _inside(s[2:], zone)]
        for a, b, c in itertools.combinations(near, 3):
            pts = [a[:2], a[2:], b[:2], b[2:], c[:2], c[2:]]
            corners = _corners(pts)
            if len(corners) != 3 or any(sum(_dist(p, k) < TOL for p in pts) != 2 for k in corners):
                continue
            xs, ys = [k[0] for k in corners], [k[1] for k in corners]
            m = 0.3 * size  # the label may overlap the triangle's edge
            if min(xs) - m <= cx <= max(xs) + m and min(ys) - m <= cy <= max(ys) + m:
                sides = sorted(_dist(p, q) for p, q in itertools.combinations(corners, 2))
                box = (_r(min(xs)), _r(min(ys)), _r(max(xs)), _r(max(ys)))
                if sides[2] / sides[0] < 1.4:
                    # the label is the text nearest the triangle's centre (a dimension beside it is not)
                    d = _dist((cx, cy), (sum(xs) / 3, sum(ys) / 3))
                    if box not in found or d < found[box][0]:
                        found[box] = (d, t)
                    break
    return [FieldRevisionMark(label=t, bbox=box) for box, (_, t) in found.items()]


def _visual(page: pymupdf.Page, r: pymupdf.Rect) -> Rect:
    v = r * page.rotation_matrix
    v.normalize()
    return (_r(v.x0), _r(v.y0), _r(v.x1), _r(v.y1))


def read_graphics(
    page: pymupdf.Page,
    rows: list[Row],
    dim_ids: dict[int, str],
    segs: list[Segment],
    lines: list[tuple[str, Rect]],
    skip: list[Rect],
) -> PageGraphics:
    drawings = page.get_drawings()
    rmat = page.rotation_matrix
    arrows = read_arrowheads(drawings, rmat, segs)
    circles = read_circles(segs)
    leaders = _Leaders(arrows, segs)
    dims = read_dimension_graphics(rows, dim_ids, segs, arrows, leaders, circles)
    styles: dict[str, int] = {}
    for a in arrows:
        styles[a.style] = styles.get(a.style, 0) + 1
    return PageGraphics(
        arrowheads=[
            ArrowheadItem(
                tip=(_r(a.tip[0]), _r(a.tip[1])),
                axis=(round(a.axis[0], 3), round(a.axis[1], 3)),
                length=_r(a.length),
                style=a.style,  # type: ignore[arg-type]
            )
            for a in arrows
        ],
        arrowhead_styles=styles,
        circles=[CircleItem(centre=(_r(c[0]), _r(c[1])), radius=_r(rad)) for c, rad in circles],
        dimensions=dims,
        revision_marks=read_field_revision_marks(segs, [*lines, *((r.text, r.bbox) for r in rows)], skip),
        datum_triangles=[_visual(page, t) for t in _filled_triangles(page)],
        revision_cells=[(_r(a), _r(b), _r(c), _r(d)) for a, b, c, d in revision_marks(page)],
        leadered_text=[
            (_r(r[0]), _r(r[1]), _r(r[2]), _r(r[3])) for r in read_leadered_text(lines, leaders, skip)
        ],
    )
