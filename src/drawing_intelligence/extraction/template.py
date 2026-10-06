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


class Template(BaseModel):
    name: str
    reference_sheet_pts: tuple[float, float]
    regions: dict[str, tuple[str | float, str | float, str | float, str | float]]
    exclude_from_dimensions: list[str]
    glyph_remap: list[GlyphRemap] = []

    def regions_for(self, width: float, height: float) -> dict[str, Rect]:
        """Every region resolved to absolute PDF points for a sheet of this size."""
        out: dict[str, Rect] = {}
        for name, coords in self.regions.items():
            x0, y0, x1, y1 = (_resolve(c, width, height) for c in coords)
            out[name] = (x0, y0, x1, y1)
        return out

    def excluded_rects(self, width: float, height: float) -> list[Rect]:
        regions = self.regions_for(width, height)
        return [regions[name] for name in self.exclude_from_dimensions]


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
