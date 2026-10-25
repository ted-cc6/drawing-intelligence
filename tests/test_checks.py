"""The check machinery and the first code checks (ADR 0010), on synthetic stage 1 data. No PDF, no LLM."""

from __future__ import annotations

from pathlib import Path

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


def ctx(*pages: PageExtraction, rules: list[Rule] | None = None) -> ReviewContext:
    ex = Extraction(source_file="t.pdf", template="wipro_pari", n_pages=len(pages), pages=list(pages))
    return ReviewContext(extraction=ex, rulebook=Rulebook(version="t", rules=rules or []), template=TEMPLATE)


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
        process="machining", kind="linear", over=o, up_to=u, tolerance=f"±{v:g}", value_mm=v,
        bbox=(0, 0, 1, 1),
    )
    for o, u, v in [(0.5, 3, 0.1), (3, 6, 0.1), (6, 30, 0.2), (30, 120, 0.3), (120, 315, 0.5)]
]  # fmt: skip


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
    assert run("treatment_material_compat", p, table="plating_processes")[1].status == "not_checked"


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
