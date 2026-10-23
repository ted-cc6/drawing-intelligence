"""Stage 1 output: everything read exactly from the PDF (text layer + vector geometry), per page.

Coordinates (`bbox`, lines) are PDF points (72 per inch), origin top-left, in the visual page orientation
(corrected for the page's /Rotate flag).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EXTRACTION_SCHEMA_VERSION = "2.1"  # 2.1: title-block fields, revision rows, chain ids

BBox = tuple[float, float, float, float]


class TextLine(BaseModel):
    """One raw text line from the PDF text layer."""

    text: str
    bbox: BBox


class TextItem(BaseModel):
    """A cleaned and classified text item (dimension, view label, note, other number)."""

    id: str | None = Field(default=None, description="D1..Dn for dimensions; None for other items")
    text: str
    is_reference: bool = False
    bbox: BBox


class MatchedLine(BaseModel):
    """A dimension value matched to the straight dimension line next to it."""

    dimension_id: str
    line: BBox = Field(description="x0, y0, x1, y1 of the line segment")
    orientation: Literal["horizontal", "vertical"]


class ChainCheck(BaseModel):
    """A chain of end-to-end dimensions compared with the overall dimension spanning it."""

    chain_texts: list[str]
    chain_ids: list[str] = Field(default=[], description="the chain's dimension ids, in order")
    chain_sum: float
    overall_text: str
    overall_id: str | None = None
    overall_value: float
    match: bool
    diff: float


class TitleBlockField(BaseModel):
    """One title-block value read by position from its cell in the template (stage 1, exact text)."""

    value: str | None = Field(description="the words in the cell in reading order; None if the cell is empty")
    bbox: BBox = Field(description="the printed value's bbox, or the cell's when it is empty")


class Tile(BaseModel):
    file: str = Field(description="path relative to the extraction folder")
    pixel_box: tuple[int, int, int, int]


class ImageSet(BaseModel):
    """Images of one page prepared for the vision LLM; paths are relative to the extraction folder."""

    dpi: int
    full: str
    title_block: str | None
    tiles: list[Tile]


class PageExtraction(BaseModel):
    page_number: int = Field(description="1-based")
    page_size_pts: tuple[float, float]
    rotation: int
    images: ImageSet | None = None
    title_block_text: list[TextLine] = []
    title_block_layout: Literal["standard", "variant"] | None = Field(
        default=None, description="variant: the template's anchor labels are not where expected, so no fields"
    )
    title_block_fields: dict[str, TitleBlockField] = Field(
        default={}, description="keyed by the `TitleBlock` field names (number, material, drawn_date, ...)"
    )
    revision_rows: list[TextLine] = Field(default=[], description="filled rows of the revision table")
    revision_numbers: list[TextLine] = Field(
        default=[], description="the revision numbers in the table's first column (1, 2, ...)"
    )
    tolerance_table_text: list[TextLine] = []
    body_text: list[TextLine] = []
    dimensions: list[TextItem] = []
    view_labels: list[TextItem] = []
    notes: list[TextItem] = []
    other_numeric: list[TextItem] = []
    matched_lines: list[MatchedLine] = []
    scale_pts_per_mm: float | None = None
    chain_checks: list[ChainCheck] = []
    warnings: list[str] = []


class Extraction(BaseModel):
    schema_version: Literal["2.0", "2.1"] = EXTRACTION_SCHEMA_VERSION
    source_file: str
    template: str
    n_pages: int
    pages: list[PageExtraction]
    warnings: list[str] = []
