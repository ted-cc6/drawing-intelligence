"""Annotated images for a human reviewer. Never needed by the pipeline itself."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from drawing_intelligence.schemas import DrawingKnowledge, PageExtraction

GREEN, BLUE, ORANGE, PINK, RED = (0, 150, 0), (0, 90, 220), (230, 120, 0), (200, 0, 160), (220, 0, 0)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def full_sheet(root: Path, page: PageExtraction) -> Image.Image:
    """The full-resolution sheet, re-assembled from the tiles sent to the model."""
    assert page.images is not None, "page has no images"
    tiles = page.images.tiles
    w = max(t.pixel_box[2] for t in tiles)
    h = max(t.pixel_box[3] for t in tiles)
    sheet = Image.new("RGB", (w, h), "white")
    for t in tiles:
        sheet.paste(Image.open(root / t.file).convert("RGB"), t.pixel_box[:2])
    return sheet


def _scaled(root: Path, page: PageExtraction, width: int) -> tuple[Image.Image, float]:
    sheet = full_sheet(root, page)
    s = width / sheet.width
    assert page.images is not None
    return sheet.resize((width, int(sheet.height * s))), page.images.dpi / 72 * s  # PDF points -> pixels


def _legend(draw: ImageDraw.ImageDraw, entries: list[tuple[str, tuple[int, int, int]]]) -> None:
    for i, (label, color) in enumerate(entries):
        draw.rectangle([30, 30 + 34 * i, 56, 56 + 34 * i], fill=color)
        draw.text((66, 32 + 34 * i), label, fill=(0, 0, 0), font=_font(20))


def extraction_diagram(root: Path, page: PageExtraction, width: int = 2200) -> Image.Image:
    """Stage 1 result: dimensions, view labels, notes and the dimension lines matched to them."""
    img, k = _scaled(root, page, width)
    draw, font = ImageDraw.Draw(img), _font(15)
    for items, color in ((page.dimensions, GREEN), (page.view_labels, BLUE), (page.notes, ORANGE)):
        for it in items:
            x0, y0, x1, y1 = (v * k for v in it.bbox)
            draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], outline=color, width=2)
            draw.text((x0, y0 - 17), it.id or it.text[:20], fill=color, font=font)
    for m in page.matched_lines:
        x0, y0, x1, y1 = (v * k for v in m.line)
        draw.line([x0, y0, x1, y1], fill=PINK, width=3)
    _legend(
        draw, [("Dimension", GREEN), ("View label", BLUE), ("Note", ORANGE), ("Matched dimension line", PINK)]
    )
    return img


def _valid_bbox(b: list[float] | None) -> bool:
    return b is not None and len(b) == 4


def knowledge_overlay(
    root: Path, page: PageExtraction, k: DrawingKnowledge, width: int = 2200
) -> Image.Image:
    """Stage 2 result: dimensions by source and the symbols the model found (approximate positions)."""
    img, s = _scaled(root, page, width)
    draw, font = ImageDraw.Draw(img), _font(16)
    items = [(d.bbox, GREEN if d.source == "pdf_text" else ORANGE, d.id) for d in k.dimensions]
    items += [(sy.bbox, RED, f"{sy.id} {sy.type}") for sy in k.symbols]
    for bbox, color, label in items:
        if bbox is None or not _valid_bbox(bbox):
            continue
        x0, y0, x1, y1 = (v * s for v in bbox)
        draw.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], outline=color, width=3)
        draw.text((x0, y0 - 19), label, fill=color, font=font)
    _legend(
        draw,
        [
            ("dimension from PDF text", GREEN),
            ("dimension from image only", ORANGE),
            ("symbol found in image (approx. position)", RED),
        ],
    )
    return img


def symbol_gallery(
    root: Path, page: PageExtraction, k: DrawingKnowledge, pad_pt: float = 18, cols: int = 5
) -> Image.Image | None:
    """A close-up of every symbol the model reported, so a reviewer can confirm each one by eye."""
    syms = [sy for sy in k.symbols if sy.bbox is not None and _valid_bbox(sy.bbox)]
    if not syms:
        return None
    assert page.images is not None
    sheet, z = full_sheet(root, page), page.images.dpi / 72
    cw, ch = 300, 220
    out = Image.new("RGB", (cols * cw, ((len(syms) + cols - 1) // cols) * (ch + 40)), "white")
    draw, font = ImageDraw.Draw(out), _font(15)
    for n, sy in enumerate(syms):
        assert sy.bbox is not None
        x0, y0, x1, y1 = sy.bbox
        box = (
            max(0, int((x0 - pad_pt) * z)),
            max(0, int((y0 - pad_pt) * z)),
            min(sheet.width, int((x1 + pad_pt) * z)),
            min(sheet.height, int((y1 + pad_pt) * z)),
        )
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        crop = sheet.crop(box)
        crop.thumbnail((cw - 10, ch - 10))
        cx, cy = (n % cols) * cw, (n // cols) * (ch + 40)
        out.paste(crop, (cx + 5, cy + 5))
        draw.rectangle([cx + 4, cy + 4, cx + 6 + crop.width, cy + 6 + crop.height], outline=RED, width=2)
        draw.text(
            (cx + 5, cy + ch - 2), f"{sy.id} {sy.type}: {str(sy.value)[:30]}", fill=(0, 0, 0), font=font
        )
    return out
