"""Drawn lengths: each dimension's line length against its value, from stage 1's matched dimension lines."""

from __future__ import annotations

import math
from dataclasses import dataclass

from drawing_intelligence.extraction.geometry import nominal_value
from drawing_intelligence.schemas import PageExtraction, TextItem

MM_PTS = 72 / 25.4  # one millimetre on paper, in PDF points


@dataclass(frozen=True)
class Drawn:
    dim: TextItem
    value: float
    length: float  # of the dimension line, in PDF points
    orientation: str

    @property
    def paper_scale(self) -> float:
        """The scale this dimension is drawn at on paper: 1.0 for 1:1, 2.0 for 2:1."""
        return self.length / (self.value * MM_PTS)


def drawn_dimensions(page: PageExtraction) -> list[Drawn]:
    """Linear dimensions with a matched line. Radius and diameter callouts (leader lines, not lengths),
    angles, and reference dimensions (derived values) are left out."""
    dims = {d.id: d for d in page.dimensions if d.id}
    out = []
    for m in page.matched_lines:
        d = dims.get(m.dimension_id)
        if d is None:
            continue
        t = d.text.strip()
        if d.is_reference or t.startswith(("(", "R", "⌀")) or "°" in t:  # angles aren't lengths either
            continue
        v = nominal_value(t)
        if not v or v <= 0:
            continue
        out.append(Drawn(d, v, math.dist(m.line[:2], m.line[2:]), m.orientation))
    return out


# ISO 5455 scales, as paper/real ratios (2.0 = 2:1).
STANDARD_SCALES: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 0.5, 0.2, 0.1, 0.05, 0.02)


def supported_scales(drawn: list[Drawn], min_support: int = 3, tol: float = 0.01) -> dict[float, list[Drawn]]:
    """Standard scales that `min_support` or more dimensions are drawn at (within `tol`), with them.

    More robust than the sheet's median scale: small dimensions with their arrows outside and leader lines
    give wild ratios, but they rarely land on a standard scale together.
    """
    out = {}
    for s in STANDARD_SCALES:
        on = [d for d in drawn if abs(d.paper_scale / s - 1) <= tol]
        if len(on) >= min_support:
            out[s] = on
    return out
