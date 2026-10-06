"""Shared fixtures. Synthetic vector PDFs stand in for client drawings, so CI never needs client data."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from drawing_intelligence.extraction.text_layer import text_dict
from drawing_intelligence.settings import Settings

A3 = (1191, 842)
A2 = (1684, 1191)


def _text_bbox(page: pymupdf.Page, text: str, near: tuple[float, float]) -> pymupdf.Rect:
    """Bbox of the text line `text` closest to `near` (the insertion point)."""
    best = None
    for block in text_dict(page)["blocks"]:
        for line in block.get("lines", []):
            if "".join(s["text"] for s in line["spans"]).strip() == text:
                r = pymupdf.Rect(line["bbox"])
                d = abs(r.x0 - near[0]) + abs(r.y1 - near[1])
                if best is None or d < best[0]:
                    best = (d, r)
    assert best, f"text {text!r} not found"
    return best[1]


def _paren_arcs(page: pymupdf.Page, r: pymupdf.Rect) -> None:
    """Draw "(" and ")" as short vector segments, as Solid Edge does for reference dimensions."""
    for x, sign in ((r.x0 - 0.5, -1), (r.x1 + 0.5, 1)):
        ys = [r.y0 + k * (r.height / 6) for k in range(7)]
        xs = [x, x + sign * 0.6, x + sign * 0.9, x + sign * 1.0, x + sign * 0.9, x + sign * 0.6, x]
        for k in range(6):
            page.draw_line((xs[k], ys[k]), (xs[k + 1], ys[k + 1]), width=0.3)


def draw_sample_sheet(page: pymupdf.Page, overall: str = "400", drawing_no: str = "P24TEST000001") -> None:
    """A minimal drawing on the Wipro PARI layout: a dimension chain with an overall dimension, a reference
    dimension, a stacked tolerance, a view label, a note, a title block and a tolerance-table entry."""
    w, h = page.rect.width, page.rect.height
    # chain 135 + 130 + (135) along y=285, overall dimension along y=245
    for x0, x1 in ((280, 330), (330, 360), (360, 410)):
        page.draw_line((x0, 285), (x1, 285), width=0.3)
    page.draw_line((280, 245), (410, 245), width=0.3)
    page.insert_text((300, 280), "135", fontsize=10)
    page.insert_text((335, 280), "130", fontsize=10)
    page.insert_text((375, 280), "135", fontsize=10)
    page.insert_text((335, 240), overall, fontsize=10)
    _paren_arcs(page, _text_bbox(page, "135", (375, 280)))
    # stacked tolerance: nominal 11 with -0.1 / -0.2 to its right
    page.insert_text((500, 500), "11", fontsize=10)
    page.insert_text((516, 494), "-0.1", fontsize=6)
    page.insert_text((516, 502), "-0.2", fontsize=6)
    page.insert_text((300, 400), "SECTION A-A", fontsize=10)
    page.insert_text((100, 600), "2. DO NOT SCALE DRAWING", fontsize=10)
    # title block (bottom-right corner) and tolerance table (right strip)
    page.insert_text((w - 300, h - 60), drawing_no, fontsize=10)
    page.insert_text((w - 300, h - 40), "MATERIAL: EN8", fontsize=10)
    page.insert_text((w - 110, 300), "6 UP TO 30", fontsize=8)


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    def _make(name: str = "sample.pdf", size: tuple[int, int] = A3, pages: int = 1, **kwargs) -> Path:
        doc = pymupdf.open()
        for _ in range(pages):
            draw_sample_sheet(doc.new_page(width=size[0], height=size[1]), **kwargs)
        path = tmp_path / name
        doc.save(path)
        doc.close()
        return path

    return _make


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings isolated in a temp data dir, ephemeral, with fake keys (no real API is ever called)."""
    kwargs: dict[str, Any] = {
        "_env_file": None,
        "data_dir": tmp_path / "data",
        "retention": "ephemeral",
        "OPENAI_API_KEY": "sk-fake",
        "QWEN_API_KEY": "qwen-fake",
    }
    return Settings(**kwargs)
