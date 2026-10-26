"""The transcribed standards tables, checked against the structure of the standards themselves, so a misread
digit in the scan shows up here rather than as a wrong finding."""

from __future__ import annotations

import itertools

import pytest

from drawing_intelligence.review.reference import (
    FitDeviations,
    GeneralTolerances,
    MetricThreads,
    load_reference,
)

# ISO 286-1 standard tolerance grades (µm) for the 13 size steps 0-3 ... 400-500 mm
IT = {
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400],
}


@pytest.fixture(scope="module")
def ref():
    return load_reference()


def test_every_zone_is_its_grade_wide(ref):
    fits: FitDeviations = ref["is919_fits"]
    for zone, devs in fits.zones.items():
        grade = int(zone.lstrip("ABCDEFGHJKMNPabcdefghjkmnp"))
        assert [u - lo for u, lo in devs] == IT[grade], zone


def test_fundamental_deviations_agree_across_grades_and_mirror(ref):
    zones = ref["is919_fits"].zones
    # shafts a-h: the upper deviation is the fundamental one, the same for every grade
    for letter in "dfgh":
        uppers = {z: [u for u, _ in d] for z, d in zones.items() if z.rstrip("0123456789") == letter}
        assert len({tuple(v) for v in uppers.values()}) == 1, uppers.keys()
    # holes A-H mirror the shafts: lower deviation = - shaft upper (F7 vs f7, G6 vs g6, D9 vs d8, E8 vs e8)
    for hole, shaft in (("F7", "f7"), ("F6", "f6"), ("G6", "g6"), ("G7", "g6"), ("D9", "d8"), ("E8", "e8")):
        assert [lo for _, lo in zones[hole]] == [-u for u, _ in zones[shaft]], hole
    for z, d in zones.items():  # H holes start at 0, h shafts end at 0
        if z[0] == "H":
            assert all(lo == 0 for _, lo in d), z
        if z[0] == "h":
            assert all(u == 0 for u, _ in d), z


def test_worked_examples_from_the_book(ref):
    fits: FitDeviations = ref["is919_fits"]
    assert fits.deviations("H7", 20) == (21, 0)  # pdf 42L: 20ϕH7 = +0.021/0
    assert fits.deviations("H7", 18) == (18, 0) and fits.deviations("H7", 18.01) == (
        21,
        0,
    )  # "up to and including"
    assert fits.deviations("H7", 600) is None and fits.deviations("r6", 20) is None
    assert fits.valid_code("H", 7) and fits.valid_code("js", 9) and not fits.valid_code("I", 7)
    assert not fits.valid_code("H", 71) and not fits.valid_code("Hg", 7)


def test_general_tolerances_widen_with_size_and_class(ref):
    gt: GeneralTolerances = ref["is2102_general_tolerances"]
    for table in (gt.linear, gt.angular):
        rows = list(table.classes().values())
        for values in rows:
            assert len(values) == len(table.steps_mm)
        for finer, coarser in itertools.pairwise(rows):  # each class at least as wide as the one before
            assert all(f <= c for f, c in zip(finer, coarser, strict=True) if f is not None and c is not None)
    medium = [v for v in gt.linear.medium if v is not None]
    assert medium == sorted(medium)
    assert [v for v in gt.angular.medium if v] == [
        60,
        30,
        20,
        10,
    ]  # PARI's machining table: ±1°, 30', 20', 10'


def test_threads_agree_with_the_book(ref):
    t: MetricThreads = ref["iso_metric_threads"]
    book_coarse = {1.6: 0.35, 2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8, 6: 1, 8: 1.25, 10: 1.5, 12: 1.75,
                   16: 2, 20: 2.5, 24: 3, 30: 3.5, 36: 4}  # pdf 45R  # fmt: skip
    assert {d: t.sizes[d].coarse for d in book_coarse} == book_coarse
    for d, p in ((8, 1), (10, 1.25), (12, 1.25), (16, 1.5), (20, 1.5), (24, 2), (30, 2), (36, 3)):  # pdf 46L
        assert p in t.sizes[d].fine
    assert t.sizes[35].coarse is None and t.pitches(35) == {1.5}
