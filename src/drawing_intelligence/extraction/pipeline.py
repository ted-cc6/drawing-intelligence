"""Stage 1: one PDF in, one `Extraction` (every page) out. Deterministic; no LLM."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from drawing_intelligence.extraction.classify import classify
from drawing_intelligence.extraction.cleanup import (
    flag_reference_dims,
    link_stacked_tolerances,
    merge_adjacent_spans,
)
from drawing_intelligence.extraction.geometry import (
    calibrate_scale,
    check_chain_vs_overall,
    find_chains,
    match_dimension_lines,
)
from drawing_intelligence.extraction.imaging import ImagingConfig, export_page_images
from drawing_intelligence.extraction.template import Rect, Template, load_template
from drawing_intelligence.extraction.text_layer import Row, all_text_lines, line_segments, raw_rows
from drawing_intelligence.extraction.title_block import read_title_block
from drawing_intelligence.extraction.tolerance_table import read_general_tolerances
from drawing_intelligence.schemas import (
    Extraction,
    MatchedLine,
    PageExtraction,
    TextItem,
    TextLine,
)

EXTRACTION_FILE = "extraction.json"


def _region_of(bbox: Rect, regions: dict[str, Rect]) -> str:
    # Which named region a line sits in, by its centre. The title block wins over the tolerance strip.
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for name in ("title_block", "tolerance_table"):
        rx0, ry0, rx1, ry1 = regions[name]
        if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
            return name
    return "drawing_body"


def _item(r: Row, item_id: str | None = None) -> TextItem:
    return TextItem(
        id=item_id,
        text=r.text,
        is_reference=r.is_reference,
        bbox=(round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)),
        limits=r.limits,
    )


def extract_rows(page: pymupdf.Page, template: Template) -> tuple[list[Row], list]:
    """Text rows cleaned and classified, plus the page's line segments (reused by the geometry step)."""
    w, h = page.rect.width, page.rect.height
    segments = line_segments(page)
    rows = raw_rows(page, template.excluded_rects(w, h), template.glyph_remap)
    rows = merge_adjacent_spans(rows)
    rows = link_stacked_tolerances(rows)
    rows = flag_reference_dims(rows, segments)
    for r in rows:
        r.category = classify(r.text)
    rows.sort(key=lambda r: (round(r.y0 / 15), r.x0))  # reading order: top-to-bottom, left-to-right
    return rows, segments


def extract_page(
    page: pymupdf.Page,
    template: Template,
    out_dir: Path | None = None,
    imaging: ImagingConfig | None = None,
) -> PageExtraction:
    w, h = page.rect.width, page.rect.height
    regions = template.regions_for(w, h)
    rows, segments = extract_rows(page, template)

    dims = [r for r in rows if r.category == "dimension_value"]
    dim_ids = {id(r): f"D{i}" for i, r in enumerate(dims, 1)}

    matches = match_dimension_lines(rows, segments)
    chains = find_chains(matches)

    text: dict[str, list[TextLine]] = {"title_block": [], "tolerance_table": [], "drawing_body": []}
    for t, bbox in all_text_lines(page, template.glyph_remap):
        text[_region_of(bbox, regions)].append(TextLine(text=t, bbox=bbox))

    tb = read_title_block(
        page, text["title_block"] + text["tolerance_table"] + text["drawing_body"], template
    )

    page_no = page.number + 1 if page.number is not None else 1
    images = None
    if out_dir is not None:
        images = export_page_images(
            page, regions.get("title_block"), out_dir, f"page_{page_no}", imaging or ImagingConfig()
        )

    warnings = []
    if not text["title_block"]:
        warnings.append("title block empty - template regions may not fit this sheet")
    elif tb.layout == "variant":
        warnings.append("variant title block - its labels are not where the template expects; no fields read")
    ref_w, ref_h = template.reference_sheet_pts
    if abs(w - ref_w) > 5 or abs(h - ref_h) > 5:
        warnings.append(
            f"sheet {w:.0f}x{h:.0f} pt differs from the template's reference {ref_w:.0f}x{ref_h:.0f} pt - "
            "regions are anchored to the sheet edges; check the title-block crop"
        )

    return PageExtraction(
        page_number=page_no,
        page_size_pts=(round(w, 1), round(h, 1)),
        rotation=page.rotation,
        images=images,
        title_block_text=text["title_block"],
        title_block_layout=tb.layout,
        title_block_fields=tb.fields,
        revision_rows=tb.revision_rows,
        revision_numbers=tb.revision_numbers,
        general_tolerances=read_general_tolerances(text["tolerance_table"]),
        tolerance_table_text=text["tolerance_table"],
        body_text=text["drawing_body"],
        dimensions=[_item(r, dim_ids[id(r)]) for r in dims],
        view_labels=[_item(r) for r in rows if r.category == "view_label"],
        notes=[_item(r) for r in rows if r.category == "note"],
        other_numeric=[_item(r) for r in rows if r.category == "other_numeric"],
        matched_lines=[
            MatchedLine(
                dimension_id=dim_ids[id(m.row)],
                line=(round(m.line[0], 1), round(m.line[1], 1), round(m.line[2], 1), round(m.line[3], 1)),
                orientation=m.orientation,
            )
            for m in matches
        ],
        scale_pts_per_mm=calibrate_scale(matches),
        chain_checks=check_chain_vs_overall(chains, matches, dim_ids),
        warnings=warnings,
    )


def extract_pdf(
    pdf_path: Path,
    out_dir: Path | None = None,
    template: Template | None = None,
    imaging: ImagingConfig | None = None,
) -> Extraction:
    """Extract every page. With `out_dir`, also write the images and `extraction.json` there."""
    template = template or load_template()
    with pymupdf.open(pdf_path) as doc:
        pages = [extract_page(page, template, out_dir, imaging) for page in doc]
    warnings = []
    if not any(p.dimensions for p in pages):
        warnings.append("no dimensions found - is this a vector PDF with a text layer?")
    extraction = Extraction(
        source_file=Path(pdf_path).name,
        template=template.name,
        n_pages=len(pages),
        pages=pages,
        warnings=warnings,
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / EXTRACTION_FILE).write_text(extraction.model_dump_json(indent=1), encoding="utf-8")
    return extraction
