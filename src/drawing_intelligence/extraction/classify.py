"""Is a text item a dimension, a view label, a note, or something else?

The patterns were tuned by hand on real drawings in notebook 01 and are kept unchanged (ADR 0005).
"""

from __future__ import annotations

import re
from typing import Literal

Category = Literal["dimension_value", "view_label", "note", "other_numeric", "text_other", "empty"]

# Anything that looks like a real dimension value: plain number / toleranced / angular / count+diameter /
# fit class / linked tolerance pair.
DIM_PATTERN = re.compile(
    r"^\(?[⌀R]?\s*\d+([.,]\d+)?\)?(\s*[±]\s*\d+([.,]\d+)?)?"
    r"(\s*(x|X)\s*\d+°?)?°?$"
    r"|^[+\-]?\d+([.,]\d+)?$"
    r"|^H\d+$"
    r"|^\d+-⌀[\d.,]+$"
    r"|^⌀\s*\d+([.,]\d+)?\s*H\d+.*$"
    r"|^\d+([.,]\d+)?\s*\([+\-][\d.,]+/[+\-]?[\d.,]+\)$"
)

# Fixed vocabulary of view/annotation labels - not measurements.
LABEL_KEYWORDS = ("SCALE", "SECTION", "DETAIL", "TYP", "NOS", "VIEW")

# A view label must LOOK like a label ("SECTION A-A", "SCALE 1:1", "TYP", "02 NOS"), not just contain the
# word - otherwise notes such as "2.DO NOT SCALE" are mislabelled.
LABEL_PATTERN = re.compile(
    r"^(SECTION|DETAIL|VIEW)\b.{0,12}$|^SCALE\s*\d+\s*:\s*\d+$|^TYP\.?$|^\d+\s*NOS\.?$"
)


def classify(text: str) -> Category:
    # Check "looks like a dimension" BEFORE keywords, so a dimension containing a keyword substring
    # (e.g. "THRU") is not tagged as a label.
    t = text.strip()
    if not t:
        return "empty"
    has_digit = any(ch.isdigit() for ch in t)
    if has_digit and DIM_PATTERN.match(t.replace(" ", "")):
        return "dimension_value"
    if LABEL_PATTERN.match(t.upper()):
        return "view_label"
    if sum(ch.isalpha() for ch in t) >= 4:
        return "note"
    if has_digit:
        return "other_numeric"
    return "text_other"
