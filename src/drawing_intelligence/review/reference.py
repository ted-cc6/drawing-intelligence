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

from drawing_intelligence.settings import get_settings


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableSource(_Strict):
    document: str
    section: str


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


TABLE_MODELS: dict[str, type[BaseModel]] = {"materials": Materials, "plating_processes": PlatingProcesses}


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
