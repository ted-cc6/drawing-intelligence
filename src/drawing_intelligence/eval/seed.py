"""Planted-error drawings (A5a): copy the four samples and plant one known mistake per case, by script.

The client has no drawings with labelled errors, so we make our own. Each case is one edit on one sample in
`data/raw/`: remove a line of text, or replace it with another value in the same font, size, baseline and
direction. The samples' text is plain Helvetica (base-14, not embedded), so a replaced value looks like the
original; dimension lines and other vector art are kept. Near-miss cases make a change that must *not* be
flagged, and clean cases copy a sample unchanged, so the eval can count false alarms.

The answer key for each case (`expected_findings.json`) is written separately, from the approved case list and
before any reviewer exists. This module only builds the drawings and records what it changed (`case.json`).

Run: uv run python -m drawing_intelligence.eval.seed [--only CASE ...]
Outputs: data/eval/seeded/<case>/<case>.pdf and case.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import pymupdf

from drawing_intelligence.extraction.template import GlyphRemap, load_template
from drawing_intelligence.extraction.text_layer import remap_text, text_dict
from drawing_intelligence.settings import get_settings

Kind = Literal["planted", "near_miss", "clean"]
Point = tuple[float, float]

CAM = "10K_CAM PLATE"
CYL = "10K_CYLINDER ROD MTG_02"
HOSE = "20_INCH HOSE PIPE CLAMP_PU_01"
BLK = "31K_PIPE CLAMP BLK_02"

# text direction on the unrotated page -> insert_text rotation (degrees, counter-clockwise)
_ANGLE = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}
# redaction modes: PyMuPDF's PDF_REDACT_IMAGE_NONE, PDF_REDACT_LINE_ART_NONE,
# PDF_REDACT_LINE_ART_REMOVE_IF_COVERED and PDF_REDACT_TEXT_NONE (missing from its stubs)
_KEEP_IMAGES = 0
_KEEP_LINE_ART = 0
_REMOVE_COVERED_LINE_ART = 1
_KEEP_TEXT = 1

Box = tuple[float, float, float, float]
# base-14 fonts in the samples -> PyMuPDF's name for their width metrics
_METRICS = {"Helvetica": "helv", "Helvetica-Bold": "hebo"}
# the band a redaction covers, in em above the baseline: the ink of capitals, digits and signs lies below the
# cap height (0.72 em in Helvetica)
_INK_BAND = (0.05, 0.75)


@dataclass(frozen=True)
class Edit:
    """Change one line of text. `to=None` removes it.

    The line must match `find` exactly (after symbol-font remapping, so "⌀ 16 H7" works). When the text
    appears more than once, `near` (a label printed next to it, e.g. "HEAT TREATMENT") or `at` (a point in
    visual page coordinates) picks the closest match; an edit that matches nothing, or more than one line
    without a locator, is an error rather than a guess. `span` changes only one piece of the line (its index
    among the line's non-blank spans), e.g. one of two dates printed as one line. A replacement is centred
    where the old text was, or keeps its `start` or `end`.
    """

    find: str
    to: str | None = None
    near: str | None = None
    at: Point | None = None
    span: int | None = None
    align: Literal["centre", "start", "end"] = "centre"


@dataclass(frozen=True)
class Case:
    """One seeded drawing. `erase` removes the line art lying wholly inside each box (visual coordinates), for
    things drawn as vector strokes rather than text: a fit's brackets, a note's dashed frame."""

    name: str
    base: str
    kind: Kind
    edits: tuple[Edit, ...] = ()
    summary: str = ""
    erase: tuple[Box, ...] = ()


# The approved case list (.scratch/a5a-planted-errors/issues/02-propose-cases.md, 2026-10-18).
CASES: tuple[Case, ...] = (
    Case("C01_clean_cam_plate", CAM, "clean", summary="unchanged sample"),
    Case("C02_clean_cylinder_rod", CYL, "clean", summary="unchanged sample"),
    Case("C03_clean_hose_clamp", HOSE, "clean", summary="unchanged sample"),
    Case("C04_clean_pipe_clamp_block", BLK, "clean", summary="unchanged sample"),
    Case(
        "P01_chain_overall",
        CAM,
        "planted",
        (Edit("100", "105"),),
        "overall 100 -> 105, so 35 + 30 + (35) no longer adds up",
    ),
    Case(
        "P02_reference_dim",
        HOSE,
        "planted",
        (Edit("24", "26", at=(431, 590)),),
        "reference (24) -> (26), so 24 + 32 + (26) is not 80",
    ),
    Case(
        "P03_two_values",
        CAM,
        "planted",
        (Edit("15", "17", at=(229, 341)),),
        "left boss height 15 -> 17; the right one stays 15 and both are drawn equal",
    ),
    Case(
        "P04_inch_value", BLK, "planted", (Edit("100", '3.94"'),), 'overall 100 -> 3.94" on a metric drawing'
    ),
    # "2-⌀6.4" is two text lines in the PDF ("2-⌀" and "6.4"), so it takes two removals
    Case(
        "P05_hole_no_size",
        BLK,
        "planted",
        (Edit("2-⌀", at=(703, 381)), Edit("6.4", at=(719, 381))),
        "hole size 2-⌀6.4 removed",
    ),
    Case("P06_slot_not_located", CAM, "planted", (Edit("20", at=(250, 419)),), "slot height 20 removed"),
    Case("P07_no_drawing_number", BLK, "planted", (Edit("P24BSP810318"),), "drawing number removed"),
    Case("P08_no_material", CAM, "planted", (Edit("M.S."),), "material removed"),
    Case(
        "P09_no_surface_treatment",
        CYL,
        "planted",
        (Edit("I.Z.B.P. (TRIVALENT)"),),
        "surface treatment removed",
    ),
    # the CHKD.BY and APPD.BY dates are one text line of two pieces; the DRN.BY date is a line of its own
    Case(
        "P10_checked_before_drawn",
        CAM,
        "planted",
        (Edit("01/10/2025 01/10/2025", "25/09/2025", span=0),),
        "checked date 01/10/2025 -> 25/09/2025, before the drawn date 01/10/2025",
    ),
    Case(
        "P11_scale_mismatch",
        HOSE,
        "planted",
        (Edit("1 : 1", "2 : 1"),),
        "title-block scale 1 : 1 -> 2 : 1 while the views say SCALE 1:1",
    ),
    Case(
        "P12_revision_mismatch",
        BLK,
        "planted",
        (Edit("00", "01", near="REV."),),
        "revision 00 -> 01 with an empty revision table",
    ),
    Case(
        "P13_fit_limits_inverted",
        CAM,
        "planted",
        # a sign typo; swapping the two limits would break Solid Edge's digit alignment of stacked limits
        (Edit("+0.018", "-0.018", at=(618, 408), align="end"),),
        "⌀ 16 H7 upper limit +0.018 -> -0.018, so (-0.018/0) has the lower limit above the upper",
    ),
    Case(
        "P14_decimals_vs_tolerance",
        CAM,
        "planted",
        (Edit("28.5±0.1", "28.500±0.1"),),
        "28.5±0.1 -> 28.500±0.1",
    ),
    Case("P15_tight_tolerance", BLK, "planted", (Edit("70±0.2", "70±0.002"),), "70±0.2 -> 70±0.002"),
    Case(
        "P16_note_removed",
        CYL,
        "planted",
        (
            Edit("HEAT TREATMENT  :-"),
            Edit("1) TO BE TOUGHENED UPTO 24-32 HRC."),
            Edit("2) RETAPPING TO BE DONE AFTER SURFACE TREATMENT"),
            Edit("AT SUPPLIER END.( IF APPLICABLE )"),
        ),
        "heat-treatment note box removed; the title-block field still says REF NOTE",
        erase=((140, 680, 426, 730),),  # the note's dashed frame
    ),
    Case(
        "P17_tempering_without_hardening",
        CYL,
        "planted",
        (Edit("1) TO BE TOUGHENED UPTO 24-32 HRC.", "1) TO BE TEMPERED UPTO 24-32 HRC.", align="start"),),
        "TOUGHENED -> TEMPERED: tempering with no hardening process",
    ),
    Case(
        "P18_heat_treatment_on_plastic",
        HOSE,
        "planted",
        (Edit("---", "HARDENED 40-45 HRC", near="HEAT TREATMENT"),),
        "heat treatment HARDENED 40-45 HRC on a polyurethane part",
    ),
    Case(
        "P19_fit_removed",
        CAM,
        "planted",
        (Edit("⌀ 16 H7", span=2), Edit("+0.018", at=(618, 408)), Edit("0", at=(612, 417))),
        "H7 (+0.018/0) removed from the ⌀ 16 locating bore; ⌀ 16 stays",
        erase=((598.5, 403, 602, 420), (634.8, 403, 638, 420)),  # the brackets, drawn as short strokes
    ),
    Case(
        "P20_corner_radius",
        CAM,
        "planted",
        (Edit("R 8", "R 0.2", at=(314, 330)),),
        "internal corner R 8 -> R 0.2, too small for standard cutters",
    ),
    Case(
        "P21_anodizing_on_steel",
        CAM,
        "planted",
        (Edit("I.Z.B.P. (TRIVALENT)", "HARD ANODIZING"),),
        "surface treatment HARD ANODIZING on an M.S. part (aluminium only)",
    ),
    Case(
        "P22_zinc_on_plastic",
        HOSE,
        "planted",
        (Edit("N.A.", "I.Z.B.P. (TRIVALENT)"),),
        "surface treatment I.Z.B.P. on a polyurethane part (mild / carbon steel only)",
    ),
    Case(
        "N01_hardness_still_valid",
        CYL,
        "near_miss",
        (Edit("1) TO BE TOUGHENED UPTO 24-32 HRC.", "1) TO BE TOUGHENED UPTO 28-32 HRC."),),
        "24-32 HRC -> 28-32 HRC, still within PARI's range for C-45 toughening",
    ),
    Case(
        "N02_tolerance_still_ordinary",
        BLK,
        "near_miss",
        (Edit("70±0.2", "70±0.1"),),
        "70±0.2 -> 70±0.1, tighter but ordinary",
    ),
)


@dataclass
class _Line:
    text: str
    spans: list[dict[str, Any]]
    direction: tuple[int, int]
    raw_bbox: pymupdf.Rect  # unrotated page coordinates (the content stream's own)
    visual_bbox: pymupdf.Rect  # as the drawing is viewed (what the extraction reports)


@dataclass
class AppliedEdit:
    find: str
    to: str | None
    bbox: list[float]  # where the text was, visual page coordinates
    font: str
    size: float


@dataclass
class SeedResult:
    case: str
    base: str
    kind: Kind
    summary: str
    pdf: str
    edits: list[AppliedEdit] = field(default_factory=list)
    erased: list[list[float]] = field(default_factory=list)  # boxes whose line art was removed (visual)


def _lines(page: pymupdf.Page, to_visual: pymupdf.Matrix, remaps: list[GlyphRemap]) -> list[_Line]:
    out = []
    for block in text_dict(page)["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"]]  # keep space spans: "R 8" is "R", " ", "8"
            if not any(s["text"].strip() for s in spans):
                continue
            raw = pymupdf.Rect(line["bbox"])
            dx, dy = line["dir"]
            out.append(
                _Line(remap_text(spans, remaps).strip(), spans, (round(dx), round(dy)), raw, raw * to_visual)
            )
    return out


def _center(r: pymupdf.Rect) -> Point:
    return ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)


def _dist(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _locate(lines: list[_Line], edit: Edit) -> _Line:
    hits = [ln for ln in lines if ln.text == edit.find]
    if not hits:
        raise ValueError(f"text {edit.find!r} not found")
    anchor: Point | None = edit.at
    if edit.near is not None:
        labels = [ln for ln in lines if ln.text == edit.near]
        if len(labels) != 1:
            raise ValueError(f"label {edit.near!r} found {len(labels)} times, need exactly one")
        anchor = _center(labels[0].visual_bbox)
    if anchor is None:
        if len(hits) > 1:
            raise ValueError(f"text {edit.find!r} found {len(hits)} times; give `near` or `at`")
        return hits[0]
    point = anchor
    return min(hits, key=lambda ln: _dist(_center(ln.visual_bbox), point))


def _rgb(color: int) -> tuple[float, float, float]:
    return ((color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)


def _pieces(line: _Line, span: int | None) -> tuple[list[dict[str, Any]], pymupdf.Rect]:
    """The spans an edit changes and their box (unrotated): the whole line, or one of its non-blank spans."""
    if span is None:
        return line.spans, line.raw_bbox
    pieces = [s for s in line.spans if s["text"].strip()]
    if not 0 <= span < len(pieces):
        raise ValueError(f"{line.text!r} has {len(pieces)} pieces, not a piece {span}")
    return [pieces[span]], pymupdf.Rect(pieces[span]["bbox"])


def _ink_box(span: dict[str, Any], direction: tuple[int, int]) -> pymupdf.Rect:
    """Where a span's glyphs are drawn (unrotated): its length, less a little at each end so text that only
    touches it survives, and only the ink band above the baseline. The span's own box also covers the font's
    ascender and descender space, which can overlap a label printed beside it (a section letter next to a
    vertical dimension), and a redaction removes every character it touches."""
    dx, dy = direction
    ux, uy = dy, -dx  # towards the tops of the glyphs
    (ox, oy), size, box = span["origin"], span["size"], pymupdf.Rect(span["bbox"])
    lo, hi = (_INK_BAND[0] * size, _INK_BAND[1] * size)
    if dx == 0:  # vertical text: the band runs across x
        x0, x1 = sorted((ox + ux * lo, ox + ux * hi))
        return pymupdf.Rect(x0, box.y0 + 0.4, x1, box.y1 - 0.4)
    y0, y1 = sorted((oy + uy * lo, oy + uy * hi))
    return pymupdf.Rect(box.x0 + 0.4, y0, box.x1 - 0.4, y1)


def _words(page: pymupdf.Page) -> Counter[tuple[str, float, float, float, float]]:
    """The page's words with their boxes (to 0.1 pt), counted."""
    out: Counter[tuple[str, float, float, float, float]] = Counter()
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        x0, y0, x1, y1 = (round(float(v), 1) for v in (x0, y0, x1, y1))
        out[(str(text), x0, y0, x1, y1)] += 1
    return out


def apply_edits(
    page: pymupdf.Page, edits: tuple[Edit, ...], remaps: list[GlyphRemap], erase: tuple[Box, ...] = ()
) -> list[AppliedEdit]:
    """Apply the edits (and erasures) to one page in place and return where each edit was made."""
    rotation = page.rotation
    to_visual = page.rotation_matrix
    page.set_rotation(0)  # work in the content stream's own coordinates; restored below
    try:
        lines = _lines(page, to_visual, remaps)
        targets = []
        for edit in edits:
            line = _locate(lines, edit)
            spans, raw = _pieces(line, edit.span)
            targets.append((edit, line, spans, raw))
        before = _words(page)
        boxes = [_ink_box(s, ln.direction) for _, ln, spans, _ in targets for s in spans if s["text"].strip()]
        for box in boxes:
            page.add_redact_annot(box)
        page.apply_redactions(images=_KEEP_IMAGES, graphics=_KEEP_LINE_ART)
        # one edit, one change: no other word on the page may go with it
        lost = before - _words(page)
        stray = [w for w in lost if not any(pymupdf.Rect(w[1:]).intersects(b) for b in boxes)]
        if stray:
            raise ValueError(f"the edits would also remove {sorted(w[0] for w in stray)}")
        if erase:
            for box in erase:
                page.add_redact_annot(pymupdf.Rect(box) * ~to_visual)
            page.apply_redactions(images=_KEEP_IMAGES, graphics=_REMOVE_COVERED_LINE_ART, text=_KEEP_TEXT)
        # write new text with the page's own font resource (basefont -> reference name, e.g. Helvetica -> F1):
        # the same font record keeps the original's text-box metrics, which the extraction relies on (stacked
        # limits are linked by their boxes), and adds no font to the file
        font_refs = {f[3]: f[4] for f in page.get_fonts()}
        applied = []
        for edit, line, spans, raw in targets:
            first = spans[0]
            if edit.to is not None:
                if len({(s["font"], round(s["size"], 2)) for s in spans if s["text"].strip()}) > 1:
                    raise ValueError(f"{edit.find!r} mixes fonts or sizes; replace it span by span")
                if first["font"] not in _METRICS or first["font"] not in font_refs:
                    raise ValueError(
                        f"{edit.find!r} is in font {first['font']!r}; only Helvetica can be rewritten"
                    )
                # place the new text where the old text was: centred (title-block values, dimensions), or
                # keeping its end so stacked limits stay aligned on their digits
                size, metrics = first["size"], _METRICS[first["font"]]
                old = remap_text(spans, remaps).strip()
                grow = pymupdf.get_text_length(edit.to, metrics, size) - pymupdf.get_text_length(
                    old, metrics, size
                )
                shift = {"centre": grow / 2, "start": 0.0, "end": grow}[edit.align]
                dx, dy = line.direction
                origin = (first["origin"][0] - shift * dx, first["origin"][1] - shift * dy)
                page.insert_text(
                    origin,
                    edit.to,
                    fontname=font_refs[first["font"]],
                    fontsize=size,
                    rotate=_ANGLE[line.direction],
                    color=_rgb(first["color"]),
                )
            vb = raw * to_visual
            applied.append(
                AppliedEdit(
                    edit.find,
                    edit.to,
                    [round(v, 1) for v in (vb.x0, vb.y0, vb.x1, vb.y1)],
                    first["font"],
                    round(first["size"], 2),
                )
            )
        return applied
    finally:
        page.set_rotation(rotation)


def seed_case(case: Case, raw_dir: Path, out_dir: Path, remaps: list[GlyphRemap]) -> SeedResult:
    """Build one case: `<out_dir>/<case>/<case>.pdf` plus `case.json` describing the edit."""
    src = raw_dir / f"{case.base}.pdf"
    folder = out_dir / case.name
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / f"{case.name}.pdf"
    doc = pymupdf.open(src)
    try:
        applied = apply_edits(doc[0], case.edits, remaps, case.erase) if case.edits or case.erase else []
        doc.save(pdf, garbage=3, deflate=True, no_new_id=True)
    finally:
        doc.close()
    result = SeedResult(
        case.name, case.base, case.kind, case.summary, pdf.name, applied, [list(b) for b in case.erase]
    )
    (folder / "case.json").write_text(
        json.dumps(asdict(result), indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return result


def seed_all(raw_dir: Path, out_dir: Path, only: list[str] | None = None) -> list[SeedResult]:
    remaps = load_template().glyph_remap
    cases = [c for c in CASES if not only or c.name in only]
    return [seed_case(c, raw_dir, out_dir, remaps) for c in cases]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the planted-error drawings in data/eval/seeded/.")
    parser.add_argument("--only", nargs="*", help="case names to build (default: all)")
    args = parser.parse_args(argv)
    settings = get_settings()
    out = settings.data_path / "eval" / "seeded"
    for r in seed_all(settings.raw_dir, out, args.only):
        print(f"{r.case}: {r.kind}, {len(r.edits)} edit(s)")


if __name__ == "__main__":
    main()
