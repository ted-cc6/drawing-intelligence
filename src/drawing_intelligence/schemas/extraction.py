"""Stage 1 output: everything read exactly from the PDF (text layer + vector geometry), per page.

Coordinates (`bbox`, lines) are PDF points (72 per inch), origin top-left, in the visual page orientation
(corrected for the page's /Rotate flag).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 2.3: graphics. 2.2: symbols. 2.1: title-block fields, revision rows, chain ids, general tolerances
EXTRACTION_SCHEMA_VERSION = "2.3"

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
    limits: tuple[str, str] | None = Field(
        default=None, description="(upper, lower) of a stacked tolerance, ordered by where they are printed"
    )


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
    source: Literal["cell", "notes"] = Field(
        default="cell",
        description="notes: the cell held the template's 'see notes' marker (#); read from the note",
    )


class GeneralToleranceRow(BaseModel):
    """One row of the general tolerance table (IS 2102): the tolerance for sizes over `over` up to `up_to`."""

    process: Literal["machining", "fabrication"]
    kind: Literal["linear", "angular"]
    over: float
    up_to: float | None = Field(description="None for the open-ended last row (OVER 2000)")
    tolerance: str = Field(description="as printed, e.g. ±0.2 or ±0°30'")
    value_mm: float | None = Field(description="the ± value in mm, for linear rows")
    bbox: BBox = Field(description="the row's size-range text")


class SymbolItem(BaseModel):
    """A symbol read from the PDF itself (Spike D): exact, unlike the vision model's guesses."""

    id: str = Field(description="S1, S2, ... in reading order")
    type: Literal["gdt", "datum", "surface_finish"]
    text: str = Field(description="what it says, e.g. 'perpendicularity 0.02 | A', 'datum B', 'Ra 3.2'")
    characteristic: str | None = Field(default=None, description="GD&T: flatness, position, ...")
    tolerance: str | None = Field(default=None, description="GD&T: the tolerance as printed, e.g. ⌀0.05")
    datums: list[str] = Field(default=[], description="GD&T: datum references; datum flag: its letter")
    ra: str | None = Field(default=None, description="surface finish: the Ra value, when one is printed")
    bbox: BBox
    provenance: Literal["pdf_text", "vector"]


class ArrowheadItem(BaseModel):
    """A dimension-line termination drawn on the sheet."""

    tip: tuple[float, float]
    axis: tuple[float, float] = Field(description="unit vector from the base to the tip")
    length: float
    style: Literal["filled", "closed", "open"] = Field(
        description="filled triangle, outlined triangle, or two strokes with no base"
    )


class CircleItem(BaseModel):
    """A full circle, drawn as a closed chain of short segments."""

    centre: tuple[float, float]
    radius: float = Field(description="in PDF points")


class DimensionGraphics(BaseModel):
    """How one dimension value is drawn: the line it sits on and what is around its text."""

    dimension_id: str
    direction: tuple[float, float] = Field(description="the text's reading direction, a unit vector")
    line: BBox | None = Field(
        default=None, description="the arrowed dimension line or leader nearest the value, or None"
    )
    arrowheads: int = Field(default=0, description="arrowheads on that line and the strokes joined to it")
    arrow_tips: list[tuple[float, float]] = []
    line_arrowheads: int = Field(
        default=0,
        description="arrowheads on the straight line itself (collinear with it), not on joined strokes",
    )
    span_pts: float | None = Field(
        default=None, description="tip-to-tip distance when the line has two opposed arrowheads"
    )
    tip_on_circle: bool = Field(default=False, description="an arrow tip lies on a full circle")
    arc_radius_pts: float | None = Field(
        default=None,
        description="radius values: the drawn radius of the arc the arrow lands on, in PDF points",
    )
    boxed: bool = Field(default=False, description="the value is framed by a drawn rectangle")
    underlined: bool = Field(default=False, description="a stroke the length of the value runs under it")
    crossed_by: list[BBox] = Field(default=[], description="strokes passing through the value's text")
    in_table: bool = Field(default=False, description="the value sits in a ruled table cell")
    ordinate: bool = Field(
        default=False,
        description="no arrowed line, but a line ends at the value along its reading direction (an ordinate "
        "or running dimension, which has no arrowheads)",
    )


class FieldRevisionMark(BaseModel):
    """A revision triangle (Δ) with its label, on the drawing field (outside the title block)."""

    label: str
    bbox: BBox


class PageGraphics(BaseModel):
    arrowheads: list[ArrowheadItem] = []
    arrowhead_styles: dict[str, int] = Field(default={}, description="style -> count")
    circles: list[CircleItem] = []
    dimensions: list[DimensionGraphics] = []
    revision_marks: list[FieldRevisionMark] = []
    revision_cells: list[BBox] = Field(
        default=[],
        description="revision triangles drawn on a table cell's border (two strokes and the border)",
    )
    datum_triangles: list[BBox] = Field(
        default=[], description="filled, about equilateral triangles: the feet of datum flags"
    )
    leadered_text: list[BBox] = Field(
        default=[], description="body text lines an arrowed leader starts from (a note pointing at an area)"
    )


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
    symbols: list[SymbolItem] = Field(default=[], description="GD&T frames, datum flags, finish marks")
    general_tolerances: list[GeneralToleranceRow] = Field(
        default=[], description="the general tolerance table's rows, read from the tolerance strip"
    )
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
    graphics: PageGraphics | None = Field(
        default=None, description="arrowheads, dimension lines, circles, revision marks (schema 2.3)"
    )
    warnings: list[str] = []


class Extraction(BaseModel):
    schema_version: Literal["2.0", "2.1", "2.2", "2.3"] = EXTRACTION_SCHEMA_VERSION
    source_file: str
    template: str
    n_pages: int
    pages: list[PageExtraction]
    warnings: list[str] = []
