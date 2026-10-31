"""The check machinery and the first code checks (ADR 0010), on synthetic stage 1 data. No PDF, no LLM."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Literal

import pytest

from drawing_intelligence.extraction import load_template
from drawing_intelligence.review import load_rulebook
from drawing_intelligence.review.checks import NotApplicable, NotCheckable, param_models, registered
from drawing_intelligence.review.checks._geometry import MM_PTS
from drawing_intelligence.review.checks._registry import CheckSpec, NoParams
from drawing_intelligence.review.checks._tolerance import general_for, parse
from drawing_intelligence.review.context import ReviewContext
from drawing_intelligence.review.reference import load_reference
from drawing_intelligence.review.reviewers import LLM_REVIEWER_FOR_CATEGORY, reviewer_for
from drawing_intelligence.review.rulebook import Rule, Rulebook, RuleSource, new_finding
from drawing_intelligence.review.runner import run_checks, run_rule
from drawing_intelligence.schemas import (
    ChainCheck,
    EvidenceRef,
    Extraction,
    GeneralToleranceRow,
    MatchedLine,
    PageExtraction,
    SymbolItem,
    TextItem,
    TextLine,
    TitleBlockField,
)

TEMPLATE = load_template()
GOOD_FIELDS = {
    "number": "P24TEST000001",
    "title": "TEST PLATE",
    "material": "M.S.",
    "surface_treatment": "N.A.",
    "weight": "0.25 kg",
    "units": "mm",
    "general_tolerance_standard": "IS 2102",
    "revision": "00",
    "scale": "1 : 1",
    "drawn_date": "01/10/2025",
    "checked_date": None,
    "approved_date": None,
}


def fields(**overrides: str | None) -> dict[str, TitleBlockField]:
    values = {**GOOD_FIELDS, **overrides}
    return {k: TitleBlockField(value=v, bbox=(900.0, 780.0, 950.0, 790.0)) for k, v in values.items()}


def dim(i: int, text: str, x: float = 100.0, y: float = 100.0) -> TextItem:
    return TextItem(id=f"D{i}", text=text, bbox=(x, y, x + 10, y + 8))


def drawn(i: int, text: str, length_mm: float, orientation: str = "horizontal", y: float = 100.0):
    """A dimension and its matched line, `length_mm` long on paper."""
    d = dim(i, text, y=y)
    length = length_mm * MM_PTS
    line = (
        (100.0, y + 10, 100.0 + length, y + 10)
        if orientation == "horizontal"
        else (100.0, y, 100.0, y + length)
    )
    return d, MatchedLine(dimension_id=d.id or "", line=line, orientation=orientation)  # type: ignore[arg-type]


def page(**kw) -> PageExtraction:
    base = {
        "page_number": 1,
        "page_size_pts": (1191.0, 842.0),
        "rotation": 0,
        "title_block_layout": "standard",
        "title_block_fields": fields(),
        "scale_pts_per_mm": MM_PTS,
    }
    return PageExtraction(**{**base, **kw})


def rule(check: str, check_type: str = "code", **params) -> Rule:
    return Rule(
        id="XX-001",
        category="consistency",
        requirement="test requirement",
        severity="major",
        check_type=check_type,  # type: ignore[arg-type]
        check=check,
        params=params,
        source=RuleSource(document="test", section="1"),
    )


REFERENCE = load_reference()


def ctx(*pages: PageExtraction, rules: list[Rule] | None = None) -> ReviewContext:
    ex = Extraction(source_file="t.pdf", template="wipro_pari", n_pages=len(pages), pages=list(pages))
    return ReviewContext(
        extraction=ex,
        rulebook=Rulebook(version="t", rules=rules or []),
        template=TEMPLATE,
        reference=REFERENCE,
    )


def run(check: str, *pages: PageExtraction, **params):
    r = rule(check, **params)
    return run_rule(ctx(*pages), r, registered()[check])


# --- machinery ----------------------------------------------------------------------------------------------


def test_every_rule_names_a_check_whose_params_fit():
    # Loading with the registry validates the params of every built check against the real rulebook.
    book = load_rulebook(checks=param_models())
    built = {r.check for r in book.rules if r.check in param_models()}
    assert built == set(param_models())  # every registered check is used by at least one rule


def test_unbuilt_check_is_not_checked_and_inapplicable_rule_is_not_applicable():
    r = rule("no_such_check")
    findings, status = run_rule(ctx(page()), r, None)
    assert (findings, status.status) == ([], "not_checked") and "not built" in (status.note or "")
    r2 = r.model_copy(update={"applies_to": r.applies_to.model_copy(update={"part_family": ["round"]})})
    c = ctx(page())
    c = ReviewContext(**{**c.__dict__, "part_family": "prismatic"})
    assert run_rule(c, r2, None)[1].status == "not_applicable"


def _spec(fn) -> CheckSpec:
    return CheckSpec("test", fn, NoParams)


def test_outcome_exceptions_and_crashes_become_statuses():
    def na(*_):
        raise NotApplicable("no threads")

    def nc(*_):
        raise NotCheckable("no title block")

    def boom(*_):
        raise ZeroDivisionError("bug")

    r = rule("test")
    assert run_rule(ctx(page()), r, _spec(na))[1].model_dump()["status"] == "not_applicable"
    assert run_rule(ctx(page()), r, _spec(nc))[1].note == "no title block"
    status = run_rule(ctx(page()), r, _spec(boom))[1]
    assert status.status == "not_checked" and "ZeroDivisionError" in (status.note or "")


def test_findings_for_another_rule_are_refused_and_duplicates_merged():
    r = rule("test")
    other = r.model_copy(update={"id": "XX-002"})
    ev = [EvidenceRef(kind="dimension", ref="D1", page=1, quote="10", provenance="pdf_text")]

    def twice(c, rl, _):
        return [new_finding(rl, reviewer="checks", evidence=ev, comment="a") for _ in range(2)]

    def wrong(c, rl, _):
        return [new_finding(other, reviewer="checks", evidence=ev, comment="a")]

    findings, status = run_rule(ctx(page()), r, _spec(twice))
    assert len(findings) == 1 and status.status == "fail" and status.finding_ids == [findings[0].id]
    assert run_rule(ctx(page()), r, _spec(wrong))[1].status == "not_checked"


def test_run_checks_covers_code_and_lookup_rules_only():
    rules = [
        rule("chain_sum"),
        rule("x", check_type="llm").model_copy(update={"id": "XX-002", "check": None}),
    ]
    out = run_checks(ctx(page(), rules=rules))
    assert out.reviewer == "checks" and [s.rule_id for s in out.rule_statuses] == ["XX-001"]


def test_every_llm_rule_has_a_reviewer():
    book = load_rulebook()
    assert {reviewer_for(r) for r in book.rules if r.check_type == "llm"} <= set(
        LLM_REVIEWER_FOR_CATEGORY.values()
    )
    assert {reviewer_for(r) for r in book.rules if r.check_type != "llm"} == {"checks"}


# --- consistency --------------------------------------------------------------------------------------------


def chain(match: bool) -> PageExtraction:
    return page(
        dimensions=[dim(1, "35"), dim(2, "30"), dim(3, "(35)"), dim(4, "105" if not match else "100")],
        chain_checks=[
            ChainCheck(
                chain_texts=["35", "30", "(35)"],
                chain_ids=["D1", "D2", "D3"],
                chain_sum=100,
                overall_text="105" if not match else "100",
                overall_id="D4",
                overall_value=105 if not match else 100,
                match=match,
                diff=5 if not match else 0,
            )
        ],
    )


def test_chain_sum():
    findings, status = run("chain_sum", chain(match=False))
    assert status.status == "fail" and {e.ref for e in findings[0].evidence} == {"D1", "D2", "D3", "D4"}
    assert run("chain_sum", chain(match=True))[1].status == "pass"
    assert run("chain_sum", page())[1].status == "not_applicable"


def test_reference_dim_consistent_cites_the_reference_first():
    findings, status = run("reference_dim_consistent", chain(match=False))
    assert status.status == "fail" and findings[0].evidence[0].ref == "D3"
    plain = chain(match=False)
    plain.dimensions[2] = dim(3, "35")
    assert run("reference_dim_consistent", plain)[1].status == "not_applicable"


def scaled_page(*dims_and_lines, **kw) -> PageExtraction:
    return page(dimensions=[d for d, _ in dims_and_lines], matched_lines=[m for _, m in dims_and_lines], **kw)


def test_conflicting_values_flags_a_value_drawn_like_its_neighbour():
    to_scale = [drawn(1, "40", 40, y=100), drawn(2, "60", 60, y=150), drawn(3, "15", 15, "vertical", y=200)]
    typo = drawn(4, "17", 15, "vertical", y=300)  # drawn 15 mm long, says 17
    findings, status = run("conflicting_values", scaled_page(*to_scale, typo))
    assert status.status == "fail" and [e.ref for e in findings[0].evidence] == ["D4", "D3"]
    assert run("conflicting_values", scaled_page(*to_scale))[1].status == "pass"


def test_conflicting_values_ignores_radii_angles_references_and_detail_views():
    to_scale = [drawn(1, "40", 40, y=100), drawn(2, "60", 60, y=150), drawn(3, "15", 15, "vertical", y=200)]
    for text in ("R 17", "17°", "(17)"):
        assert (
            run("conflicting_values", scaled_page(*to_scale, drawn(4, text, 15, "vertical", y=300)))[1].status
            == "pass"
        )
    # A 2:1 detail: values drawn at twice their size, supported by enough dimensions, are not typos.
    detail = [drawn(5, "10", 20, y=400), drawn(6, "12", 24, y=420), drawn(7, "7.5", 15, "vertical", y=440)]
    assert run("conflicting_values", scaled_page(*to_scale, *detail))[1].status == "pass"


def test_conflicting_values_needs_a_measurable_scale():
    assert run("conflicting_values", page())[1].status == "not_checked"


def test_inch_mark_after_a_value_is_flagged_but_not_in_notes():
    p = page(
        other_numeric=[TextItem(text='3.94"', bbox=(300, 500, 320, 510))],
        notes=[TextItem(text='1/2" BSP PORT', bbox=(100, 700, 160, 710))],
    )
    findings, status = run("no_mixed_unit_systems", p, flag_units=["psi"], flag_on_dimensions=['"', "in"])
    assert status.status == "fail" and [f.evidence[0].quote for f in findings] == ['3.94"']


def test_units_flagged_anywhere_except_excluded_fields():
    p = page(
        notes=[TextItem(text="TEST TO 200 psi", bbox=(100, 700, 160, 710))],
        title_block_fields=fields(surface_area="15.54 psi"),
    )
    findings, _ = run("no_mixed_unit_systems", p, flag_units=["psi"], exclude_fields=["surface_area"])
    assert [f.evidence[0].quote for f in findings] == ["TEST TO 200 psi"]


def test_units_check_skips_non_metric_and_unknown_units():
    assert (
        run("no_mixed_unit_systems", page(title_block_fields=fields(units="inch")))[1].status
        == "not_applicable"
    )
    assert (
        run("no_mixed_unit_systems", page(title_block_fields=fields(units=None)))[1].status == "not_checked"
    )


# --- title block --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "params", "status"),
    [
        ("M.S.", {"field": "material"}, "pass"),
        (None, {"field": "material"}, "fail"),
        ("---", {"field": "material"}, "fail"),
        ("#", {"field": "material", "placeholder_ok": ["#"]}, "pass"),
        ("IS 2102", {"field": "material", "must_contain": ["IS 2102"]}, "pass"),
        ("ISO 2768-m", {"field": "material", "must_contain": ["IS 2102"]}, "fail"),
    ],
)
def test_title_block_field(value, params, status):
    assert (
        run("title_block_field", page(title_block_fields=fields(material=value)), **params)[1].status
        == status
    )


def test_title_block_checks_need_a_read_title_block():
    p = page(title_block_layout="variant", title_block_fields={})
    assert run("title_block_field", p, field="material")[1].status == "not_checked"


def test_title_block_pattern():
    assert run("title_block_pattern", page(), field="number")[1].status == "pass"
    assert (
        run("title_block_pattern", page(title_block_fields=fields(number=None)), field="number")[1].status
        == "fail"
    )
    assert (
        run("title_block_pattern", page(), field="number", pattern=r"P\d{2}[A-Z]{3}\d{6}")[1].status == "fail"
    )


def test_dates_in_order_reads_day_month_year():
    ok = page(title_block_fields=fields(drawn_date="01/10/2025", checked_date="02/10/2025"))
    assert run("dates_in_order", ok)[1].status == "pass"
    # 25/09 is before 01/10 day-first; month-first it would be an invalid date and could not be compared.
    bad = page(title_block_fields=fields(drawn_date="01/10/2025", checked_date="25/09/2025"))
    findings, status = run("dates_in_order", bad)
    assert status.status == "fail" and [e.ref for e in findings[0].evidence] == ["checked_date", "drawn_date"]
    assert run("dates_in_order", page())[1].status == "not_checked"  # nothing to compare


def test_scale_against_view_labels():
    labels = [
        TextItem(text="SCALE 1:1", bbox=(300, 650, 340, 660)),
        TextItem(text="SCALE 2:1", bbox=(500, 650, 540, 660)),
    ]
    assert run("scale_consistent", page(view_labels=labels))[1].status == "pass"  # a 2:1 detail is fine
    findings, status = run(
        "scale_consistent", page(view_labels=labels[:1], title_block_fields=fields(scale="2 : 1"))
    )
    assert status.status == "fail" and findings[0].evidence[1].quote == "SCALE 1:1"


def test_scale_against_drawn_dimensions_without_labels():
    at_2_to_1 = [drawn(1, "40", 80, y=100), drawn(2, "60", 120, y=150), drawn(3, "15", 30, "vertical", y=200)]
    findings, status = run("scale_consistent", scaled_page(*at_2_to_1))
    assert status.status == "fail" and "2 : 1" in findings[0].comment
    assert (
        run("scale_consistent", scaled_page(*at_2_to_1, title_block_fields=fields(scale="2 : 1")))[1].status
        == "pass"
    )
    assert run("scale_consistent", page(title_block_fields=fields(scale="1 :")))[1].status == "not_checked"


def test_revision_matches_table():
    numbers = [TextLine(text="1", bbox=(640, 640, 645, 648)), TextLine(text="2", bbox=(640, 628, 645, 636))]
    assert run("revision_matches_table", page())[1].status == "pass"  # 00 and no rows
    findings, status = run("revision_matches_table", page(title_block_fields=fields(revision="01")))
    assert status.status == "fail" and {e.kind for e in findings[0].evidence} == {"title_block", "region"}
    assert (
        run(
            "revision_matches_table", page(revision_numbers=numbers, title_block_fields=fields(revision="02"))
        )[1].status
        == "pass"
    )
    assert (
        run("revision_matches_table", page(title_block_fields=fields(revision="A")))[1].status
        == "not_checked"
    )


def test_fields_blank_at_submission():
    params = {"fields": ["checked_date", "approved_date"]}
    assert run("fields_blank_at_submission", page(), **params)[1].status == "pass"
    signed = page(title_block_fields=fields(checked_date="01/10/2025", approved_date="01/10/2025"))
    findings, status = run("fields_blank_at_submission", signed, **params)
    assert status.status == "fail" and len(findings) == 1 and len(findings[0].evidence) == 2


def test_checks_are_pure_functions_of_their_input():
    p = chain(match=False)
    assert run("chain_sum", p)[0] == run("chain_sum", p)[0]


# --- tolerance ----------------------------------------------------------------------------------------------

GENERAL = [
    GeneralToleranceRow(
        process="machining",
        kind="linear",
        over=o,
        up_to=u,
        tolerance=f"±{v:g}",
        value_mm=v,
        bbox=(0, 0, 1, 1),
    )
    for o, u, v in [(0.5, 3, 0.1), (3, 6, 0.1), (6, 30, 0.2), (30, 120, 0.3), (120, 315, 0.5)]
]


def tol_page(*texts: str, limits: dict[str, tuple[str, str]] | None = None) -> PageExtraction:
    dims = [
        TextItem(
            id=f"D{i}", text=t, bbox=(100, 100 + 20 * i, 130, 110 + 20 * i), limits=(limits or {}).get(t)
        )
        for i, t in enumerate(texts, 1)
    ]
    return page(dimensions=dims, general_tolerances=GENERAL)


@pytest.mark.parametrize(
    ("text", "nominal", "fit", "upper", "lower"),
    [
        ("28.5±0.1", 28.5, None, 0.1, -0.1),
        ("30 ±0.1", 30, None, 0.1, -0.1),
        ("⌀ 16 H7 (+0.018/0)", 16, "H7", 0.018, 0),
        ("R 8", 8, None, None, None),
        ("⌀8   H7", 8, "H7", None, None),
    ],
)
def test_tolerance_parsing(text, nominal, fit, upper, lower):
    t = parse(dim(1, text))
    assert t is not None and (t.nominal, t.fit, t.upper, t.lower) == (nominal, fit, upper, lower)


@pytest.mark.parametrize("text", ["3 x 45°", "(35)", "2-⌀15", "⌀8 H7 THRU", "0.00 (-35.00/-35.00)"])
def test_not_a_toleranced_size(text):
    assert parse(dim(1, text)) is None


def test_limits_come_from_their_printed_order_not_the_text():
    t = parse(TextItem(id="D1", text="42 (-0.2/0)", bbox=(0, 0, 1, 1), limits=("0", "-0.2")))
    assert t is not None and (t.upper, t.lower) == (0, -0.2)


def test_general_tolerance_lookup_by_size():
    p = tol_page()
    assert general_for(p, 2.5).tolerance == "±0.1"  # type: ignore[union-attr]
    assert general_for(p, 30).tolerance == "±0.2"  # type: ignore[union-attr]  # 6 < 30 <= 30
    assert general_for(p, 30.5).tolerance == "±0.3"  # type: ignore[union-attr]
    assert general_for(p, 0.2) is None


def test_tolerance_limits_valid():
    bad = tol_page("11 (-0.2/-0.1)", limits={"11 (-0.2/-0.1)": ("-0.2", "-0.1")})
    findings, status = run("tolerance_limits_valid", bad)
    assert status.status == "fail" and findings[0].evidence[0].ref == "D1"
    good = tol_page("42 (-0.2/0)", limits={"42 (-0.2/0)": ("0", "-0.2")})
    assert run("tolerance_limits_valid", good)[1].status == "pass"
    assert run("tolerance_limits_valid", tol_page("40±0.1"))[1].status == "not_applicable"


def test_decimals_vs_tolerance():
    findings, status = run(
        "decimals_vs_tolerance", tol_page("28.500±0.1", "28.5±0.1", "20±0.02", "34.97", "2.5")
    )
    assert status.status == "fail" and [f.evidence[0].quote for f in findings] == ["28.500±0.1", "34.97"]
    assert run("decimals_vs_tolerance", tol_page("⌀8   H7"))[1].status == "not_checked"  # a fit says nothing


def test_tolerance_tighter_than_general_is_a_warning():
    p = tol_page("70±0.002", "70±0.1", "20±0.02", "⌀ 16 H7 (+0.018/0)")
    findings, status = run("tolerance_tighter_than_general", p, ratio=20)
    assert status.status == "warning" and [f.evidence[0].quote for f in findings] == ["70±0.002"]
    assert run("tolerance_tighter_than_general", p)[1].status == "not_checked"  # no ratio agreed


# --- surface treatment --------------------------------------------------------------------------------------


def notes_page(heat: str | None, *notes: str) -> PageExtraction:
    items = [TextItem(text=n, bbox=(100, 600 + 10 * i, 300, 608 + 10 * i)) for i, n in enumerate(notes)]
    return page(notes=items, title_block_fields=fields(heat_treatment=heat))


def test_referenced_note_exists():
    ok = notes_page("REF NOTE", "HEAT TREATMENT  :-", "1) TO BE TOUGHENED UPTO 24-32 HRC.")
    assert run("referenced_note_exists", ok, field="heat_treatment")[1].status == "pass"
    gone = notes_page("REF NOTE", "HEAT TREATMENT  :-")  # the heading alone specifies nothing
    findings, status = run("referenced_note_exists", gone, field="heat_treatment")
    assert status.status == "fail" and findings[0].evidence[0].ref == "heat_treatment"
    assert (
        run("referenced_note_exists", notes_page("---"), field="heat_treatment")[1].status == "not_applicable"
    )


HARDENING = {
    "needs_prior_hardening": ["tempering", "sub-zero treatment"],
    "hardening_terms": ["hardening", "hardened and tempered", "toughening", "carburizing"],
}


@pytest.mark.parametrize(
    ("note", "status"),
    [
        ("1) TO BE TEMPERED UPTO 24-32 HRC.", "fail"),
        ("1) TO BE TEMPERING UPTO 52~55 HRC.", "fail"),
        ("SUB ZERO TREATMENT AFTER MACHINING", "fail"),
        ("HARDENED AND TEMPERED TO 40-45 HRC", "pass"),
        ("CARBURISED AND TEMPERED", "pass"),  # British spelling of a hardening process
        ("1) TO BE TOUGHENED UPTO 28-32 HRC.", "not_applicable"),
    ],
)
def test_hardened_only_treatments_have_hardening(note, status):
    assert (
        run("hardened_only_treatments_have_hardening", notes_page("REF NOTE", note), **HARDENING)[1].status
        == status
    )


def test_decimals_can_ignore_cad_trailing_zeros_under_the_general_tolerance():
    p = tol_page("18.00", "34.97", "28.500±0.1")
    findings, _ = run("decimals_vs_tolerance", p, ignore_trailing_zeros_under_general=True)
    assert [f.evidence[0].quote for f in findings] == [
        "34.97",
        "28.500±0.1",
    ]  # an explicit ± is taken as printed
    findings, _ = run("decimals_vs_tolerance", p)
    assert [f.evidence[0].quote for f in findings] == ["18.00", "34.97", "28.500±0.1"]


# --- lookup checks and their reference tables ---------------------------------------------------------------

REFERENCE = load_reference()


def lookup_run(check: str, p: PageExtraction, **params):
    c = ctx(p)
    c = ReviewContext(**{**c.__dict__, "reference": REFERENCE})
    return run_rule(c, rule(check, check_type="lookup", **params), registered()[check])


@pytest.mark.parametrize(
    ("printed", "cls", "family"),
    [
        ("M.S.", "mild_steel", "ferrous"),
        ("M.S 2", "mild_steel", "ferrous"),  # a stray zone digit in the cell
        ("C-45", "carbon_steel", "ferrous"),
        ("EN-24", "alloy_steel", "ferrous"),
        ("20MNCR5", "alloy_steel", "ferrous"),
        ("Aluminum, HE30/6082", "aluminium", "non_ferrous"),
        ("PHOSPHOR BRONZE", "copper_alloy", "non_ferrous"),
        ("Polyurethene", "plastic", "non_metallic"),  # as misspelt on the drawings
        ("Delrin", "plastic", "non_metallic"),
        ("#", None, None),
    ],
)
def test_materials_table(printed, cls, family):
    materials = REFERENCE["materials"]
    assert materials.classify(printed) == cls and materials.family(cls) == family


@pytest.mark.parametrize(
    ("printed", "process"),
    [
        ("I.Z.B.P. (TRIVALENT)", "izbp"),
        ("IZBP", "izbp"),
        ("HARD ANODIZING", "hard_anodizing"),
        ("SELF-ANODIZING", "silver_anodizing"),
        ("ELECTOLESS NICKEL PLATING", "enp"),  # as misspelt on a drawing
        ("E.N.P.", "enp"),
        ("QPQ", "qpq"),
        ("PAINTING", None),  # not a DES-12 plating process
    ],
)
def test_plating_processes_table(printed, process):
    found = REFERENCE["plating_processes"].identify(printed)
    assert (found.id if found else None) == process


def test_reference_tables_change_the_rulebook_version(tmp_path: Path):
    rules = tmp_path / "rules"
    rules.mkdir()
    before = load_rulebook(rules).version
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "extra.yaml").write_text("a: 1\n", encoding="utf-8")
    assert load_rulebook(rules).version != before


@pytest.mark.parametrize(
    ("treatment", "material", "status"),
    [
        ("HARD ANODIZING", "M.S.", "fail"),
        ("I.Z.B.P. (TRIVALENT)", "Polyurethene", "fail"),
        ("I.Z.B.P. (TRIVALENT)", "C-45", "pass"),
        ("HARD ANODIZING", "Aluminum, 6061-T6", "pass"),
        ("ENP", "Delrin", "pass"),  # DES-12: "Plastic (ABS) and Other"
        ("PAINTING", "M.S.", "not_applicable"),  # not a DES-12 process
        ("IZBP", "#", "not_checked"),  # material not stated
        ("IZBP", "Steel", "not_checked"),  # steel, grade not stated
    ],
)
def test_treatment_material_compat(treatment, material, status):
    p = page(title_block_fields=fields(surface_treatment=treatment, material=material))
    findings, s = lookup_run("treatment_material_compat", p, table="plating_processes")
    assert s.status == status
    if status == "fail":
        assert {e.ref for e in findings[0].evidence} == {"surface_treatment", "material"}


def test_treatment_check_needs_its_table():
    p = page(title_block_fields=fields(surface_treatment="IZBP"))
    no_tables = dataclasses.replace(ctx(p), reference={})
    r = rule("treatment_material_compat", table="plating_processes")
    assert run_rule(no_tables, r, registered()["treatment_material_compat"])[1].status == "not_checked"


@pytest.mark.parametrize(
    ("heat", "material", "notes", "status"),
    [
        ("HARDENED 40-45 HRC", "Polyurethene", [], "fail"),
        ("HARDENED 40-45 HRC", "C-45", [], "pass"),
        ("REF NOTE", "NYLON", ["1) TO BE HARDENED UPTO 40 HRC."], "fail"),  # the note it refers to
        (
            "---",
            "Polyurethene",
            ["SHORE HARDNESS- 80"],
            "not_applicable",
        ),  # shore hardness is not a treatment
        ("HARDENED 40-45 HRC", "#", [], "not_checked"),
    ],
)
def test_heat_treatment_only_on_metals(heat, material, notes, status):
    p = notes_page(heat, *notes)
    p = p.model_copy(update={"title_block_fields": fields(heat_treatment=heat, material=material)})
    params = {"table": "plastics_families", "non_metals": ["PVC", "nylon"]}
    assert lookup_run("heat_treatment_only_on_metals", p, **params)[1].status == status


def test_ref_drawing_or_bom_is_not_a_note_reference():
    for value in ("REF. DRG", "REF BOM"):
        assert (
            run("referenced_note_exists", notes_page(value), field="heat_treatment")[1].status
            == "not_applicable"
        )


def test_any_run_of_dashes_is_a_placeholder():
    p = notes_page("----")
    p = p.model_copy(update={"title_block_fields": fields(heat_treatment="----", material="DELRIN")})
    params = {"table": "plastics_families", "non_metals": []}
    assert lookup_run("heat_treatment_only_on_metals", p, **params)[1].status == "not_applicable"
    assert (
        run("title_block_field", page(title_block_fields=fields(material="----")), field="material")[1].status
        == "fail"
    )


# --- GD&T and datums (stage 1 symbols) ----------------------------------------------------------------------


def sym(i: int, kind: Literal["gdt", "datum", "surface_finish"], text: str, **kw) -> SymbolItem:
    return SymbolItem(
        id=f"S{i}",
        type=kind,
        text=text,
        bbox=(100 + 20 * i, 100, 115 + 20 * i, 110),
        provenance="pdf_text" if kind == "gdt" else "vector",
        **kw,
    )


def frame(i: int, characteristic: str, datums=(), tolerance="0.05") -> SymbolItem:
    return sym(
        i,
        "gdt",
        f"{characteristic} {tolerance}",
        characteristic=characteristic,
        tolerance=tolerance,
        datums=list(datums),
    )


def flag(i: int, letter: str) -> SymbolItem:
    return sym(i, "datum", f"datum {letter}", datums=[letter])


def sym_page(*symbols, n: int = 1, notes=()) -> PageExtraction:
    lines = [TextLine(text=t, bbox=(100, 700, 300, 710)) for t in notes]
    return page(page_number=n, symbols=list(symbols), body_text=lines)


def test_datum_referenced_defined():
    findings, status = run(
        "datum_referenced_defined",
        sym_page(frame(1, "parallelism", ["A"]), frame(2, "position", ["A-B"]), flag(3, "A")),
    )
    assert (
        status.status == "fail" and "datum B" in findings[0].comment and findings[0].evidence[0].ref == "S2"
    )
    assert run("datum_referenced_defined", sym_page(frame(1, "flatness")))[1].status == "not_applicable"


def test_fcf_has_datum():
    params = {"characteristics": ["position", "perpendicularity", "symmetry"]}
    findings, status = run(
        "fcf_has_datum",
        sym_page(frame(1, "symmetry"), frame(2, "position", ["A"]), frame(3, "flatness")),
        **params,
    )
    assert status.status == "fail" and [f.evidence[0].ref for f in findings] == ["S1"]


def test_datum_letters_valid():
    assert (
        run("datum_letters_valid", sym_page(flag(1, "I"), flag(2, "A")), illegal=["I", "O", "Q"])[1].status
        == "fail"
    )
    assert run("datum_letters_valid", sym_page(flag(1, "A")), illegal=["I"])[1].status == "pass"


def test_datum_unused_counts_frames_and_notes():
    p = sym_page(
        frame(1, "parallelism", ["A"]),
        flag(2, "A"),
        flag(3, "B"),
        flag(4, "C"),
        notes=["CO PLANERITY OF SURFACE C SHOULD BE WITHIN 0.03"],
    )
    findings, status = run("datum_unused", p)
    assert status.status == "fail" and [f.evidence[0].ref for f in findings] == ["S3"]  # only B is unused


def test_datum_on_same_sheet():
    pages = (sym_page(flag(1, "A"), n=1), sym_page(frame(1, "parallelism", ["A"]), n=2))
    findings, status = run("datum_on_same_sheet", *pages)
    assert status.status == "fail" and findings[0].evidence[0].page == 2
    assert run("datum_on_same_sheet", sym_page(flag(1, "A")))[1].status == "not_applicable"


def test_fcf_grammar():
    p = sym_page(
        frame(1, "flatness", ["A"]), frame(2, "position", ["A"], tolerance=""), frame(3, "parallelism", ["A"])
    )
    findings, status = run("fcf_grammar", p)
    assert status.status == "fail" and [f.evidence[0].ref for f in findings] == ["S1", "S2"]


# --- notes, drawing form, sheets, material ------------------------------------------------------------------


def body_page(*lines: str, **kw) -> PageExtraction:
    text = [TextLine(text=t, bbox=(100, 600 + 10 * i, 400, 608 + 10 * i)) for i, t in enumerate(lines)]
    return page(body_text=text, **kw)


def test_no_model_deferral():
    params = {"phrases": ["SEE 3D", "AS PER MODEL"]}
    assert run("no_model_deferral", body_page("PROFILE AS PER MODEL"), **params)[1].status == "fail"
    assert run("no_model_deferral", body_page("DEBURR ALL SHARP EDGES"), **params)[1].status == "pass"


def test_placeholders_count_only_in_a_field_not_as_an_area_marker():
    params = {"patterns": ["XXX", "TBD"]}
    findings, status = run(
        "no_placeholder_text", body_page("H.T.PROCESS : XXXXX", "XXXXX", "COLOUR TBD"), **params
    )
    assert status.status == "fail" and [f.evidence[0].quote for f in findings] == [
        "H.T.PROCESS : XXXXX",
        "COLOUR TBD",
    ]


def test_leading_zero_but_not_hole_tags():
    findings, _ = run("leading_zero_decimal", page(dimensions=[dim(1, ".5"), dim(2, "0.5"), dim(3, "A.1")]))
    assert [f.evidence[0].quote for f in findings] == [".5"]
    diameter = page(dimensions=[dim(1, "Ø.5"), dim(2, "⌀.25"), dim(3, "Ø0.5")])
    assert [f.evidence[0].quote for f in run("leading_zero_decimal", diameter)[0]] == ["Ø.5", "⌀.25"]


def test_comma_thousands():
    findings, _ = run("digit_grouping", page(dimensions=[dim(1, "1,200"), dim(2, "1200"), dim(3, "12,5")]))
    assert [f.evidence[0].quote for f in findings] == ["1,200"]


HARD = {"HRC": [20, 67], "HRB": [60, 99], "HB_max_steel_ball": 400, "HB_max_carbide_ball": 700}


def test_hardness_in_scale_range():
    findings, status = run(
        "hardness_value_in_scale_range", body_page("TO BE TOUGHENED UPTO 24-32 HRC", "HARDEN 15 HRC"), **HARD
    )
    assert status.status == "fail" and "15" in findings[0].comment
    assert run("hardness_value_in_scale_range", body_page("DEBURR"), **HARD)[1].status == "not_applicable"
    # a decimal comma is a decimal point: 58,5 HRC is in range, 5,8 HRC is not
    assert run("hardness_value_in_scale_range", body_page("HARDEN TO 58,5 HRC"), **HARD)[1].status == "pass"
    comma = run("hardness_value_in_scale_range", body_page("HARDEN TO 5,8 HRC"), **HARD)
    assert comma[1].status == "fail" and "5,8" in comma[0][0].comment
    # the scale name may come first: HRC 58-62
    assert run("hardness_value_in_scale_range", body_page("HARDNESS HRC 58-62"), **HARD)[1].status == "pass"
    after = run("hardness_value_in_scale_range", body_page("HARDNESS HRC 15-62"), **HARD)
    assert after[1].status == "fail" and "15 HRC" in after[0][0].comment
    assert run("hardness_value_in_scale_range", body_page("58-62 HRC"), **HARD)[1].status == "pass"


def test_hardness_spec_complete():
    ok = body_page("1) TO BE CASE HARDENED UPTO 56~60 HRC.", "2) CASE DEPTH 0.8~1.2mm.")
    assert run("hardness_spec_complete", ok)[1].status == "pass"
    no_depth = body_page("1) TO BE CASE HARDENED UPTO 56~60 HRC.")
    assert "case depth" in run("hardness_spec_complete", no_depth)[0][0].comment
    bought_out = body_page("LM GUIDE ROD OD 20 (HARDENED & GROUND)")  # names a part, gives no instruction
    assert run("hardness_spec_complete", bought_out)[1].status == "not_applicable"


def test_dates_valid_accepts_other_separators():
    assert (
        run("dates_valid", page(title_block_fields=fields(drawn_date="06-05-2024")), fields=["drawn_date"])[
            1
        ].status
        == "pass"
    )
    assert (
        run("dates_valid", page(title_block_fields=fields(drawn_date=None)), fields=["drawn_date"])[1].status
        == "fail"
    )
    assert (
        run("dates_valid", page(title_block_fields=fields(drawn_date="SOON")), fields=["drawn_date"])[
            1
        ].status
        == "fail"
    )


def test_sheet_numbering():
    one = page(title_block_fields=fields(sheet="1 OF 2"))
    two = page(page_number=2, title_block_fields=fields(sheet="3 OF 2"))
    findings, status = run("sheet_numbering", one, two)
    assert status.status == "fail" and findings[0].evidence[0].page == 2


def test_sheet_size_matches_page():
    assert (
        run("sheet_size_matches_page", page(title_block_fields=fields(sheet_size="A3")))[1].status == "pass"
    )
    findings, _ = run("sheet_size_matches_page", page(title_block_fields=fields(sheet_size="A2")))
    assert "A3" in findings[0].comment


def test_template_text_over_two_lines():
    params = {"text": "ALL RIGHTS OF REPRODUCTION & DISTRIBUTION ARE RESERVED"}
    split = body_page("C ALL RIGHTS OF REPRODUCTION &", "DISTRIBUTION ARE RESERVED")
    assert run("template_text_present", split, **params)[1].status == "pass"
    assert run("template_text_present", body_page("DEBURR"), **params)[1].status == "fail"


def test_revision_sequence():
    nums = [TextLine(text=n, bbox=(640, 630 + 10 * i, 645, 638 + 10 * i)) for i, n in enumerate(["1", "3"])]
    assert run("revision_sequence", page(revision_numbers=nums))[1].status == "fail"


def test_sheets_agree():
    a = page(title_block_fields=fields(revision="01", sheet_size="A3"))
    b = page(page_number=2, title_block_fields=fields(revision="00", sheet_size="A3"))
    assert run("sheets_same_revision", a, b, min_sheets=2)[1].status == "fail"
    assert run("sheets_same_size", a, b, min_sheets=2)[1].status == "pass"
    assert run("sheets_same_revision", a, min_sheets=2)[1].status == "not_applicable"


def test_reference_dims_untoleranced():
    findings, _ = run("reference_dim_untoleranced", page(dimensions=[dim(1, "(35)"), dim(2, "(35±0.1)")]))
    assert [f.evidence[0].quote for f in findings] == ["(35±0.1)"]


def test_izbp_trivalent():
    assert (
        run("izbp_trivalent", page(title_block_fields=fields(surface_treatment="IZBP")))[1].status == "fail"
    )
    ok = page(title_block_fields=fields(surface_treatment="I.Z.B.P. (TRIVALENT)"))
    assert run("izbp_trivalent", ok)[1].status == "pass"


def test_material_written_consistently():
    p = body_page("# MATERIAL: EN8", title_block_fields=fields(material="EN-9"))
    findings, status = run("material_written_consistently", p)
    assert status.status == "fail" and {e.kind for e in findings[0].evidence} == {"title_block", "text"}
    same = body_page("# MATERIAL: M.S", title_block_fields=fields(material="M.S."))
    assert run("material_written_consistently", same)[1].status == "pass"


# --- fits, general tolerances, threads (reference tables) -------------------------------------------------


def test_fit_codes_valid_but_not_chamfers():
    p = page(dimensions=[dim(1, "⌀20 H7"), dim(2, "12 g6 -0.006"), dim(3, "10 H71"), dim(4, "2X45°")])
    findings, status = run("fit_code_valid", p, table="is919_fits")
    assert status.status == "fail" and [f.evidence[0].ref for f in findings] == ["D3"]


def test_fit_deviations_against_is919():
    ok = page(dimensions=[dim(1, "⌀ 20 H7 +0.021"), dim(2, "6 f6 -0.010", y=300), dim(3, "-0.018", y=300)])
    assert run("fit_deviations_match_table", ok, table="is919_fits")[1].status == "pass"
    wrong = page(dimensions=[dim(1, "⌀ 20 H7 +0.025")])
    findings, _ = run("fit_deviations_match_table", wrong, table="is919_fits")
    assert "+0.021/0" in findings[0].comment
    stacked_wrong = page(dimensions=[dim(1, "6 f6 -0.010"), dim(2, "-0.020")])  # the stacked lower is wrong
    assert run("fit_deviations_match_table", stacked_wrong, table="is919_fits")[1].status == "fail"
    untabulated = page(dimensions=[dim(1, "18 N9 -0.043")])  # a keyway zone the book does not list
    assert run("fit_deviations_match_table", untabulated, table="is919_fits")[1].status == "not_applicable"


def gt_rows(
    process: str, kind: str, values: list[tuple[float, float | None, str]]
) -> list[GeneralToleranceRow]:
    return [
        GeneralToleranceRow(
            process=process, kind=kind, over=o, up_to=u, tolerance=t,  # type: ignore[arg-type]
            value_mm=float(t.strip("±")) if kind == "linear" else None, bbox=(1100, 100, 1120, 106),
        )
        for o, u, t in values
    ]  # fmt: skip


MEDIUM = [(0.5, 3, "±0.1"), (3, 6, "±0.1"), (6, 30, "±0.2"), (30, 120, "±0.3"), (120, 315, "±0.5"),
          (315, 1000, "±0.8"), (1000, 2000, "±1.2"), (2000, None, "±2")]  # fmt: skip


def test_general_tolerance_table_is_one_is2102_class():
    angular = gt_rows(
        "machining",
        "angular",
        [(0, 10, "±1°"), (10, 50, "±0°30'"), (50, 120, "±0°20'"), (120, 400, "±0°10'")],
    )
    good = page(general_tolerances=[*gt_rows("machining", "linear", MEDIUM), *angular])
    assert run("general_tolerance_table_matches", good, table="is2102_general_tolerances")[1].status == "pass"
    typo = [*MEDIUM[:2], (6, 30, "±0.3"), *MEDIUM[3:]]
    typo_page = page(general_tolerances=gt_rows("machining", "linear", typo))
    findings, _ = run("general_tolerance_table_matches", typo_page, table="is2102_general_tolerances")
    assert "closest is medium" in findings[0].comment and "6-30" in findings[0].comment


def body(*lines: str) -> PageExtraction:
    return page(
        body_text=[TextLine(text=t, bbox=(100, 600 + 10 * i, 400, 608 + 10 * i)) for i, t in enumerate(lines)]
    )


def test_standard_thread_sizes_and_pitches():
    ok = body("4 HOLES M8 x 16 DEEP", "M24 x 1.5 x 38 DEEP", "$THREAD M65X2P FOR DEPTH 17MM", "M35 X 1.5 P")
    assert run("standard_thread_size", ok, table="iso_metric_threads")[1].status == "pass"
    findings, _ = run("standard_thread_size", body("M13 x 20 DEEP", "M8 x 1.5"), table="iso_metric_threads")
    assert ["M13" in findings[0].comment, "no 1.5 pitch" in findings[1].comment] == [True, True]


def test_thread_tolerance_classes():
    params = {
        "internal_classes": ["5H", "6H", "7H"],
        "external_classes": ["4h", "6g", "8g"],
        "table": "iso_metric_threads",
    }
    assert run("thread_tolerance_class_valid", body("M10x1.25-6H"), **params)[1].status == "pass"
    findings, _ = run("thread_tolerance_class_valid", body("M2-7H", "M8-6e"), **params)
    assert len(findings) == 2 and "from M3" in findings[0].comment


# --- P1: numbered notes -------------------------------------------------------------------------------------


def column_page(*columns: tuple[float, list[str]], extra: list[str] | None = None) -> PageExtraction:
    """Body lines laid out in columns: (left edge, texts top to bottom). `extra` lines go in a far column."""
    lines = [
        TextLine(text=t, bbox=(x, 500 + 10 * i, x + 200, 508 + 10 * i))
        for x, texts in columns
        for i, t in enumerate(texts)
    ]
    lines += [TextLine(text=t, bbox=(20, 100 + 10 * i, 120, 108 + 10 * i)) for i, t in enumerate(extra or [])]
    return page(body_text=lines)


def test_numbered_notes_in_order_pass_and_template_notes_are_skipped():
    ok = column_page(
        (600, ["1) TO BE HARDENED UPTO 50 HRC.", "2) RETAPPING AFTER SURFACE TREATMENT"]),
        extra=["3.IF IN DOUBT ,", "2.DO NOT SCALE", "1.ALL DIMENSIONS ARE", "1.2 H13"],
    )
    assert run("general_notes_consecutive", ok)[1].status == "pass"
    assert run("general_notes_consecutive", body_page("DEBURR ALL EDGES"))[1].status == "not_applicable"


def test_numbered_notes_with_a_gap_a_repeat_or_a_wrong_start():
    gap, _ = run("general_notes_consecutive", column_page((600, ["1) PROFILE CUTTING", "3) CASE DEPTH 0.8"])))
    assert "goes from 1 to 3" in gap[0].comment and gap[0].evidence[0].quote == "3) CASE DEPTH 0.8"
    again, _ = run(
        "general_notes_consecutive", column_page((600, ["1) CASE CARBURISING", "2) INDUCTION", "2) DEPTH"]))
    )
    assert "repeats 2" in again[0].comment
    late, _ = run("general_notes_consecutive", column_page((600, ["2) RETAPPING", "3) DEBURR"])))
    assert "starts at 2, not 1" in late[0].comment


def test_a_second_list_in_another_language_or_column_is_judged_alone():
    english_and_french = column_page(
        (600, ["1) ALL H7 HOLES", "2) ALL TAPPED HOLES", "1) TOUT TROU H7", "2) TOUT TROU TARAUDE"]),
        (900, ["1) TO BE TOUGHENED", "2) RETAPPING"]),
    )
    assert run("general_notes_consecutive", english_and_french)[1].status == "pass"
    one_bad = column_page((600, ["1) CHAMFER", "2) DEBURR"]), (900, ["1) ANODISE", "3) PACK"]))
    findings, _ = run("general_notes_consecutive", one_bad)
    assert [f.evidence[0].quote for f in findings] == ["3) PACK"]


def test_note_references_must_point_at_a_note_that_exists():
    notes = (600, ["1) TO BE HARDENED", "2) RETAPPING AFTER TREATMENT"])
    ok = column_page(notes, extra=["SEE NOTE 2"])
    assert run("note_references_resolve", ok)[1].status == "pass"
    findings, status = run("note_references_resolve", column_page(notes, extra=["REFER TO NOTE NO. 5"]))
    assert status.status == "fail" and "note 5" in findings[0].comment
    assert run("note_references_resolve", column_page(notes, extra=["H.T.PROCESS : REFER NOTE"]))[
        1
    ].status == ("not_applicable")
    template_note = column_page(extra=["1.ALL DIMENSIONS ARE", "SEE NOTE 1"])
    assert run("note_references_resolve", template_note)[1].status == "pass"


def test_notes_marked_with_hash_or_dollar_or_on_the_heading_line_are_numbered_notes():
    marked = column_page(
        (600, ["1) # USE STD. DIA. 30 g6 BRIGHT BAR", "2) STRAIGHTNESS 0.2 MAX", "3) $ HARD CHROME PLATING"])
    )
    assert run("general_notes_consecutive", marked)[1].status == "pass"
    heading = column_page((600, ["NOTE:- 1)TO BE TOUGHENED TO 28-30 HRc.", "2)REMOVE ALL SHARP EDGES"]))
    assert run("general_notes_consecutive", heading)[1].status == "pass"
    accented = column_page((600, ["1) TO BE HARDENED", "1) À ENDURCIR", "2) PROFONDEUR"]))
    assert run("general_notes_consecutive", accented)[1].status == "pass"


def test_a_repeated_one_after_a_single_note_is_a_repeat_not_a_copy():
    # 1) / 1) / 2): the second 1 does not start a new list unless a full list or a French line precedes it
    findings, status = run(
        "general_notes_consecutive", column_page((600, ["1) CHAMFER", "1) DEBURR", "2) ANODISE"]))
    )
    assert status.status == "fail" and "repeats 1" in findings[0].comment
    # a full English list followed by its copy is still two lists
    copy = column_page((600, ["1) CHAMFER", "2) DEBURR", "1) CHANFREIN", "2) EBAVURER"]))
    assert run("general_notes_consecutive", copy)[1].status == "pass"


# --- P1: paint colour -------------------------------------------------------------------------------------


def finish_page(finish: str, *notes: str) -> PageExtraction:
    return page(
        title_block_fields=fields(surface_treatment=finish),
        notes=[TextItem(text=t, bbox=(100, 600 + 10 * i, 300, 608 + 10 * i)) for i, t in enumerate(notes)],
    )


def test_paint_needs_a_colour_code_not_a_name():
    findings, status = run("paint_colour_code", finish_page("PAINTING", "COLOUR - WHITE"))
    assert status.status == "fail" and findings[0].evidence[0].ref == "surface_treatment"
    assert run("paint_colour_code", finish_page("POWDER COATING"))[1].status == "fail"
    assert run("paint_colour_code", finish_page("POWDER COATING", "COLOUR RAL 7035"))[1].status == "pass"
    assert run("paint_colour_code", finish_page("PAINTING RAL9005"))[1].status == "pass"
    assert run("paint_colour_code", finish_page("I.Z.B.P. (TRIVALENT)"))[1].status == "not_applicable"


def test_insert_note_must_say_which_insert():
    findings, status = run("insert_spec", body("1)USE HELICOIL INSERT AT ALL TAPPING HOLES"))
    assert status.status == "fail" and "no insert part number" in findings[0].comment
    ok = ("USE HELICOIL INSERT AT ALL TAPPING HOLES", "INSERT UP TO TOTAL LENGTH OF TAPPING")
    assert run("insert_spec", body(*ok))[1].status == "pass"  # one note on the sheet gives the length
    assert run("insert_spec", body("USE M8 THREADED INSERT AT ALL TAPPING HOLES"))[1].status == "pass"
    assert run("insert_spec", body("TO BE USED THREAD INSERTS MAKE Kerb Konus"))[1].status == "pass"
    assert run("insert_spec", body("DEBURR ALL EDGES"))[1].status == "not_applicable"
    history = page(
        body_text=[TextLine(text="THREAD INSERTS ADDED", bbox=(100, 600, 300, 608))],
        revision_rows=[TextLine(text="THREAD INSERTS ADDED", bbox=(100, 600, 300, 608))],
    )
    assert run("insert_spec", history)[1].status == "not_applicable"


def test_supersede_note_needs_the_old_number_and_revision():
    ok = body("SUPERSEDES DWG P23N1B075061 REV 02")
    assert run("supersede_note_complete", ok)[1].status == "pass"
    assert (
        run("supersede_note_complete", body("SUPERSEDES DRAWING NO. P23N1B075061 REV. B"))[1].status == "pass"
    )
    findings, status = run("supersede_note_complete", body("SUPERSEDES DWG P23N1B075061"))
    assert status.status == "fail" and "number and its revision" in findings[0].comment
    assert run("supersede_note_complete", body("SUPERSEDES OLD DRAWING"))[1].status == "fail"
    # a keyword is not a drawing number: the number must hold a digit
    for text in ("SUPERSEDES DRAWING REV 02", "SUPERSEDES DWG REV 02", "SUPERSEDES DRAWING NO. REV 02"):
        assert run("supersede_note_complete", body(text))[1].status == "fail", text
    assert run("supersede_note_complete", body("DEBURR ALL EDGES"))[1].status == "not_applicable"


# --- P1 batch 2: dimension text ----------------------------------------------------------------------------


def test_diameter_and_radius_symbols_not_words():
    bad = page(
        dimensions=[dim(1, "DIA 30"), dim(2, "30 DIA"), dim(3, "RADIUS 5"), dim(4, "⌀ 30"), dim(5, "R5")]
    )
    findings, status = run("diameter_radius_symbol_prefix", bad)
    assert status.status == "fail" and [f.evidence[0].quote for f in findings] == [
        "DIA 30",
        "30 DIA",
        "RADIUS 5",
    ]
    # the word in a note is a warning, not a failure: prose may say DIA, the symbol is the standard
    findings, status = run("diameter_radius_symbol_prefix", body_page("WIRE DIA- 4mm & MESH SIZE 1X1"))
    assert (
        status.status == "warning" and findings[0].result == "warning" and "The note" in findings[0].comment
    )
    # a dimension value and the same text as a body line are one finding, not two
    twice = page(
        dimensions=[dim(1, "DIA 30")], body_text=[TextLine(text="DIA 30", bbox=(100, 100, 150, 108))]
    )
    assert len(run("diameter_radius_symbol_prefix", twice)[0]) == 1
    # history and feature names are not callouts: a change note, a file path, a thread's major diameter
    for text in (
        "2-DIA20MM HOLE CHANGED TO DIA 30",
        "\\\\srv\\ExDM\\Front Shaft Dia.20.dft",
        "MAJOR DIA -0.05",
    ):
        assert run("diameter_radius_symbol_prefix", body_page(text))[1].status == "pass", text


def test_torque_and_pressure_carry_their_unit():
    findings, status = run(
        "non_length_value_has_unit", body_page("TORQUE 25", "PRESSURE : 6 bar", "TORQUE TO 40 N.m")
    )
    assert status.status == "fail" and [f.evidence[0].quote for f in findings] == ["TORQUE 25"]
    assert (
        run("non_length_value_has_unit", body_page("STANDARD FASTENER TORQUE AS PER STD-DES-01-00"))[1].status
        == "pass"
    )


def test_angles_use_one_format_and_never_radians():
    mixed = page(dimensions=[dim(1, "30°"), dim(2, "45°30'")])
    findings, status = run("angle_format_consistent", mixed, preferred="decimal_degrees", allowed=[])
    assert status.status == "fail" and "45°30'" in findings[0].comment
    ok = page(dimensions=[dim(1, "30°"), dim(2, "1 x 45°"), dim(3, "THRU'")])
    assert run("angle_format_consistent", ok, preferred="decimal_degrees", allowed=[])[1].status == "pass"
    rad = page(dimensions=[dim(1, "0.5 RAD")])
    assert run("angle_format_consistent", rad, preferred="decimal_degrees", allowed=[])[1].status == "fail"
    assert run("angle_format_consistent", page(dimensions=[dim(1, "30")]), preferred="x", allowed=[])[
        1
    ].status == ("not_applicable")


def test_pitch_notation_product_equals_total():
    params = {"forms": ["n×p=L"]}
    assert (
        run("pitch_notation_arithmetic", page(dimensions=[dim(1, "4 x 60 = 240")]), **params)[1].status
        == "pass"
    )
    assert (
        run("pitch_notation_arithmetic", page(dimensions=[dim(1, "7@75=525")]), **params)[1].status == "pass"
    )
    findings, status = run("pitch_notation_arithmetic", page(dimensions=[dim(1, "4X60=250")]), **params)
    assert status.status == "fail" and "is 240, not 250" in findings[0].comment


def test_pitch_notation_ignores_a_count_inside_a_decimal():
    params = {"forms": ["n×p=L"]}
    # "1.5 x 4 = 6" is a decimal times 4, not a count of 5: it must not fail
    assert run("pitch_notation_arithmetic", page(dimensions=[dim(1, "1.5 x 4 = 6")]), **params)[1].status != (
        "fail"
    )
    mixed = page(dimensions=[dim(1, "1.5 x 4 = 6"), dim(2, "4 x 60 = 240")])
    assert run("pitch_notation_arithmetic", mixed, **params)[1].status == "pass"


def test_counterbore_callout_needs_a_depth_even_on_a_second_line():
    params = {"required": ["depth"], "example": {"depth": 6}}
    ok = body_page("C'BORE Ø 18.00 mm - 10.80 mm DEEP")
    assert run("counterbore_callout_complete", ok, **params)[1].status == "pass"
    split = page(
        body_text=[
            TextLine(text="C'BORE Ø 18.00 mm", bbox=(1255, 462, 1453, 479)),
            TextLine(text="- 10.80 mm DEEP", bbox=(1255, 486, 1436, 502)),
        ]
    )
    assert run("counterbore_callout_complete", split, **params)[1].status == "pass"
    findings, status = run("counterbore_callout_complete", body_page("C'BORE Ø 18.00 mm"), **params)
    assert status.status == "fail" and "no depth" in findings[0].comment
    # a general note, or a hole callout whose counterbore is drawn elsewhere, is not judged
    for text in ("ALL HOLES,TAP & COUNTER BORE C.D,", "Ø9 THRU & C'BORE"):
        assert run("counterbore_callout_complete", body_page(text), **params)[1].status == "not_applicable"


def test_softening_only_treatment_with_a_hardened_hardness():
    params = {
        "softening_terms": ["annealing", "stress relieving"],
        "annealed_max_hb": {"IS 3749": [200, 260]},
        "hardening_terms": ["hardening", "toughening"],
    }
    findings, status = run("softening_treatment_vs_hardness", body_page("ANNEALED", "58-62 HRC"), **params)
    assert status.status == "fail" and "softens it" in findings[0].comment
    assert (
        run("softening_treatment_vs_hardness", body_page("ANNEALED", "200 HB"), **params)[1].status == "pass"
    )
    after_hardening = body_page("TO BE HARDENED", "STRESS RELIEVING TO BE DONE", "58-62 HRC")
    assert run("softening_treatment_vs_hardness", after_hardening, **params)[1].status == "pass"
    assert (
        run("softening_treatment_vs_hardness", body_page("58-62 HRC"), **params)[1].status == "not_applicable"
    )


# --- P1 batch 3: revision table, scales, soft metric ----------------------------------------------------


def rev_row(y: float, *texts: str, x: float = 1150.0) -> list[TextLine]:
    """One revision-table row: number, description, date, drawer, left to right at the template's columns."""
    xs = [x, x + 30, x + 340, x + 385]
    return [TextLine(text=t, bbox=(xs[i], y, xs[i] + 60, y + 8)) for i, t in enumerate(texts)]


def test_revision_rows_need_description_date_and_drawer():
    full = page(revision_rows=rev_row(990, "1", "DIMENSION ADDED", "08/05/2024", "9265"))
    assert run("revision_table_complete", full)[1].status == "pass"
    joined = page(revision_rows=rev_row(990, "1", "TOLERANCES CHANGED", "14.07.2025 7273"))
    assert run("revision_table_complete", joined)[1].status == "pass"  # date and drawer in one item
    no_drawer = page(revision_rows=rev_row(990, "1", "DIMENSION ADDED", "08/05/2024"))
    findings, status = run("revision_table_complete", no_drawer)
    assert status.status == "fail" and "missing the drawer" in findings[0].comment
    no_date = page(revision_rows=rev_row(990, "1", "DIMENSION ADDED"))
    assert "a date" in run("revision_table_complete", no_date)[0][0].comment
    number_only = page(revision_rows=rev_row(990, "1"))
    assert "a description and a date" in run("revision_table_complete", number_only)[0][0].comment
    two_rows = page(
        revision_rows=[
            *rev_row(990, "1", "DIMENSION ADDED", "08/05/2024", "9265"),
            *rev_row(976, "2", "HOLE ADDED", "09/01/25"),
        ]
    )
    findings, _ = run("revision_table_complete", two_rows)
    assert len(findings) == 1 and "HOLE ADDED" in findings[0].comment
    assert run("revision_table_complete", page())[1].status == "not_applicable"


def test_a_wrapped_description_stays_with_its_row():
    wrapped = page(
        revision_rows=[
            *rev_row(990, "1", "TOTAL LENGTH CHANGED AND", "15/05/24", "9265"),
            TextLine(text="HOLE SHIFTED.", bbox=(1180, 999, 1240, 1007)),
        ]
    )
    assert run("revision_table_complete", wrapped)[1].status == "pass"


SCALES = {
    "full_size": "1:1",
    "reduced": ["1:2", "1:5", "1:10", "1:20", "1:50"],
    "enlarged": ["2:1", "5:1", "10:1", "20:1", "50:1"],
}


def test_scales_must_be_preferred():
    ok = page(
        title_block_fields=fields(scale="1 : 2"),
        body_text=[TextLine(text="SCALE/ÉCHELLE 2:1", bbox=(100, 600, 200, 608))],
    )
    assert run("scale_is_preferred", ok, **SCALES)[1].status == "pass"
    bad = page(
        title_block_fields=fields(scale="4 : 1"),
        body_text=[TextLine(text="SCALE 1:2.5", bbox=(100, 600, 200, 608))],
    )
    findings, status = run("scale_is_preferred", bad, **SCALES)
    assert status.status == "fail" and [f.comment.split()[2] for f in findings] == ["4:1", "1:2.5"]
    assert run("scale_is_preferred", page(title_block_fields=fields(scale="1 :")), **SCALES)[1].status == (
        "not_applicable"
    )
    # a colon after the label ("SCALE: 1:3") is still a scale label
    for label in ("SCALE: 1:3", "SCALE : 1:3", "SCALE/ÉCHELLE: 1:3"):
        colon = page(
            title_block_fields=fields(scale="1 : 1"),
            body_text=[TextLine(text=label, bbox=(100, 600, 200, 608))],
        )
        findings, status = run("scale_is_preferred", colon, **SCALES)
        assert status.status == "fail" and findings[0].comment.split()[2] == "1:3", label


def test_detail_view_needs_a_scale_beside_its_name():
    def labels(*items: tuple[str, float, float]) -> list[TextItem]:
        return [TextItem(text=t, bbox=(x, y, x + 60, y + 11)) for t, x, y in items]

    ok = page(
        view_labels=labels(("DETAIL B", 1395, 378)),
        body_text=[TextLine(text="SCALE/ÉCHELLE 2:1", bbox=(1342, 393, 1532, 409))],
    )
    assert run("detail_view_scale", ok)[1].status == "pass"
    in_name = page(view_labels=labels(("DETAIL C (2:1)", 100, 100)))
    assert run("detail_view_scale", in_name)[1].status == "pass"
    findings, status = run(
        "detail_view_scale", page(view_labels=labels(("DETAIL A", 280, 118), ("SECTION A-A", 5, 5)))
    )
    assert status.status == "fail" and [f.evidence[0].quote for f in findings] == ["DETAIL A"]
    assert (
        run("detail_view_scale", page(view_labels=labels(("SECTION A-A", 5, 5))))[1].status
        == "not_applicable"
    )


def test_inch_fractions_in_mm_are_a_warning_not_a_failure():
    soft = page(
        dimensions=[dim(1, "19.05±0.1"), dim(2, "98.43"), dim(3, "25.40"), dim(4, "12.7"), dim(5, "20.00")]
    )
    findings, status = run("soft_metric_conversion_suspect", soft)
    assert status.status == "warning" and [f.result for f in findings] == ["warning", "warning"]
    assert "3/4 in" in findings[0].comment and "3 7/8 in" in findings[1].comment
    assert run("soft_metric_conversion_suspect", page(dimensions=[dim(1, "20.5")]))[1].status == "pass"


# --- P1 batch 4: what stage 1 supports ----------------------------------------------------------------------


def test_trapezoidal_lead_is_a_multiple_of_the_pitch():
    ok = body_page("Tr 40x14 (P7)", "Tr 12 x 3P", "Tr 20 x 4 (P4)")
    assert run("thread_lead_multiple_of_pitch", ok)[1].status == "pass"
    findings, status = run("thread_lead_multiple_of_pitch", body_page("Tr 40x15 (P7)"))
    assert status.status == "fail" and "lead 15 is not a whole multiple of pitch 7" in findings[0].comment
    assert run("thread_lead_multiple_of_pitch", body_page("M8 THRU"))[1].status == "not_applicable"
    # drawings are in capitals
    assert run("thread_lead_multiple_of_pitch", body_page("TR40X14(P7)"))[1].status == "pass"
    assert run("thread_lead_multiple_of_pitch", body_page("TR40X15(P7)"))[1].status == "fail"
    # a zero pitch must not divide by zero (that made the rule not_checked): it is a misprint, so it fails
    findings, status = run("thread_lead_multiple_of_pitch", body_page("Tr40x14(P0)"))
    assert status.status == "fail" and "a pitch of 0 is not a pitch" in findings[0].comment


def numbered(sheet: int, count: int = 2, **kw) -> PageExtraction:
    return page(title_block_fields=fields(sheet=f"{sheet} OF {count}", **kw))


def test_continuation_sheets_repeat_the_identification():
    params = {
        "required_fields": ["drawing_number", "sheet", "title", "scale"],
        "min_sheets": 2,
        "must_match_sheet1": ["drawing_number", "title"],
    }
    assert run("continuation_sheet_title_fields", numbered(1), numbered(2), **params)[1].status == "pass"
    findings, status = run("continuation_sheet_title_fields", numbered(1), numbered(2, scale="#"), **params)
    assert status.status == "fail" and "does not repeat the scale" in findings[0].comment
    findings, _ = run(
        "continuation_sheet_title_fields", numbered(1), numbered(2, number="P24OTHER00001"), **params
    )
    assert "has the drawing number 'P24OTHER00001'" in findings[0].comment
    assert run("continuation_sheet_title_fields", numbered(1), **params)[1].status == "not_applicable"


def test_sheet_one_carries_the_notes_and_revision_history_that_later_sheets_carry():
    notes = [TextLine(text="1.ALL DIMENSIONS ARE", bbox=(100, 600, 200, 608))]
    rows = rev_row(990, "1", "DIMENSION ADDED", "08/05/2024", "9265")
    both = {"min_sheets": 2}
    ok = run(
        "sheet1_has_title_revision_notes",
        page(body_text=notes, revision_rows=rows),
        page(body_text=notes),
        **both,
    )
    assert ok[1].status == "pass"
    no_notes = run("sheet1_has_title_revision_notes", page(), page(body_text=notes), **both)
    assert no_notes[1].status == "fail" and "general notes but sheet 1" in no_notes[0][0].comment
    no_history = run(
        "sheet1_has_title_revision_notes", page(body_text=notes), page(revision_rows=rows), **both
    )
    assert "revision rows but sheet 1 has none" in no_history[0][0].comment
    # a designer's numbered note about a hole table on sheet 2 is PARI's practice, not a finding
    table_note = [TextLine(text="1) ALL H7 HOLES C.D CONTROLLED", bbox=(600, 500, 800, 508))]
    assert (
        run("sheet1_has_title_revision_notes", page(body_text=notes), page(body_text=table_note), **both)[
            1
        ].status
        == "pass"
    )
    assert run("sheet1_has_title_revision_notes", page(), **both)[1].status == "not_applicable"


def test_limits_of_size_match_the_deviations():
    ok = page(dimensions=[dim(1, "⌀ 6 H7 (+0.012/0) 6.012/6.000"), dim(2, "15 (+0.1/-0.2) (15.100/14.800)")])
    assert run("limits_match_deviations", ok)[1].status == "pass"
    findings, status = run(
        "limits_match_deviations", page(dimensions=[dim(1, "⌀ 6 H7 (+0.012/0) 6.015/6.000")])
    )
    assert status.status == "fail" and "6.012 / 6.000" in findings[0].comment
    # PARI prints deviations only: nothing to compare
    deviations_only = page(dimensions=[dim(1, "⌀ 6 H7 (+0.012/0)"), dim(2, "351.43 (-2.12/0.00)")])
    assert run("limits_match_deviations", deviations_only)[1].status == "not_applicable"


# --- P1 batch 5: the last eight -----------------------------------------------------------------------------


def test_checker_must_not_be_the_drawer():
    ok = page(title_block_fields=fields(drawn_by="03006751", checked_by="03004785"))
    assert run("checker_independent", ok)[1].status == "pass"
    same = page(title_block_fields=fields(drawn_by="6330(MD)", checked_by="6330"))
    findings, status = run("checker_independent", same)
    assert status.status == "fail" and "same person" in findings[0].comment
    initials = page(title_block_fields=fields(drawn_by="M.S.K.", checked_by="MSK"))
    assert run("checker_independent", initials)[1].status == "fail"
    # a blank checker is TB-016's business, not a finding here
    blank = page(title_block_fields=fields(drawn_by="03006751", checked_by=None))
    assert run("checker_independent", blank)[1].status == "not_applicable"
    # cells that were never read (an extraction made before the template had them) cannot be checked
    unread = page(title_block_fields=fields())
    assert run("checker_independent", unread)[1].status == "not_checked"


def car_page(*rows: tuple[float, str, str | None]) -> PageExtraction:
    """The older revision table: header at y 636, rows above it as (y, date, change number or None)."""
    lines = [
        TextLine(text="CAR. NO.", bbox=(352, 636, 386, 652)),
        TextLine(text="DATE", bbox=(401, 636, 430, 652)),
    ]
    for y, date, car in rows:
        lines.append(TextLine(text=date, bbox=(394, y, 434, y + 11)))
        if car:
            lines.append(TextLine(text=car, bbox=(354, y, 383, y + 11)))
    return page(body_text=lines)


def test_every_revision_in_a_car_table_has_its_change_number():
    ok = car_page((624, "21.03.2009", "3015/09"), (610, "18.05.2011", "4362/11"))
    assert run("revision_change_ref", ok)[1].status == "pass"
    findings, status = run(
        "revision_change_ref", car_page((624, "21.03.2009", None), (610, "18.05.2011", "4362/11"))
    )
    assert status.status == "fail" and len(findings) == 1 and "21.03.2009" in findings[0].comment
    assert run("revision_change_ref", page(revision_rows=rev_row(990, "1", "DIMENSION ADDED", "08/05/2024")))[
        1
    ].status == ("not_applicable")


def test_two_revisions_with_the_same_date_are_two_findings():
    # a finding's id comes from its quoted evidence: the row's mark and description keep the two apart
    table = car_page((624, "12.05.2024", None), (610, "12.05.2024", None))
    table.body_text += [
        TextLine(text="REVISION", bbox=(42, 637, 80, 651)),
        TextLine(text="01", bbox=(52, 621, 60, 632)),
        TextLine(text="HOLE ADDED", bbox=(85, 626, 200, 637)),
        TextLine(text="2", bbox=(56, 610, 60, 621)),
        TextLine(text="CHAMFER REVISED", bbox=(83, 610, 220, 621)),
    ]
    findings, status = run("revision_change_ref", table)
    assert status.status == "fail" and len(findings) == 2
    assert {f.comment for f in findings} == {
        "Revision 01 (dated 12.05.2024) has no change number (CAR. NO.).",
        "Revision 2 (dated 12.05.2024) has no change number (CAR. NO.).",
    }
    assert [e.quote for e in findings[0].evidence][1:] in (["01", "HOLE ADDED"], ["2", "CHAMFER REVISED"])


def option_page(*lines: tuple[str, float, float]) -> PageExtraction:
    return page(body_text=[TextLine(text=t, bbox=(x, y, x + 50, y + 9)) for t, x, y in lines])


def test_a_welding_note_keeps_one_option():
    both = option_page(
        ("1) DYE PENETRATION TEST FOR WELDING  -", 636, 224),
        ("APPLICABLE", 786, 221),
        ("NOT APPLICABLE", 786, 230),
        ("3) LEAK PROOF WELD JOINT  -", 636, 238),
        ("NOT REQUIRED", 786, 238),
    )
    findings, status = run("weld_note_options_resolved", both)
    assert status.status == "fail" and len(findings) == 1
    assert "DYE PENETRATION" in findings[0].comment and "no option was chosen" in findings[0].comment
    two_notes = option_page(
        ("8) STRESS RELIEVING -", 636, 205),
        ("APPLICABLE", 724, 200),
        ("NOT APPLICABLE", 724, 209),
        ("1) DYE PENETRATION TEST  -", 636, 224),
        ("APPLICABLE", 786, 221),
        ("NOT APPLICABLE", 786, 230),
    )
    assert len(run("weld_note_options_resolved", two_notes)[0]) == 2  # same words, told apart by their notes
    assert run("weld_note_options_resolved", option_page(("NOT REQUIRED", 786, 238)))[1].status == "pass"
    # one option left, whichever it is, is a resolved note (a lone option must not pair with itself)
    assert run("weld_note_options_resolved", option_page(("APPLICABLE", 786, 221)))[1].status == "pass"
    assert run("weld_note_options_resolved", option_page(("REQUIRED", 786, 221), ("APPLICABLE", 786, 230)))[
        1
    ].status == ("pass")
    assert run("weld_note_options_resolved", option_page(("WELD: APPLICABLE / NOT APPLICABLE", 100, 100)))[
        1
    ].status == ("fail")
    assert run("weld_note_options_resolved", body_page("DEBURR"))[1].status == "not_applicable"
    # two notes each printed as "APPLICABLE / NOT APPLICABLE" are two findings, told apart by their labels
    one_line = option_page(
        ("9) STRESS RELIEVING -", 636, 200),
        ("APPLICABLE / NOT APPLICABLE", 724, 200),
        ("10) SHOT BLASTING -", 636, 207),
        ("APPLICABLE / NOT APPLICABLE", 724, 207),
    )
    findings, status = run("weld_note_options_resolved", one_line)
    assert status.status == "fail" and len(findings) == 2
    assert sorted(f.comment.split(":")[0] for f in findings) == [
        "'10) SHOT BLASTING -'",
        "'9) STRESS RELIEVING -'",
    ]


def test_a_tapped_hole_callout_gives_its_depth():
    params = {"require_class": False}
    ok = body_page("M6 x 12 DEEP TAPPED HOLE", "4 HOLES M8 THRU")
    assert run("thread_callout_complete", ok, **params)[1].status == "pass"
    findings, status = run("thread_callout_complete", body_page("4 HOLES M8"), **params)
    assert status.status == "fail" and "depth" in findings[0].comment
    # a bare size, a change note and a drawing without tapped holes are not judged
    for text in ("M8", "NEW M6 TAP HOLE ADDED (04 NOS)", "DEBURR ALL EDGES"):
        assert run("thread_callout_complete", body_page(text), **params)[1].status == "not_applicable"
    assert (
        run("thread_callout_complete", body_page("4 HOLES M8 THRU"), require_class=True)[1].status == "fail"
    )


def test_a_chamfer_gives_length_and_angle():
    params = {"formats": ["length x angle"]}
    length_only = option_page(("CH1.5", 100, 100))
    findings, status = run("chamfer_callout_complete", length_only, **params)
    assert status.status == "fail" and "no angle" in findings[0].comment
    angle_only = option_page(("CH 45°", 100, 100))
    assert "no length" in run("chamfer_callout_complete", angle_only, **params)[0][0].comment
    split = page(
        body_text=[
            TextLine(text="CH0.5", bbox=(523, 132, 551, 142)),
            TextLine(text="x45°", bbox=(552, 131, 570, 142)),
        ]
    )
    assert run("chamfer_callout_complete", split, **params)[1].status == "pass"
    assert (
        run("chamfer_callout_complete", body_page("1 x 45°", "CH.1 x 45°"), **params)[1].status
        == "not_applicable"
    )


def test_a_countersink_gives_its_angle():
    params = {"required": ["angle"], "example": {"angle_deg": 90}, "screw_seat_angle_deg": 90}
    assert (
        run("countersink_callout_complete", body_page("C'SINK Ø 12.00 mm x 90°"), **params)[1].status
        == "pass"
    )
    split = page(
        body_text=[
            TextLine(text="CSK Ø 12 mm", bbox=(100, 100, 200, 110)),
            TextLine(text="x 90°", bbox=(100, 112, 150, 122)),
        ]
    )
    assert run("countersink_callout_complete", split, **params)[1].status == "pass"
    findings, status = run("countersink_callout_complete", body_page("C'SINK Ø 12.00 mm"), **params)
    assert status.status == "fail" and "no included angle" in findings[0].comment
    assert run("countersink_callout_complete", body_page("COUNTERSINK AS REQUIRED"), **params)[1].status == (
        "not_applicable"
    )


def test_a_taper_ratio_and_cone_angle_agree():
    assert run("taper_values_consistent", body_page("TAPER 1:10 (5°43'29\")"))[1].status == "pass"
    assert run("taper_values_consistent", body_page("TAPER 1:10 5.7°"))[1].status == "pass"
    findings, status = run("taper_values_consistent", body_page("TAPER 1:10 (7°)"))
    assert status.status == "fail" and "5.7248" in findings[0].comment
    assert run("taper_values_consistent", body_page("SCALE 1:2 30°"))[1].status == "not_applicable"
    # minutes without seconds are rounded to half a minute: 5°43' is 1:10 rounded, 5°45' is not
    assert run("taper_values_consistent", body_page("TAPER 1:10 5°43'"))[1].status == "pass"
    assert run("taper_values_consistent", body_page("TAPER 1:10 5°44'"))[1].status == "fail"


def test_dual_dimensions_convert_correctly_and_a_roughness_is_not_one():
    ok = page(dimensions=[dim(1, "25.4 (1.00)"), dim(2, "1.00 [25.4]"), dim(3, "50.8 (2.00)")])
    assert run("dual_dimensioning", ok, mm_per_inch=25.4)[1].status == "pass"
    findings, status = run("dual_dimensioning", page(dimensions=[dim(1, "25.4 (1.10)")]), mm_per_inch=25.4)
    assert status.status == "fail" and "is 1.00 in, not 1.10" in findings[0].comment
    # PARI's '3.2 (0.8)' is a roughness, not a conversion
    assert run("dual_dimensioning", page(dimensions=[dim(1, "3.2 (0.8)")]), mm_per_inch=25.4)[1].status == (
        "not_applicable"
    )
