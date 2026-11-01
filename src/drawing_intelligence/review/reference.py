"""Reference tables for the `lookup` rules (`config/reference/*.yaml`): data, validated, cited (ADR 0010).

Each table is a YAML file named as the rules' `params.table` names it. A table this module knows is validated
into its model; `load_reference()` returns them by name for `ReviewContext.reference`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from drawing_intelligence.review.reference_des11 import Des11Stock, MaterialHeatTreatment
from drawing_intelligence.review.reference_p2 import P2_MODELS
from drawing_intelligence.settings import get_settings


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableSource(_Strict):
    document: str
    section: str
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class MaterialClass(_Strict):
    class_: str = Field(alias="class")
    patterns: list[str]


class Materials(_Strict):
    """Title-block material designation -> class (mild_steel, aluminium, plastic, ...) -> family."""

    source: TableSource
    families: dict[str, list[str]]
    classes: list[MaterialClass]

    @model_validator(mode="after")
    def _every_class_has_a_family(self) -> Materials:
        known = {c for members in self.families.values() for c in members}
        missing = sorted({c.class_ for c in self.classes} - known)
        if missing:
            raise ValueError(f"material classes with no family: {missing}")
        return self

    def classify(self, designation: str | None) -> str | None:
        """The material class of a designation as printed, or None if it is not recognised."""
        if not designation:
            return None
        for c in self.classes:
            if any(re.search(p, designation, re.IGNORECASE) for p in c.patterns):
                return c.class_
        return None

    def family(self, material_class: str | None) -> str | None:
        return next((f for f, members in self.families.items() if material_class in members), None)


class PlatingProcess(_Strict):
    id: str
    name: str
    patterns: list[str]
    materials: list[str]
    source_row: int | None = Field(default=None, ge=1, le=10)
    prerequisites_as_printed: str | None = None
    process_constraints_as_printed: str | None = None
    remarks_as_printed: str | None = None


class PlatingProcesses(_Strict):
    """PARI's plating processes (DES-12) and the material classes each suits."""

    source: TableSource
    processes: list[PlatingProcess]

    def identify(self, treatment: str | None) -> PlatingProcess | None:
        if not treatment:
            return None
        for p in self.processes:
            if any(re.search(pat, treatment, re.IGNORECASE) for pat in p.patterns):
                return p
        return None


def _step(steps: list[list[float]], size: float, *, open_last: bool = False) -> int | None:
    """Index of the step 'over a, up to and including b' holding `size` (the first step includes a)."""
    for i, (low, high) in enumerate(steps):
        if (size >= low if i == 0 else size > low) and (size <= high or (open_last and high is None)):
            return i
    return None


class FitDeviations(_Strict):
    """IS 919 / ISO 286 deviations (µm) per tolerance zone and size step (is919_fits.yaml)."""

    source: TableSource
    steps_mm: list[list[float]]
    zones: dict[str, list[list[int]]]
    hole_letters: list[str]
    grades: list[int]

    @model_validator(mode="after")
    def _one_pair_per_step(self) -> FitDeviations:
        bad = sorted(z for z, devs in self.zones.items() if len(devs) != len(self.steps_mm) or any(
            len(d) != 2 or d[0] <= d[1] for d in devs))  # fmt: skip
        if bad:
            raise ValueError(f"zones without one [upper, lower] pair per size step: {bad}")
        return self

    def valid_code(self, letters: str, grade: int) -> bool:
        """A code ISO 286 defines: a deviation letter (capital for holes, small for shafts) and a grade."""
        if letters not in self.hole_letters and letters not in {x.lower() for x in self.hole_letters}:
            return False
        return self.grades[0] <= grade <= self.grades[1]

    def deviations(self, zone: str, size: float) -> tuple[int, int] | None:
        """(upper, lower) in µm, or None when the zone or the size is not in the table."""
        i = _step(self.steps_mm, size) if zone in self.zones else None
        return None if i is None else (self.zones[zone][i][0], self.zones[zone][i][1])


class ToleranceClasses(_Strict):
    steps_mm: list[list[float | None]]
    fine: list[float | None]
    medium: list[float | None]
    coarse: list[float | None]
    extra_coarse: list[float | None]

    def classes(self) -> dict[str, list[float | None]]:
        return {
            "fine": self.fine,
            "medium": self.medium,
            "coarse": self.coarse,
            "extra coarse": self.extra_coarse,
        }

    def step_from(self, over: float) -> int | None:
        """The step starting at `over`: printed rows ('OVER 2000', '120 UP TO 400') match by their start."""
        return next(
            (i for i, (low, _) in enumerate(self.steps_mm) if low == over or (i == 0 and over == 0)), None
        )


class GeneralTolerances(_Strict):
    """IS 2102-1969 general tolerances by class: linear in ± mm, angular in ± minutes of arc."""

    source: TableSource
    linear: ToleranceClasses
    angular: ToleranceClasses


class ThreadSize(_Strict):
    coarse: float | None
    fine: list[float]


class MetricThreads(_Strict):
    """ISO 261 sizes and pitches, and the IS 4218 tabulated tolerance classes (iso_metric_threads.yaml)."""

    source: TableSource
    sizes: dict[float, ThreadSize]
    tolerance_classes: dict[str, dict[str, float]]

    def pitches(self, size: float) -> set[float]:
        s = self.sizes[size]
        return set(s.fine) | ({s.coarse} if s.coarse else set())

    @property
    def largest(self) -> float:
        return max(self.sizes)


TABLE_MODELS: dict[str, type[BaseModel]] = {
    **P2_MODELS,
    "material_heat_treatment": MaterialHeatTreatment,
    "raw_material_sizes_des11": Des11Stock,
    "materials": Materials,
    "plating_processes": PlatingProcesses,
    "is919_fits": FitDeviations,
    "is2102_general_tolerances": GeneralTolerances,
    "iso_metric_threads": MetricThreads,
}


class ReferenceTableError(ValueError):
    pass


def reference_files(folder: Path | None = None) -> list[Path]:
    folder = folder or get_settings().config_path / "reference"
    return sorted(folder.glob("*.yaml")) if folder.is_dir() else []


def load_reference(folder: Path | None = None) -> dict[str, Any]:
    """Every table by name, validated when its model is known. A missing folder means no tables."""
    tables: dict[str, Any] = {}
    problems = []
    for f in reference_files(folder):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        model = TABLE_MODELS.get(f.stem)
        try:
            tables[f.stem] = model.model_validate(data) if model else data
        except ValueError as e:
            problems.append(f"{f.name}: {e}")
    if problems:
        raise ReferenceTableError("problems in the reference tables:\n" + "\n".join(problems))
    return tables
