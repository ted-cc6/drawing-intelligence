"""P2 reference models. Partial tables declare their scope; absence is never disapproval."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(Strict):
    document: str
    section: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Equivalent(Strict):
    us: str
    india: str
    cell: str
    # Only literal grade pairs are mechanically checked, never prose/alternatives.
    automatic: bool


class Equivalents(Strict):
    source: Citation
    scope: str
    rows: list[Equivalent]


class StockRow(Strict):
    material: str
    form: str
    sizes_mm: list[float]
    cell: str

    @model_validator(mode="after")
    def positive_unique(self) -> StockRow:
        if not self.sizes_mm or self.sizes_mm != sorted(set(self.sizes_mm)):
            raise ValueError("sizes must be nonempty, increasing and unique")
        if any(not math.isfinite(v) or v <= 0 for v in self.sizes_mm):
            raise ValueError("stock sizes must be positive and finite")
        return self


class StockTable(Strict):
    source: Citation
    scope: str
    rows: list[StockRow]


class NumericTable(Strict):
    source: Citation
    scope: str
    values: dict[str, list[float]]

    @model_validator(mode="after")
    def finite_positive(self) -> NumericTable:
        if not self.values or any(
            not vs or any(not math.isfinite(v) or v <= 0 for v in vs) for vs in self.values.values()
        ):
            raise ValueError("numeric table requires finite positive values")
        return self


class HardnessRow(Strict):
    hv: float = Field(gt=0)
    hrc: float | None = Field(default=None, gt=0, le=100)
    hrb: float | None = Field(default=None, gt=0)
    hb_steel_ball: float | None = Field(default=None, gt=0)
    hb_carbide_ball: float | None = Field(default=None, gt=0)
    tensile_kgf_mm2: float | None = Field(default=None, gt=0)


class HardnessTable(Strict):
    source: Citation
    scope: str
    rows: list[HardnessRow]

    @model_validator(mode="after")
    def monotonic(self) -> HardnessTable:
        if len(self.rows) < 2:
            raise ValueError("at least two rows required")
        for column in HardnessRow.model_fields:
            values = [value for row in self.rows if (value := getattr(row, column)) is not None]
            if any(not math.isfinite(v) for v in values) or any(a >= b for a, b in pairwise(values)):
                raise ValueError(f"hardness column {column} must be finite and strictly increasing")
        return self


class MorseRow(Strict):
    designation: str
    gauge_d_mm: float = Field(gt=0)
    thread: str | None
    alpha_dms_as_printed: list[int]

    @model_validator(mode="after")
    def valid_alpha(self) -> MorseRow:
        if len(self.alpha_dms_as_printed) != 3:
            raise ValueError("table alpha requires degrees, minutes, seconds")
        d, m, s = self.alpha_dms_as_printed
        if d < 0 or not 0 <= m < 60 or not 0 <= s < 60:
            raise ValueError("invalid DMS angle")
        return self


class MorseTable(Strict):
    source: Citation
    scope: str
    rows: list[MorseRow]


class UndercutRow(Strict):
    diameters_mm: list[float]
    external_width_mm_by_min_angle_deg: dict[float, float | None]
    external_radius_mm: float = Field(gt=0)
    external_g_subtract_mm: float | None = Field(default=None, gt=0)
    internal_width_mm_by_min_angle_deg: dict[float, float | None]
    internal_radius_mm: float | None = Field(default=None, gt=0)
    internal_g1_add_mm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_columns(self) -> UndercutRow:
        if set(self.external_width_mm_by_min_angle_deg) != {15, 22.5, 30}:
            raise ValueError("external table requires all three throat-angle columns")
        if set(self.internal_width_mm_by_min_angle_deg) != {20, 25}:
            raise ValueError("internal table requires both lead-angle columns")
        for values in (
            self.diameters_mm,
            list(self.external_width_mm_by_min_angle_deg.values()),
            list(self.internal_width_mm_by_min_angle_deg.values()),
        ):
            if any(not math.isfinite(v) or v <= 0 for v in values if v is not None):
                raise ValueError("undercut sizes must be finite and positive or an explicit blank")
        return self


class UndercutTable(Strict):
    source: Citation
    scope: str
    rows: list[UndercutRow]


class Prerequisite(Strict):
    process: str
    min_base_hrc: float | None = None
    forbidden_heat: list[str] = []
    not_recommended_heat: list[str] = []
    forbidden_material: list[str] = []


class Prerequisites(Strict):
    source: Citation
    scope: str
    rows: list[Prerequisite]


class KeywayRow(Strict):
    shaft_over_mm: float = Field(gt=0)
    shaft_up_to_mm: float = Field(gt=0)
    lower_inclusive: bool = False
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    shaft_depth_mm: float = Field(gt=0)
    hub_depth_mm: float = Field(gt=0)
    key_length_mm: float | None = Field(default=None, gt=0)
    key_diameter_mm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_dimensions(self) -> KeywayRow:
        if self.shaft_over_mm >= self.shaft_up_to_mm:
            raise ValueError("invalid shaft-diameter interval")
        return self


class Keyways(Strict):
    source: Citation
    scope: str
    tolerances_transcribed: Literal[False]
    material_requirement_as_printed: str
    taper_keys_is2292: list[KeywayRow]
    woodruff_keys_is2294: list[KeywayRow]


class CatalogueCell(Strict):
    address: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    value: str | int | float


class CatalogueSheet(Strict):
    name: str
    cells: list[CatalogueCell]
    merged_ranges: list[str]

    @model_validator(mode="after")
    def unique_addresses(self) -> CatalogueSheet:
        if len({c.address for c in self.cells}) != len(self.cells):
            raise ValueError("duplicate catalogue cell address")
        return self


class RawMaterialCatalogue(Strict):
    source: Citation
    scope: str
    graphical_shapes_transcribed: Literal[False]
    sheets: list[CatalogueSheet]

    @model_validator(mode="after")
    def unique_sheets(self) -> RawMaterialCatalogue:
        if not self.sheets or len({s.name for s in self.sheets}) != len(self.sheets):
            raise ValueError("catalogue sheets must be nonempty and uniquely named")
        return self


P2_MODELS: dict[str, type[BaseModel]] = {
    "us_india_materials": Equivalents,
    "raw_material_sizes": StockTable,
    "is3458_standard_tapers": NumericTable,
    "is6688_taper_pins": NumericTable,
    "is2473_centre_holes": NumericTable,
    "material_specific_weight": NumericTable,
    "hardness_conversion_steel": HardnessTable,
    "is1715_self_holding_tapers": MorseTable,
    "is1369_thread_runout_undercut": UndercutTable,
    "plating_prerequisites": Prerequisites,
    "keyways": Keyways,
    "raw_material_catalogue": RawMaterialCatalogue,
}
