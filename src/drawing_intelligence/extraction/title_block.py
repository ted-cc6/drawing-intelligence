"""Title-block fields read by position: each template cell collects the words whose centre lies in it.

Exact and free, like the rest of stage 1. Lines are no good here: the PDF often joins the words of two
neighbouring cells into one line (e.g. the checked and approved dates), so this works on single words.
A sheet whose template labels are not where the template expects them is a variant title block, and no
fields are read from it rather than wrong ones.
"""

from __future__ import annotations

import re
from typing import Literal, NamedTuple

import pymupdf

from drawing_intelligence.extraction.template import Rect, Template, resolve_rect
from drawing_intelligence.schemas import TextLine, TitleBlockField

Word = tuple[str, Rect]
ANCHOR_TOL_PTS = 4.0


def page_words(page: pymupdf.Page) -> list[Word]:
    """Every word on the page with its bbox, corrected for the page's /Rotate flag."""
    rmat = page.rotation_matrix
    out = []
    for w in page.get_text("words"):
        r = pymupdf.Rect(w[:4]) * rmat
        out.append((w[4], (r.x0, r.y0, r.x1, r.y1)))
    return out


def _centre_in(bbox: Rect, cell: Rect) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return cell[0] <= cx <= cell[2] and cell[1] <= cy <= cell[3]


def _round(b: Rect) -> Rect:
    return (round(b[0], 1), round(b[1], 1), round(b[2], 1), round(b[3], 1))


def layout(
    words: list[Word], template: Template, width: float, height: float
) -> Literal["standard", "variant"]:
    found = 0
    for text, x, y in template.anchors_for(width, height):
        found += any(
            t == text and abs(b[0] - x) <= ANCHOR_TOL_PTS and abs(b[1] - y) <= ANCHOR_TOL_PTS
            for t, b in words
        )
    return "standard" if found >= template.title_block_min_anchors else "variant"


def read_fields(
    words: list[Word], template: Template, width: float, height: float
) -> dict[str, TitleBlockField]:
    """One field per template cell: its words in reading order, or None (with the cell's bbox) when empty."""
    fields: dict[str, TitleBlockField] = {}
    for name, cell in template.field_cells(width, height).items():
        inside = sorted(
            (w for w in words if _centre_in(w[1], cell)),
            key=lambda w: (round((w[1][1] + w[1][3]) / 10), w[1][0]),
        )
        value = " ".join(t for t, _ in inside).strip()
        prefix = template.title_block_prefixes.get(name)
        if prefix and value.startswith(prefix):
            value = value[len(prefix) :].strip()
        if not value:
            fields[name] = TitleBlockField(value=None, bbox=_round(cell))
            continue
        bbox = (
            min(b[0] for _, b in inside),
            min(b[1] for _, b in inside),
            max(b[2] for _, b in inside),
            max(b[3] for _, b in inside),
        )
        fields[name] = TitleBlockField(value=value, bbox=_round(bbox))
    return fields


def read_units(lines: list[TextLine], template: Template) -> TitleBlockField | None:
    """The unit from the notes' unit statement, e.g. "ALL DIMENSIONS ARE IN mm" -> mm."""
    if not template.units_pattern:
        return None
    pattern = re.compile(template.units_pattern)
    for line in lines:
        m = pattern.search(line.text)
        if m:
            return TitleBlockField(value=m.group(1), bbox=line.bbox)
    return None


def read_marked_notes(
    fields: dict[str, TitleBlockField], lines: list[TextLine], template: Template
) -> dict[str, TitleBlockField]:
    """Fields whose cell holds the "see notes" marker take the value of their note ("# MATERIAL: M.S.")."""
    marker = template.notes_marker
    if not marker:
        return fields
    out = dict(fields)
    for label, name in template.notes_fields.items():
        cell = fields.get(name)
        if cell is None or not (cell.value or "").startswith(marker):
            continue
        pattern = re.compile(
            rf"{re.escape(marker)}\s*{re.escape(label)}\s*:\s*([^{re.escape(marker)}]*)", re.IGNORECASE
        )
        for line in lines:
            m = pattern.search(line.text)
            if m and m.group(1).strip():
                out[name] = TitleBlockField(value=m.group(1).strip(), bbox=line.bbox, source="notes")
                break
    return out


def read_revision_rows(
    lines: list[TextLine], template: Template, width: float, height: float
) -> tuple[list[TextLine], list[TextLine]]:
    """The revision table's filled lines (placeholder dots dropped), and the revision numbers among them."""
    if template.revision_rows is None:
        return [], []
    region = resolve_rect(template.revision_rows, width, height)
    rows = [ln for ln in lines if _centre_in(ln.bbox, region) and re.search(r"\w", ln.text)]
    if template.revision_number_column is None:
        return rows, []
    column = resolve_rect(template.revision_number_column, width, height)
    numbers = [ln for ln in rows if _centre_in(ln.bbox, column) and re.fullmatch(r"\d{1,3}", ln.text.strip())]
    return rows, numbers


class TitleBlockRead(NamedTuple):
    layout: Literal["standard", "variant"] | None
    fields: dict[str, TitleBlockField]
    revision_rows: list[TextLine]
    revision_numbers: list[TextLine]


def read_title_block(page: pymupdf.Page, lines: list[TextLine], template: Template) -> TitleBlockRead:
    """Layout, fields and revision table of one page. A template without field cells reads nothing."""
    if not template.title_block_fields:
        return TitleBlockRead(None, {}, [], [])
    w, h = page.rect.width, page.rect.height
    words = page_words(page)
    kind = layout(words, template, w, h)
    if kind == "variant":
        return TitleBlockRead(kind, {}, [], [])
    fields = read_marked_notes(read_fields(words, template, w, h), lines, template)
    units = read_units(lines, template)
    if units is not None:
        fields["units"] = units
    return TitleBlockRead(kind, fields, *read_revision_rows(lines, template, w, h))
