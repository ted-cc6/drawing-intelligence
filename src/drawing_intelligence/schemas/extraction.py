"""Stage 1 output: everything read exactly from the PDF (text layer + vector geometry), per page.

Coordinates (`bbox`, lines) are PDF points (72 per inch), origin top-left, in the visual page orientation
(corrected for the page's /Rotate flag).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EXTRACTION_SCHEMA_VERSION = "2.0"

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
    chain_sum: float
    overall_text: str
    overall_value: float
    match: bool
    diff: float


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
    schema_version: Literal["2.0"] = EXTRACTION_SCHEMA_VERSION
    source_file: str
    template: str
    n_pages: int
    pages: list[PageExtraction]
    warnings: list[str] = []
