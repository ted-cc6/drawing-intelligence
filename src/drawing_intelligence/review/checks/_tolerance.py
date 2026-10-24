"""Dimension tolerances read from the exact dimension text, and the general tolerance that covers a size."""

from __future__ import annotations

import re
from dataclasses import dataclass

from drawing_intelligence.schemas import GeneralToleranceRow, PageExtraction, TextItem

_NUM = r"[+\-]?\d+(?:\.\d+)?"
# nominal, then an optional ISO fit (H7, g6), then ±t or (upper/lower) as stage 1 joins stacked limits
_DIM = re.compile(
    rf"^(?P<prefix>[⌀R]\s*)?(?P<nominal>\d+(?:\.\d+)?)\s*(?P<fit>[A-Za-z]{{1,2}}\d{{1,2}})?\s*"
    rf"(?:±\s*(?P<pm>\d+(?:\.\d+)?)|\(\s*(?P<upper>{_NUM})\s*/\s*(?P<lower>{_NUM})\s*\))?\s*$"
)


def decimals(number: str) -> int:
    return len(number.split(".", 1)[1]) if "." in number else 0


@dataclass(frozen=True)
class Tolerance:
    """A linear size and its tolerance, as printed. Deviations are signed: upper +0.1, lower -0.1."""

    dim: TextItem
    nominal: float
    nominal_text: str
    fit: str | None
    upper: float | None
    lower: float | None
    deviation_texts: tuple[str, ...]

    @property
    def explicit(self) -> bool:
        return self.upper is not None and self.lower is not None

    @property
    def band(self) -> float | None:
        return None if self.upper is None or self.lower is None else self.upper - self.lower

    @property
    def deviation_decimals(self) -> int:
        return max((decimals(t.lstrip("+-")) for t in self.deviation_texts), default=0)


def parse(dim: TextItem) -> Tolerance | None:
    """The size and tolerance of a linear, radius or diameter dimension. None for anything else (chamfers
    "3 x 45°", angles, counts "2-⌀15", reference dimensions "(35)", threads, text after the value)."""
    text = dim.text.strip()
    if dim.is_reference or text.startswith("(") or "°" in text or "x" in text.lower():
        return None
    m = _DIM.match(text)
    if not m:
        return None
    if m["pm"] is not None:
        upper, lower, devs = float(m["pm"]), -float(m["pm"]), (m["pm"],)
    elif m["upper"] is not None:
        # the text keeps the PDF's order; stage 1 orders the pair by where it is printed
        hi, lo = dim.limits or (m["upper"], m["lower"])
        upper, lower, devs = float(hi), float(lo), (hi, lo)
    else:
        upper = lower = None
        devs = ()
    nominal = float(m["nominal"])
    if upper is not None and lower is not None and max(abs(upper), abs(lower)) > max(1.0, 0.05 * nominal):
        return (
            None  # not a tolerance: coordinate-table values joined like a limit pair ("0.00 (-35.00/-35.00)")
        )
    return Tolerance(dim, nominal, m["nominal"], m["fit"], upper, lower, devs)


def tolerances(page: PageExtraction) -> list[Tolerance]:
    return [t for d in page.dimensions if (t := parse(d)) is not None]


def process(page: PageExtraction) -> str:
    """Which general tolerances apply: fabrication drawings use the FAB rows, everything else machining."""
    f = page.title_block_fields.get("drawing_type")
    return "fabrication" if f and f.value and "FAB" in f.value.upper() else "machining"


def general_for(page: PageExtraction, size: float) -> GeneralToleranceRow | None:
    """The general linear tolerance row for `size`: over < size <= up to (the first row from its start)."""
    rows = [r for r in page.general_tolerances if r.kind == "linear" and r.process == process(page)]
    for i, r in enumerate(rows):
        low_ok = size >= r.over if i == 0 else size > r.over
        if low_ok and (r.up_to is None or size <= r.up_to):
            return r
    return None
