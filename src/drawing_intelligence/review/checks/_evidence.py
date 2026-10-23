"""Evidence helpers: point a finding at what it cites, exactly as stage 1 read it."""

from __future__ import annotations

from drawing_intelligence.review.checks._registry import NotCheckable
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.schemas import EvidenceRef, PageExtraction, TextItem, TextLine

# Values that only hold a cell's place. A rule's `placeholder_ok` lists the ones it accepts as a real answer
# (e.g. "N.A." for a surface treatment that is deliberately none).
PLACEHOLDERS = frozenset({"#", "-", "--", "---", "N.A.", "NA", "N/A", "NIL", "TBD", "XX", "XXX"})


def dimension(page: PageExtraction, dim: TextItem) -> EvidenceRef:
    return EvidenceRef(
        kind="dimension",
        ref=dim.id,
        page=page.page_number,
        bbox=list(dim.bbox),
        quote=dim.text,
        provenance="pdf_text",
    )


def text(page: PageExtraction, item: TextItem | TextLine) -> EvidenceRef:
    return EvidenceRef(
        kind="text", page=page.page_number, bbox=list(item.bbox), quote=item.text, provenance="pdf_text"
    )


def field(page: PageExtraction, name: str) -> EvidenceRef:
    """A title-block field; an empty one cites its cell, with no quote."""
    f = page.title_block_fields.get(name)
    return EvidenceRef(
        kind="title_block",
        ref=name,
        page=page.page_number,
        bbox=list(f.bbox) if f else None,
        quote=f.value if f else None,
        provenance="pdf_text",
    )


def value(page: PageExtraction, name: str) -> str | None:
    f = page.title_block_fields.get(name)
    return f.value if f else None


def title_block_pages(ctx: ReviewContext) -> list[PageExtraction]:
    """Pages whose title block was read. None at all -> the rule can't be checked on this drawing."""
    pages = [p for p in ctx.pages if p.title_block_layout == "standard"]
    if not pages:
        raise NotCheckable("no title block read (variant layout or unknown template)")
    return pages


def dims_by_id(page: PageExtraction) -> dict[str, TextItem]:
    return {d.id: d for d in page.dimensions if d.id}
