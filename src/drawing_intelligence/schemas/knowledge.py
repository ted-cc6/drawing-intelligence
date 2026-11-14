"""Stage 2 output: the structured understanding of one drawing sheet.

`DrawingKnowledge` is also the strict JSON schema sent to the LLM, so the field descriptions below are
instructions to the model. Every field is required; "unknown" is expressed as null, never by leaving a
field out.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KNOWLEDGE_SCHEMA_VERSION = "1.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


BBoxOrNull = list[float] | None
_BBOX = "[x0, y0, x1, y1] in PDF points, or null"


class TitleBlock(_Strict):
    number: str | None = Field(description="drawing number, exactly as printed")
    title: str | None
    revision: str | None
    material: str | None
    surface_treatment: str | None
    heat_treatment: str | None
    scale: str | None
    sheet_size: str | None
    units: str | None = Field(description="the unit stated in the notes, e.g. mm")
    general_tolerance_standard: str | None
    drawn_date: str | None = Field(description="as printed")
    checked_date: str | None
    approved_date: str | None
    weight: str | None = Field(description="with its unit as printed, e.g. 0.25 kg")


class View(_Strict):
    id: str = Field(description="view1, view2, ...")
    name: str = Field(description="e.g. FRONT VIEW, SECTION B-B, DETAIL A")
    scale: str | None = Field(description="e.g. 2:1, or null")


DimensionType = Literal["linear", "diameter", "radius", "angle", "chamfer", "count_x_diameter", "other"]


class Dimension(_Strict):
    id: str = Field(
        description="the extracted id D1, D2, ... unchanged; V1, V2, ... for image-only dimensions"
    )
    text: str = Field(description="exact text, character for character")
    value: float | None = Field(description="nominal value as a number")
    unit: str | None = Field(description="mm or deg")
    tolerance: str | None = Field(description="e.g. ±0.1 or H7 (+0.018/0), or null")
    type: DimensionType
    is_reference: bool
    view_id: str | None
    feature_id: str | None
    source: Literal["pdf_text", "vision"]
    bbox: BBoxOrNull = Field(description=_BBOX)


FeatureType = Literal["hole", "slot", "chamfer", "fillet", "thread", "pocket", "step", "outline", "other"]


class Feature(_Strict):
    id: str = Field(description="F1, F2, ...")
    type: FeatureType
    description: str
    dimension_ids: list[str]
    view_id: str | None


SymbolType = Literal["gdt", "surface_finish", "weld", "datum", "other"]


class Symbol(_Strict):
    id: str = Field(description="S1, S2, ...")
    type: SymbolType
    value: str | None = Field(description="what the symbol says, e.g. flatness 0.05, Ra 3.2, datum A")
    datum: str | None = Field(description="datum letter(s) or null")
    view_id: str | None
    tile: str | None = Field(description="image file where the symbol was seen")
    bbox: BBoxOrNull = Field(description="approximate " + _BBOX)
    source: Literal["vision"]


NoteCategory = Literal["general", "heat_treatment", "surface", "standard", "material", "other"]


class Note(_Strict):
    id: str = Field(description="N1, N2, ...")
    text: str = Field(description="exact text; join the lines of one note with a space")
    category: NoteCategory


class GeneralTolerance(_Strict):
    kind: Literal["linear", "angular"]
    process: str | None = Field(description="machining or fabrication")
    range: str = Field(description="e.g. 6 UP TO 30")
    tolerance: str = Field(description="e.g. ±0.2")


class Revision(_Strict):
    rev: str | None
    date: str | None
    description: str | None


class Uncertain(_Strict):
    item: str
    reason: str


class DrawingKnowledge(_Strict):
    drawing: TitleBlock
    views: list[View]
    dimensions: list[Dimension]
    features: list[Feature]
    symbols: list[Symbol]
    notes: list[Note]
    general_tolerances: list[GeneralTolerance]
    revisions: list[Revision]
    uncertain: list[Uncertain]


TagRole = Literal[
    "internal_fit",
    "external_fit",
    "keyway_width",
    "keyway_depth_shaft",
    "keyway_depth_hub",
    "keyway_bottom_shaft",
    "keyway_bottom_hub",
    "circlip_groove_diameter",
    "circlip_groove_width",
    "undercut_width",
    "undercut_diameter",
    "undercut_radius",
]


class DimensionTag(_Strict):
    """What feature one dimension measures, for the checks that need to know (stage 2's tagger)."""

    dimension_id: str = Field(description="the dimension's id in DRAWING (D1, D2, ...)")
    quote: str = Field(description="the dimension's text exactly as in DRAWING")
    role: TagRole
    of: str | None = Field(
        description="the shaft, bore or thread the feature belongs to: its dimension id, or its call-out "
        "text exactly as printed (e.g. M20 x 1.5); null when the drawing does not say"
    )


class TagResult(BaseModel):
    """The tagger's answer for one page and how it was produced."""

    model: str
    thinking: str
    tags: list[DimensionTag] = []
    dropped: int = Field(
        default=0, description="tags naming a dimension the page does not have, or misquoting it"
    )
    valid: bool = True
    cost_usd: float = 0.0
    latency_s: float = 0.0
    cached: bool = False


class UnderstandingResult(BaseModel):
    """What stage 2 saves per page: the knowledge plus how it was produced."""

    schema_version: Literal["1.0"] = KNOWLEDGE_SCHEMA_VERSION
    page_number: int
    model: str
    thinking: str
    knowledge: DrawingKnowledge | None
    valid: bool
    attempts: int
    problems: list[str] = []
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    cached: bool = False
    tagging: TagResult | None = Field(default=None, description="the tagger's dimension roles (2026-11-13)")

    @property
    def billed_usd(self) -> float:
        """What this page cost in API calls on this run: cached replies are free."""
        tag = self.tagging
        return (0.0 if self.cached else self.cost_usd) + (0.0 if tag is None or tag.cached else tag.cost_usd)

    @property
    def all_cached(self) -> bool:
        return self.cached and (self.tagging is None or self.tagging.cached)
