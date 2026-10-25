"""Drawing zones ("C4"): the grid an engineer uses to find something on the sheet.

The zone markers are printed in the sheet border (numbers along the top and bottom, letters up the sides), so
they are read from the page itself rather than assumed from the sheet size.
"""

from __future__ import annotations

import re

from drawing_intelligence.extraction.template import Template
from drawing_intelligence.schemas import PageExtraction

_COLUMN = re.compile(r"^\d{1,2}$")
_ROW = re.compile(r"^[A-Z]$")


def _centre(b: tuple[float, float, float, float] | list[float]) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def markers(page: PageExtraction, template: Template) -> tuple[dict[str, float], dict[str, float]]:
    """Zone column markers (label -> x) and row markers (label -> y) found in the border."""
    regions = template.regions_for(*page.page_size_pts)
    lines = [*page.body_text, *page.title_block_text, *page.tolerance_table_text]

    def found(names: tuple[str, ...], pattern: re.Pattern[str], axis: int) -> dict[str, float]:
        out: dict[str, float] = {}
        for line in lines:
            text = line.text.strip()
            c = _centre(line.bbox)
            in_border = any(
                n in regions
                and regions[n][0] <= c[0] <= regions[n][2]
                and regions[n][1] <= c[1] <= regions[n][3]
                for n in names
            )
            if in_border and pattern.match(text):
                out.setdefault(text, c[axis])
        return out

    return found(("border_top", "border_bottom"), _COLUMN, 0), found(("border_left", "border_right"), _ROW, 1)


def zone(
    page: PageExtraction, template: Template, bbox: list[float] | None, found: tuple[dict, dict] | None = None
) -> str | None:
    """The zone of a bbox's centre, e.g. "C4", or None when the sheet has no zone markers."""
    if bbox is None:
        return None
    columns, rows = found or markers(page, template)
    if not columns or not rows:
        return None
    x, y = _centre(bbox)
    column = min(columns, key=lambda k: abs(columns[k] - x))
    row = min(rows, key=lambda k: abs(rows[k] - y))
    return f"{row}{column}"
