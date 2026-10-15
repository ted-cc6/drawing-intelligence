"""A cheap, rule-based title-block proxy for Spike C (no LLM, $0).

Stage 1 has no parsed title-block fields - those come from the vision LLM in stage 2. So we approximate
"can we read the title block?" with geometry only, using the text lines stage 1 already places in the
bottom-right `title_block` region.

The proxy has two parts:

1. **Template labels.** The Wipro PARI block prints a fixed set of field labels (MATERIAL, SCALE,
   SHEET SIZE, ...). We count how many are present as substrings of the region's text. Few labels found
   means a different template or a crop that missed the block.
2. **Field values.** For five key fields we look for a value line near the label. The search box is
   anchored to the *label's* position, not to absolute page coordinates, so it still lines up when the
   same block is printed on a bigger sheet (A2, A1) further down and to the right.

`tb_status` summarises the two parts: empty / no_template / missing_values / ok. The thresholds were
measured once on the A3 sample and are checked against `data/labels/title_block_truth.json` by
`check_proxy.py` before the proxy is trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from drawing_intelligence.schemas import TextLine

# Distinctive fixed labels printed on the Wipro PARI block. Matched as substrings (case-insensitive),
# because some print merged on one line ("SURFACE TREATMENT MACHINING", "DESIGN UNIT DESIGN UNIT CD.").
EXPECTED_LABELS = (
    "DRG./PART CODE",
    "DESCRIPTION",
    "MATERIAL",
    "SCALE",
    "SHEET SIZE",
    "REV.",
    "SHEET",
    "SURFACE TREATMENT",
    "HEAT TREATMENT",
    "NET WEIGHT",
    "DRN.BY",
    "CHKD.BY",
    "APPD.BY",
    "DESIGN UNIT",
    "PART CLASS.",
    "WIPRO PARI GROUP",
)

# A value is spurious if it is itself one of these labels (or template boilerplate) rather than real data.
_BOILERPLATE = {lab.upper() for lab in EXPECTED_LABELS} | {
    "DESCRIPTION",
    "DRAWING TYPE",
    "SURFACE AREA",
    "REFERENCE DWG.",
    "TEAM NO.",
    "LIMITS",
    "DATE",
    "PUNE",
    "MACHINING",
}


@dataclass
class ValueBox:
    """Where a field's value sits relative to its label's (x0, y0), in PDF points.

    The box is on the label-line center. dx is positive to the right; dy is positive downward.
    """

    label: str
    dx0: float
    dy0: float
    dx1: float
    dy1: float


# Offsets measured on the A3 sample (10K_CAM PLATE.pdf). Four fields print their value just below the
# label; the title (DESCRIPTION) prints to the right on the same row.
VALUE_BOXES = {
    "number": ValueBox("DRG./PART CODE", dx0=-40, dy0=8, dx1=70, dy1=40),
    "material": ValueBox("MATERIAL", dx0=-20, dy0=6, dx1=45, dy1=28),
    "scale": ValueBox("SCALE", dx0=-20, dy0=6, dx1=45, dy1=28),
    "sheet_size": ValueBox("SHEET SIZE", dx0=-15, dy0=6, dx1=45, dy1=30),
    "title": ValueBox("DESCRIPTION", dx0=55, dy0=-6, dx1=320, dy1=24),
}

KEY_FIELDS = tuple(VALUE_BOXES)  # number, material, scale, sheet_size, title


@dataclass
class TitleBlockRead:
    status: str  # empty | no_template | missing_values | ok
    labels_found: int
    labels_total: int
    values: dict[str, str | None] = field(default_factory=dict)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def _find_label_lines(lines: list[TextLine], label: str) -> list[TextLine]:
    """Every region line containing the label. A field label can print more than once (e.g. the
    revision table repeats DESCRIPTION), so we search around all of them and keep the nearest value."""
    up = label.upper()
    return [ln for ln in lines if up in _norm(ln.text).upper()]


def _value_near(lines: list[TextLine], label_lines: list[TextLine], box: ValueBox) -> str | None:
    best: tuple[float, str] | None = None
    for label_line in label_lines:
        lx0, ly0 = label_line.bbox[0], label_line.bbox[1]
        for ln in lines:
            if ln is label_line:
                continue
            text = _norm(ln.text)
            if not text or text.upper() in _BOILERPLATE:
                continue
            cx, cy = _center(ln.bbox)
            if lx0 + box.dx0 <= cx <= lx0 + box.dx1 and ly0 + box.dy0 <= cy <= ly0 + box.dy1:
                dist = abs(cx - lx0) + abs(cy - ly0)
                if best is None or dist < best[0]:
                    best = (dist, text)
    return best[1] if best else None


def read_title_block(title_block_text: list[TextLine]) -> TitleBlockRead:
    lines = title_block_text
    if not lines:
        return TitleBlockRead("empty", 0, len(EXPECTED_LABELS), dict.fromkeys(KEY_FIELDS))

    blob = " | ".join(_norm(ln.text).upper() for ln in lines)
    labels_found = sum(1 for lab in EXPECTED_LABELS if lab.upper() in blob)

    values: dict[str, str | None] = {}
    for field_name, box in VALUE_BOXES.items():
        label_lines = _find_label_lines(lines, box.label)
        values[field_name] = _value_near(lines, label_lines, box) if label_lines else None

    if labels_found < len(EXPECTED_LABELS) / 2:
        status = "no_template"
    elif any(values[f] is None for f in KEY_FIELDS):
        status = "missing_values"
    else:
        status = "ok"
    return TitleBlockRead(status, labels_found, len(EXPECTED_LABELS), values)
