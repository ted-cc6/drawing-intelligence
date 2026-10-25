"""The general tolerance table (IS 2102) printed in the template's right strip, read into rows.

The strip holds four sections, each opened by a header such as "UNSPECIFIED TOL.(M/C)" / "FOR LINEAR IN mm.",
followed by rows that pair a size range ("6 UP TO 30") with a tolerance ("±0.2") printed on the same line.
Read from the text alone, so it does not depend on where the strip sits on the sheet.
"""

from __future__ import annotations

import re

from drawing_intelligence.schemas import GeneralToleranceRow, TextLine

_RANGE = re.compile(
    r"^(?:(?P<over>\d+(?:\.\d+)?)\s+)?UP\s+TO\s+(?P<to>\d+(?:\.\d+)?)$|^OVER\s+(?P<only>\d+(?:\.\d+)?)$"
)
_VALUE = re.compile(r"^±\s*\S+$")
_MM = re.compile(r"^±\s*(\d+(?:\.\d+)?)$")
ROW_TOL_PTS = 3.0


def _cy(line: TextLine) -> float:
    return (line.bbox[1] + line.bbox[3]) / 2


def read_general_tolerances(lines: list[TextLine]) -> list[GeneralToleranceRow]:
    """Every row of the general tolerance table, with the section (process and kind) it belongs to."""
    headers: list[tuple[float, str, str]] = []  # (y, process, kind)
    process = None
    for line in sorted(lines, key=_cy):
        t = line.text.upper()
        if "UNSPECIFIED TOL" in t:
            process = "fabrication" if "FAB" in t else "machining" if "M/C" in t else None
        elif t.startswith("FOR ") and process and ("LINEAR" in t or "ANGULAR" in t):
            headers.append((_cy(line), process, "linear" if "LINEAR" in t else "angular"))
    values = [ln for ln in lines if _VALUE.match(ln.text.strip())]
    rows = []
    for line in lines:
        m = _RANGE.match(line.text.strip().upper())
        if not m:
            continue
        section = [h for h in headers if h[0] < _cy(line)]
        value = min(
            (v for v in values if abs(_cy(v) - _cy(line)) <= ROW_TOL_PTS and v.bbox[0] > line.bbox[2]),
            key=lambda v: v.bbox[0] - line.bbox[2],
            default=None,
        )
        if not section or value is None:
            continue
        _, proc, kind = max(section)
        over = float(m["over"] or m["only"] or 0)
        up_to = float(m["to"]) if m["to"] else None
        mm = _MM.match(value.text.strip())
        rows.append(
            GeneralToleranceRow(
                process=proc,  # type: ignore[arg-type]
                kind=kind,  # type: ignore[arg-type]
                over=over,
                up_to=up_to,
                tolerance=value.text.strip(),
                value_mm=float(mm[1]) if mm and kind == "linear" else None,
                bbox=line.bbox,
            )
        )
    return sorted(rows, key=lambda r: (r.process, r.kind, r.over))
