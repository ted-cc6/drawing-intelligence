"""Matching dimension values to their dimension lines, and the chain-sum consistency check.

Logic kept from notebook 01 v2 (strict absolute tolerance for chain sums, default 0.05 mm).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from drawing_intelligence.extraction.text_layer import Row, Segment
from drawing_intelligence.schemas import ChainCheck

Orientation = Literal["horizontal", "vertical"]

_NUM = re.compile(r"[+\-]?\d+(?:[.,]\d+)?")


@dataclass(eq=False)
class Match:
    row: Row
    value: float
    line: Segment
    orientation: Orientation


def nominal_value(text: str) -> float | None:
    """The plain leading number of a dimension, e.g. "40±0.1" -> 40.0.

    Angular, count-diameter and fit callouts return None: the line matcher does not handle them yet.
    """
    t = text.strip().lstrip("(").rstrip(")")
    if "x" in t.lower() or ("H" in t) or ("⌀" in t and "-" in t):
        return None
    m = _NUM.match(t.lstrip("R⌀ ").strip())
    return float(m.group().replace(",", ".")) if m else None


def match_dimension_lines(
    rows: list[Row], segments: list[Segment], max_perp_offset: float = 15
) -> list[Match]:
    """For each dimension, the nearby straight line in the same direction as the text.

    Radius/diameter callouts with a diagonal leader line are not reliably matched.
    """
    matches = []
    for r in rows:
        if r.category != "dimension_value":
            continue
        val = nominal_value(r.text)
        if val is None:
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        is_wide = (r.x1 - r.x0) > (r.y1 - r.y0)
        best, best_dist = None, 1e9
        for x0, y0, x1, y1 in segments:
            horiz, vert = abs(y0 - y1) < 0.5, abs(x0 - x1) < 0.5
            if max(abs(x1 - x0), abs(y1 - y0)) < 5:
                continue
            if is_wide and horiz and min(x0, x1) - 5 <= cx <= max(x0, x1) + 5:
                dist = abs(y0 - cy)
                if dist < max_perp_offset and dist < best_dist:
                    best, best_dist = (x0, y0, x1, y1), dist
            elif (not is_wide) and vert and min(y0, y1) - 5 <= cy <= max(y0, y1) + 5:
                dist = abs(x0 - cx)
                if dist < max_perp_offset and dist < best_dist:
                    best, best_dist = (x0, y0, x1, y1), dist
        if best:
            matches.append(Match(r, val, best, "horizontal" if is_wide else "vertical"))
    return matches


def calibrate_scale(matches: list[Match]) -> float | None:
    """Page scale in points per mm: median of line length / printed value (robust to a few bad matches)."""
    ratios = sorted(
        (((m.line[2] - m.line[0]) ** 2 + (m.line[3] - m.line[1]) ** 2) ** 0.5) / m.value
        for m in matches
        if m.value > 0
    )
    return ratios[len(ratios) // 2] if ratios else None


def _span(m: Match, orientation: Orientation) -> tuple[float, float]:
    a, b = (m.line[0], m.line[2]) if orientation == "horizontal" else (m.line[1], m.line[3])
    return min(a, b), max(a, b)


def find_chains(
    matches: list[Match], offset_tol: float = 1.0, endpoint_tol: float = 1.5
) -> list[tuple[Orientation, list[Match]]]:
    """Group collinear dimensions (same direction and offset) that touch end to end."""
    chains: list[tuple[Orientation, list[Match]]] = []
    orientations: tuple[Orientation, ...] = ("horizontal", "vertical")
    for orientation in orientations:
        buckets: dict[float, list[Match]] = {}
        for m in (m for m in matches if m.orientation == orientation):
            pos = m.line[1] if orientation == "horizontal" else m.line[0]
            buckets.setdefault(round(pos / offset_tol) * offset_tol, []).append(m)
        o: Orientation = orientation
        for members in buckets.values():
            members.sort(key=lambda m: _span(m, o)[0])
            chain = [members[0]]
            for m in members[1:]:
                if abs(_span(m, orientation)[0] - _span(chain[-1], orientation)[1]) < endpoint_tol:
                    chain.append(m)
                else:
                    if len(chain) > 1:
                        chains.append((orientation, chain))
                    chain = [m]
            if len(chain) > 1:
                chains.append((orientation, chain))
    return chains


def check_chain_vs_overall(
    chains: list[tuple[Orientation, list[Match]]], matches: list[Match], abs_tol: float = 0.05
) -> list[ChainCheck]:
    """For each chain, find an overall dimension spanning the same range and check the sum.

    Pass rule: |chain sum - overall| <= abs_tol (mm). The original 2 % rule let 6995 vs 7000 pass.
    """
    results = []
    for orientation, chain in chains:
        span0 = min(_span(m, orientation)[0] for m in chain)
        span1 = max(_span(m, orientation)[1] for m in chain)
        chain_sum = sum(m.value for m in chain)
        overall = next(
            (
                m
                for m in matches
                if m.orientation == orientation
                and m not in chain
                and abs(_span(m, orientation)[0] - span0) < 2
                and abs(_span(m, orientation)[1] - span1) < 2
            ),
            None,
        )
        if overall:
            diff = abs(chain_sum - overall.value)
            results.append(
                ChainCheck(
                    chain_texts=[m.row.text for m in chain],
                    chain_sum=round(chain_sum, 3),
                    overall_text=overall.row.text,
                    overall_value=overall.value,
                    match=diff <= abs_tol,
                    diff=round(diff, 3),
                )
            )
    return results
