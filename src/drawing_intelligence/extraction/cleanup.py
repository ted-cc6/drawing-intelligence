"""Repairing dimensions that the PDF splits into several text objects, and finding reference dimensions.

Logic kept unchanged from notebook 01 (ADR 0005); only the data structure moved from dicts to `Row`.
"""

from __future__ import annotations

import re

from drawing_intelligence.extraction.classify import LABEL_KEYWORDS
from drawing_intelligence.extraction.text_layer import Row, Segment


def _is_protected_label(text: str) -> bool:
    return text.strip().upper() in LABEL_KEYWORDS


def merge_adjacent_spans(rows: list[Row], max_gap: float = 3.0) -> list[Row]:
    """Merge tokens close together on the same row, e.g. "2-⌀" + "15" drawn in two fonts.

    A standalone label (TYP, SCALE...) is never merged into a neighbour, otherwise a value sitting next to
    its own "TYP" caption would be destroyed.
    """
    rows = sorted(rows, key=lambda r: (round(r.y0), r.x0))
    merged: list[Row] = []
    used = [False] * len(rows)
    for i, r in enumerate(rows):
        if used[i]:
            continue
        used[i] = True
        cur = Row(r.text, r.x0, r.y0, r.x1, r.y1, r.font_size, r.is_reference)
        if _is_protected_label(r.text):
            merged.append(cur)
            continue
        changed = True
        while changed:
            changed = False
            for j, r2 in enumerate(rows):
                if used[j] or _is_protected_label(r2.text):
                    continue
                y_overlap = min(cur.y1, r2.y1) - max(cur.y0, r2.y0)
                gap = r2.x0 - cur.x1
                if y_overlap > 0.5 * min(cur.y1 - cur.y0, r2.y1 - r2.y0) and 0 <= gap < max_gap:
                    cur.text += r2.text
                    cur.x1 = max(cur.x1, r2.x1)
                    cur.y0, cur.y1 = min(cur.y0, r2.y0), max(cur.y1, r2.y1)
                    used[j] = True
                    changed = True
        merged.append(cur)
    return merged


_SIGNED = re.compile(r"^[+\-]\d+([.,]\d+)?$")  # anchor: explicit sign
_TOL_PARTNER = re.compile(r"^[+\-]?\d+([.,]\d+)?$")  # partner: sign optional (bare "0" allowed)
_NOMINAL = re.compile(r"^\(?[⌀R]?\s*\d+([.,]\d+)?\)?$|^H\d+$|^[⌀R]\s*\d+([.,]\d+)?\s*H\d+$")


def link_stacked_tolerances(rows: list[Row], max_gap: float = 15) -> list[Row]:
    """Join a nominal value with its upper/lower limit pair, e.g. "11" + "-0.2" + "-0.1" -> "11 (-0.2/-0.1)".

    Handles both layouts seen so far: pair stacked vertically with the nominal to the LEFT (horizontal
    dimensions), or pair side by side with the nominal BELOW (rotated dimensions).
    """
    tol_tokens = [r for r in rows if _SIGNED.match(r.text.strip())]
    partners = [r for r in rows if _TOL_PARTNER.match(r.text.strip())]
    result: list[Row] = []
    consumed: set[int] = set()

    def gap_overlap(a0, a1, b0, b1, c0, c1, d0, d1):
        return max(a0, b0) - min(a1, b1), min(c1, d1) - max(c0, d0)

    for t1 in tol_tokens:
        if id(t1) in consumed:
            continue
        for t2 in partners:
            if t2 is t1 or id(t2) in consumed:
                continue
            gap_v, ov_v = gap_overlap(t1.y0, t1.y1, t2.y0, t2.y1, t1.x0, t1.x1, t2.x0, t2.x1)
            gap_h, ov_h = gap_overlap(t1.x0, t1.x1, t2.x0, t2.x1, t1.y0, t1.y1, t2.y0, t2.y1)
            if not ((-1 <= gap_v < max_gap and ov_v > 0) or (-1 <= gap_h < max_gap and ov_h > 0)):
                continue
            px0, px1 = min(t1.x0, t2.x0), max(t1.x1, t2.x1)
            py0, py1 = min(t1.y0, t2.y0), max(t1.y1, t2.y1)
            for nom in rows:
                if nom is t1 or nom is t2 or id(nom) in consumed:
                    continue
                if not _NOMINAL.match(nom.text.strip()):
                    continue
                left_ok = -1 <= (px0 - nom.x1) < max_gap and min(nom.y1, py1) - max(nom.y0, py0) > 0
                below_ok = -1 <= (nom.y0 - py1) < max_gap and min(nom.x1, px1) - max(nom.x0, px0) > 0
                if left_ok or below_ok:
                    result.append(
                        Row(
                            f"{nom.text} ({t1.text}/{t2.text})",
                            min(nom.x0, px0),
                            min(nom.y0, py0),
                            max(nom.x1, px1),
                            max(nom.y1, py1),
                            nom.font_size,
                        )
                    )
                    consumed.update([id(nom), id(t1), id(t2)])
                    break
            if id(t1) in consumed:
                break
    return result + [r for r in rows if id(r) not in consumed]


def flag_reference_dims(rows: list[Row], segments: list[Segment], y_pad: float = 2) -> list[Row]:
    """Mark reference dimensions such as "(35)", whose parentheses are drawn as vector arcs, not text.

    Requires a real multi-segment arc (>= 3 short segments spanning most of the text height) on BOTH sides;
    a single stray tick mark near a number is not a parenthesis.
    """
    short = list(
        {
            (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
            for x0, y0, x1, y1 in segments
            if ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 < 3.0
        }
    )

    def flank_arc_height(x_near: float, y0: float, y1: float) -> float:
        pts_y: list[float] = []
        for sx0, sy0, _sx1, sy1 in short:
            if abs(sx0 - x_near) < 2.5 and y0 - y_pad - 3 < sy0 < y1 + y_pad + 3:
                pts_y += [sy0, sy1]
        return (max(pts_y) - min(pts_y)) if len(pts_y) >= 3 else 0

    for r in rows:
        if r.text.strip().replace(".", "").isdigit():
            h = r.y1 - r.y0
            if flank_arc_height(r.x0, r.y0, r.y1) > 0.6 * h and flank_arc_height(r.x1, r.y0, r.y1) > 0.6 * h:
                r.text = f"({r.text})"
                r.is_reference = True
    return rows
