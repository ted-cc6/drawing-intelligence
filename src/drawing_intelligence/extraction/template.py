"""Drawing-template configuration: where the title block, tolerance table and borders sit on the sheet."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel

from drawing_intelligence.settings import get_settings

Rect = tuple[float, float, float, float]

_COORD = re.compile(
    r"^\s*(?:(?P<edge>[WH])\s*(?:(?P<sign>[+-])\s*(?P<off>\d+(?:\.\d+)?))?|(?P<num>-?\d+(?:\.\d+)?))\s*$"
)


class GlyphRemap(BaseModel):
    font_contains: str
    char: str
    replace_with: str


Coords = tuple[str | float, str | float, str | float, str | float]


class Anchor(BaseModel):
    text: str
    at: tuple[str | float, str | float]


class Template(BaseModel):
    name: str
    reference_sheet_pts: tuple[float, float]
    regions: dict[str, Coords]
    exclude_from_dimensions: list[str]
    glyph_remap: list[GlyphRemap] = []
    title_block_fields: dict[str, Coords] = {}
    title_block_prefixes: dict[str, str] = {}
    title_block_anchors: list[Anchor] = []
    title_block_min_anchors: int = 0
    revision_rows: Coords | None = None
    revision_number_column: Coords | None = None
    units_pattern: str | None = None
    date_format: str = "%d/%m/%Y"

    def regions_for(self, width: float, height: float) -> dict[str, Rect]:
        """Every region resolved to absolute PDF points for a sheet of this size."""
        return {name: resolve_rect(coords, width, height) for name, coords in self.regions.items()}

    def field_cells(self, width: float, height: float) -> dict[str, Rect]:
        return {name: resolve_rect(coords, width, height) for name, coords in self.title_block_fields.items()}

    def anchors_for(self, width: float, height: float) -> list[tuple[str, float, float]]:
        return [
            (a.text, _resolve(a.at[0], width, height), _resolve(a.at[1], width, height))
            for a in self.title_block_anchors
        ]

    def excluded_rects(self, width: float, height: float) -> list[Rect]:
        regions = self.regions_for(width, height)
        return [regions[name] for name in self.exclude_from_dimensions]


def resolve_rect(coords: Coords, width: float, height: float) -> Rect:
    """A template rectangle (numbers or W/H expressions) in absolute PDF points."""
    x0, y0, x1, y1 = (_resolve(c, width, height) for c in coords)
    return (x0, y0, x1, y1)


def _resolve(value: str | float, width: float, height: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    m = _COORD.match(value)
    if not m:
        raise ValueError(f"bad template coordinate {value!r}: use a number, W, H, 'W-123' or 'H-45'")
    if m["num"] is not None:
        return float(m["num"])
    base = width if m["edge"] == "W" else height
    off = float(m["off"] or 0)
    return base - off if m["sign"] == "-" else base + off


def load_template(name: str = "wipro_pari", config_dir: Path | None = None) -> Template:
    folder = (config_dir or get_settings().config_path) / "templates"
    path = folder / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in folder.glob("*.yaml"))
        raise FileNotFoundError(f"template {name!r} not found in {folder}; available: {available}")
    return Template.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
