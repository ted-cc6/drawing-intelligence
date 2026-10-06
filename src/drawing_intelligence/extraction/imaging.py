"""Page images for the vision LLM: a full-page overview, overlapping zoomed tiles and a title-block close-up.

The tiling is configurable because image tokens dominate the cost of the understanding call; `di eval`
compares settings.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image
from pydantic import BaseModel, Field

from drawing_intelligence.extraction.template import Rect
from drawing_intelligence.schemas import ImageSet, Tile


class ImagingConfig(BaseModel):
    dpi: int = Field(default=250, description="render resolution for tiles and the title-block crop")
    grid_rows: int = 2
    grid_cols: int = 3
    overlap: float = Field(default=0.08, description="tile overlap as a fraction of tile size")
    overview_max_px: int = Field(default=1568, description="longest side of the full-page overview")
    title_block: bool = True


def render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def tile_boxes(width: int, height: int, cfg: ImagingConfig) -> list[tuple[str, tuple[int, int, int, int]]]:
    tw, th = width / cfg.grid_cols, height / cfg.grid_rows
    ow, oh = cfg.overlap * tw, cfg.overlap * th
    boxes = []
    for i in range(cfg.grid_rows):
        for j in range(cfg.grid_cols):
            box = (
                max(0, int(j * tw - ow)),
                max(0, int(i * th - oh)),
                min(width, int((j + 1) * tw + ow)),
                min(height, int((i + 1) * th + oh)),
            )
            boxes.append((f"tile_r{i}c{j}.png", box))
    return boxes


def export_page_images(
    page: pymupdf.Page, title_block: Rect | None, root: Path, subdir: str, cfg: ImagingConfig
) -> ImageSet:
    """Write the page's images to root/subdir; returned paths are relative to root."""
    folder = root / subdir
    folder.mkdir(parents=True, exist_ok=True)
    img = render_page(page, cfg.dpi)

    overview = img.copy()
    overview.thumbnail((cfg.overview_max_px, cfg.overview_max_px))
    overview.save(folder / "page_full.png")

    tiles = []
    for name, box in tile_boxes(img.width, img.height, cfg):
        img.crop(box).save(folder / name)
        tiles.append(Tile(file=f"{subdir}/{name}", pixel_box=box))

    tb_file = None
    if cfg.title_block and title_block:
        z = cfg.dpi / 72
        x0, y0, x1, y1 = (int(v * z) for v in title_block)
        img.crop((x0, y0, x1, y1)).save(folder / "title_block.png")
        tb_file = f"{subdir}/title_block.png"

    return ImageSet(dpi=cfg.dpi, full=f"{subdir}/page_full.png", title_block=tb_file, tiles=tiles)
