"""Source-faithful PARI DES-11 data. Lookups do not assert that a drawing has passed a rule.

NIL is a printed table entry, not a statement about every physically possible treatment.
The document explicitly permits justified special selections in note iii.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Process = Literal["toughening", "flame", "induction", "case", "nitriding", "through"]
PROCESSES: tuple[Process, ...] = ("toughening", "flame", "induction", "case", "nitriding", "through")
Form = Literal["round", "plate_block", "unspecified"]
StockForm = Literal["black_round", "black_square", "plate_thickness"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    document: str
    document_id: str
    version: int = Field(ge=1)
    revision: int = Field(ge=0)
    effective_date: date
    section: str
    pdf_pages: list[int]
    repository_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Range(Strict):
    low: float
    high: float
    unit: Literal["HRC", "mm", "microns", "Kg/mm² as printed"]

    @model_validator(mode="after")
    def ordered_positive(self) -> Self:
        if not all(math.isfinite(v) and v > 0 for v in (self.low, self.high)) or self.low > self.high:
            raise ValueError("range must have finite positive endpoints in ascending order")
        if self.unit == "HRC" and self.high > 100:
            raise ValueError("HRC above the physical scale")
        return self


class Treatment(Strict):
    status: Literal["tabulated", "nil"]
    printed: str
    hardness: Range | None = None
    depth_as_printed: Range | None = None
    depth_mm: Range | None = None
    area_marking_required: bool = False

    @model_validator(mode="after")
    def validate_cell(self) -> Self:
        if self.status == "nil":
            if self.printed != "NIL" or any((self.hardness, self.depth_as_printed, self.depth_mm)):
                raise ValueError("a NIL cell cannot contain numeric treatment values")
            if self.area_marking_required:
                raise ValueError("NIL has no hardened-area requirement")
            return self
        if not self.printed.strip() or self.printed == "NIL" or self.hardness is None:
            raise ValueError("a tabulated treatment requires printed text and hardness")
        if self.hardness.unit != "HRC":
            raise ValueError("DES-11 process hardness is in HRC")
        if (self.depth_as_printed is None) != (self.depth_mm is None):
            raise ValueError("printed and normalised depth must both be present or both absent")
        if self.depth_as_printed and self.depth_mm:
            if self.depth_as_printed.unit not in {"mm", "microns"} or self.depth_mm.unit != "mm":
                raise ValueError("case depth units must be mm or microns, normalised to mm")
            scale = 0.001 if self.depth_as_printed.unit == "microns" else 1.0
            for printed, normal in (
                (self.depth_as_printed.low, self.depth_mm.low),
                (self.depth_as_printed.high, self.depth_mm.high),
            ):
                if not math.isclose(printed * scale, normal, abs_tol=1e-12):
                    raise ValueError("incorrect case-depth unit conversion")
        return self


class Selection(Strict):
    preferred_form: Form
    diameter_operator: Literal["<=", ">"] | None = None
    diameter_mm: float | None = Field(default=None, gt=0)
    interpretation_note: str | None = None

    @model_validator(mode="after")
    def diameter_only_for_round(self) -> Self:
        if (self.diameter_operator is None) != (self.diameter_mm is None):
            raise ValueError("diameter operator and threshold are a pair")
        if self.diameter_mm is not None and self.preferred_form != "round":
            raise ValueError("diameter selection applies only to round stock")
        return self


class Material(Strict):
    row: int = Field(ge=1, le=13)
    key: str
    material_as_printed: str
    pari_std_as_printed: str
    equivalents_as_printed: list[str]
    raw_material_note: str
    raw_note_shared_rows: list[int] = []
    selection: Selection
    treatments: dict[Process, Treatment]
    uts_as_printed: str | None
    uts: Range | None
    allowable_stress_as_printed: str | None
    allowable_stress: Range | None
    typical_application: str
    additional_information: str
    source_location: str

    @model_validator(mode="after")
    def complete_columns(self) -> Self:
        if set(self.treatments) != set(PROCESSES):
            raise ValueError("all six DES-11 treatment columns must be represented, including NIL")
        for printed, band in (
            (self.uts_as_printed, self.uts),
            (self.allowable_stress_as_printed, self.allowable_stress),
        ):
            if (printed is None) != (band is None):
                raise ValueError("blank mechanical-property cells stay null; numeric cells need a range")
            if band and band.unit != "Kg/mm² as printed":
                raise ValueError("retain the mechanical-property unit exactly as printed")
        return self


class Policy(Strict):
    material_keys: list[str]
    requirement: Literal[
        "nitriding_after_finish_machining",
        "prefer_toughening_before_nitriding",
        "avoid_chrome_after_nitriding",
    ]
    strength: Literal["instruction", "preference", "avoid_recommendation"]
    source_location: str


class MaterialHeatTreatment(Strict):
    source: Source
    scope: str
    general_notes: dict[str, str]
    column_notes: dict[str, str]
    materials: list[Material]
    policies: list[Policy]

    @model_validator(mode="after")
    def complete_document(self) -> Self:
        if sorted(m.row for m in self.materials) != list(range(1, 14)):
            raise ValueError("DES-11 page 1 requires each row 1–13 exactly once")
        keys = {m.key for m in self.materials}
        if len(keys) != 13 or set(self.general_notes) != {"i", "ii", "iii"}:
            raise ValueError("13 unique material keys and all three general notes are required")
        for policy in self.policies:
            if not set(policy.material_keys) <= keys:
                raise ValueError("policy refers to an unknown material")
        return self

    def by_key(self, key: str) -> Material:
        """Explicit source row, not an inference about an ambiguous drawing designation."""
        return next(m for m in self.materials if m.key == key)

    def candidates(self, designation: str, form: Form | None = None) -> list[Material]:
        """All matching source rows. Callers must handle multiple matches, never pick the first."""
        normal = re.sub(r"[^A-Z0-9]", "", designation.upper())
        if not normal:
            return []
        return [
            m
            for m in self.materials
            if (form is None or m.selection.preferred_form in {form, "unspecified"})
            and normal in {re.sub(r"[^A-Z0-9]", "", s.upper()) for s in [m.key, *m.equivalents_as_printed]}
        ]

    def preferred_round_grade(self, diameter_mm: float) -> str:
        """DES-11's EN9/EN24 selection boundary; this does not forbid other engineered selections."""
        if not math.isfinite(diameter_mm) or diameter_mm <= 0:
            raise ValueError("diameter must be finite and positive")
        for material in self.materials:
            selection = material.selection
            threshold = selection.diameter_mm
            if threshold is not None and (
                (selection.diameter_operator == "<=" and diameter_mm <= threshold)
                or (selection.diameter_operator == ">" and diameter_mm > threshold)
            ):
                return material.key
        raise ValueError("no source-backed diameter selection")


def validate_sizes(values: list[float]) -> None:
    if not values or values != sorted(set(values)) or any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("stock sizes must be finite, positive, unique and increasing")


class StockMaterial(Strict):
    material: str
    material_as_printed: str
    sizes_mm: dict[StockForm, list[float]]
    sizes_as_printed: dict[StockForm, str]
    buffer_round_mm: list[float] | None
    buffer_as_printed: str
    supply_note: str | None
    unavailable_forms_as_printed: list[str] = []
    plate_sheet_dimensions_mm: list[float] | None = None
    source_location: str

    @model_validator(mode="after")
    def validate_stock(self) -> Self:
        if not self.sizes_mm or set(self.sizes_mm) != set(self.sizes_as_printed):
            raise ValueError("every transcribed stock form needs printed and numeric sizes")
        for sizes in self.sizes_mm.values():
            validate_sizes(sizes)
        if self.buffer_round_mm is not None:
            validate_sizes(self.buffer_round_mm)
        if self.plate_sheet_dimensions_mm is not None and (
            len(self.plate_sheet_dimensions_mm) != 2
            or any(not math.isfinite(v) or v <= 0 for v in self.plate_sheet_dimensions_mm)
        ):
            raise ValueError("a plate sheet needs two positive printed dimensions")
        return self


class StockAnomaly(Strict):
    material: str
    issue: Literal["buffer_size_absent_from_market_list"]
    sizes_mm: list[float]
    handling: str


class Des11Stock(Strict):
    source: Source
    scope: str
    materials: list[StockMaterial]
    source_anomalies: list[StockAnomaly]

    @model_validator(mode="after")
    def complete_stock(self) -> Self:
        names = {m.material for m in self.materials}
        if len(self.materials) != 6 or names != {"EN9", "EN24", "SAE8620", "20MnCr5", "C45", "EN19"}:
            raise ValueError("DES-11 page 2 requires exactly its six stock-material rows")
        missing = {
            m.material: set(m.buffer_round_mm or []) - set(m.sizes_mm.get("black_round", []))
            for m in self.materials
        }
        declared = {a.material: set(a.sizes_mm) for a in self.source_anomalies}
        if {k: v for k, v in missing.items() if v} != declared:
            raise ValueError("every buffer/market mismatch must be preserved and explicitly documented")
        return self
