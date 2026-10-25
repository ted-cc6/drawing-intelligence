"""Stage 1 symbols: GD&T frame parsing and the vector detectors for datum flags and finish marks."""

from __future__ import annotations

import math
from pathlib import Path

import pymupdf
import pytest

from drawing_intelligence.extraction import load_template
from drawing_intelligence.extraction.symbols import parse_frame, read_symbols

A3 = (1191, 842)


@pytest.mark.parametrize(
    ("raw", "characteristic", "tolerance", "datums"),
    [
        ("n 0.05 A", "perpendicularity", "0.05", ["A"]),
        ("l O0.1 A B C", "position", "⌀0.1", ["A", "B", "C"]),
        ("r 0.02", "flatness", "0.02", []),
        ("^ 0.03 A-B", "circular_runout", "0.03 A-B", []),
    ],
)
def test_frame_parsing(raw, characteristic, tolerance, datums):
    assert parse_frame(raw) == {"characteristic": characteristic, "tolerance": tolerance, "datums": datums}


def test_not_a_frame():
    assert parse_frame("O") is None and parse_frame("") is None  # the diameter glyph alone is not a frame


def _box(page: pymupdf.Page, x: float, y: float, size: float = 12) -> None:
    for a, b in (((x, y), (x + size, y)), ((x + size, y), (x + size, y + size)),
                 ((x + size, y + size), (x, y + size)), ((x, y + size), (x, y))):  # fmt: skip
        page.draw_line(a, b, width=0.3)


def _stroked_triangle(page: pymupdf.Page, x: float, y: float, side: float = 8) -> None:
    h = side * math.sqrt(3) / 2
    p1, p2, p3 = (x, y), (x + side, y), (x + side / 2, y + h)
    for a, b in ((p1, p2), (p2, p3), (p3, p1)):
        page.draw_line(a, b, width=0.3)


def symbols_of(tmp_path: Path, draw) -> list:
    doc = pymupdf.open()
    page = doc.new_page(width=A3[0], height=A3[1])
    draw(page)
    path = tmp_path / "s.pdf"
    doc.save(path)
    with pymupdf.open(path) as d:
        return read_symbols(d[0], load_template())


def test_boxed_letter_is_a_datum_flag(tmp_path: Path):
    def draw(page):
        _box(page, 300, 300)
        page.insert_text((303, 310), "A", fontsize=9)
        page.insert_text((500, 310), "B", fontsize=9)  # a lone letter is not a flag

    syms = symbols_of(tmp_path, draw)
    assert [(s.type, s.datums) for s in syms] == [("datum", ["A"])]
    assert syms[0].id == "S1" and syms[0].provenance == "vector"


def test_letter_by_a_filled_triangle_is_a_datum_flag(tmp_path: Path):
    def draw(page):
        page.draw_polyline([(400, 330), (410, 330), (405, 321.3), (400, 330)], fill=(0, 0, 0), width=0.3)
        page.insert_text((402, 315), "C", fontsize=9)

    assert [s.text for s in symbols_of(tmp_path, draw)] == ["datum C"]


def test_triangle_cluster_is_a_machining_mark_but_not_a_revision_triangle(tmp_path: Path):
    def draw(page):
        _stroked_triangle(page, 300, 400)
        _stroked_triangle(page, 309, 400)  # "VV": two triangles, one mark
        _stroked_triangle(page, 600, 400, side=14)
        page.insert_text((604, 411), "1", fontsize=7)  # Δ1: a revision mark

    syms = symbols_of(tmp_path, draw)
    assert [(s.type, s.text) for s in syms] == [("surface_finish", "machining mark")]


def test_ra_value_by_a_check_mark(tmp_path: Path):
    def draw(page):
        page.draw_line((500, 500), (505, 509), width=0.3)  # short arm of the √
        page.draw_line((505, 509), (520, 483), width=0.3)  # long arm, ~60° to the short one
        page.insert_text((512, 490), "3.2", fontsize=8)

    syms = symbols_of(tmp_path, draw)
    assert [(s.type, s.ra) for s in syms] == [("surface_finish", "3.2")]


def test_symbols_in_the_title_block_are_left_out(tmp_path: Path):
    def draw(page):
        _box(page, A3[0] - 100, A3[1] - 80)
        page.insert_text((A3[0] - 97, A3[1] - 70), "A", fontsize=9)

    assert symbols_of(tmp_path, draw) == []
