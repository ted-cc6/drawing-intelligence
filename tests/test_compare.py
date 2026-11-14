"""Compare revisions (api/compare.py): which findings are new, fixed or still open between two reviews."""

from typing import Any

from drawing_intelligence.api.compare import anchor, compare


def _f(
    rule: str,
    ref: str | None = None,
    quote: str | None = None,
    zone: str | None = None,
    location: str = "loc",
    no: int = 1,
) -> dict[str, Any]:
    evidence = [] if ref is None and quote is None else [{"ref": ref, "quote": quote, "zone": zone}]
    return {"no": no, "rule_id": rule, "category": "cat", "location": location, "evidence": evidence}


def _view(
    findings: list[dict[str, Any]],
    tb: dict[str, str] | None = None,
    rows: list[str] | None = None,
    id: str = "s",
    name: str = "n",
) -> dict[str, Any]:
    tb = {"number": "P1", "revision": "00"} if tb is None else tb
    return {"id": id, "name": name, "title_block": tb, "findings": findings, "revision_rows": rows or []}


def _rules(items: list[dict[str, Any]]) -> list[str]:
    return [f["rule_id"] for f in items]


def test_anchor_drops_the_tolerance_of_a_numbered_ref():
    # D-numbers are positions on the sheet: a dimension added before D12 renumbers it
    assert anchor(_f("WPS-004", "D12", "⌀ 16 H7 (-0.018/0)", "D3")) == anchor(
        _f("WPS-004", "D7", "⌀ 16 H7 (+0.018/0)", "D3")
    )
    assert anchor(_f("X", "D1", "25 ±0.1", "B2")) == anchor(_f("X", "D9", "25 ±0.2", "B2"))
    assert anchor(_f("X", "D1", "25 ±0.1", "B2")) != anchor(_f("X", "D1", "25 ±0.1", "C2"))


def test_a_named_ref_is_its_own_anchor():
    assert anchor(_f("TB-016", "checked_date", "01/10/2025")) == anchor(
        _f("TB-016", "checked_date", "02/11/2026")
    )


def test_no_evidence_falls_back_to_location():
    assert anchor(_f("A", location="note 3")) == anchor(_f("A", location="note 3"))
    assert anchor(_f("A", location="note 3")) != anchor(_f("A", location="note 4"))


def test_findings_split_into_new_fixed_still_open():
    old = _view([_f("A", "D1", "10 H7", "A1"), _f("B", "D2", "20 (+0.1/0)", "B1")])
    new = _view([_f("B", "D5", "20 (-0.1/0)", "B1"), _f("C", "flag", "x")])
    out = compare(old, new)["findings"]
    assert _rules(out["new"]) == ["C"] and _rules(out["fixed"]) == ["A"]
    (b,) = out["still_open"]
    assert b["rule_id"] == "B" and b["was"] == "20 (+0.1/0)" and b["now"] == "20 (-0.1/0)"
    same = compare(old, old)["findings"]["still_open"]
    assert all(f["was"] is None and f["now"] is None for f in same)


def test_a_changed_nominal_is_fixed_plus_new():
    out = compare(_view([_f("A", "D1", "⌀ 16 H7", "A1")]), _view([_f("A", "D1", "⌀ 18 H7", "A1")]))[
        "findings"
    ]
    assert len(out["fixed"]) == 1 and len(out["new"]) == 1 and out["still_open"] == []


def test_duplicates_match_one_to_one():
    old = _view([_f("A", "D1", "5", "A1", no=1), _f("A", "D2", "5", "A1", no=2)])
    out = compare(old, _view([_f("A", "D1", "5", "A1")]))["findings"]
    assert len(out["still_open"]) == 1 and len(out["fixed"]) == 1 and out["new"] == []


def test_same_view_twice_is_all_still_open():
    v = _view([_f("A", "D1", "5", "A1"), _f("B", location="x")])
    out = compare(v, v)
    assert out["findings"]["new"] == [] and out["findings"]["fixed"] == []
    assert len(out["findings"]["still_open"]) == 2 and out["notes"] == [] and out["title_block"] == []


def test_title_block_and_revision_rows():
    old = _view(
        [], tb={"number": "P1", "revision": "00", "material": "M.S.", "weight": "1 kg"}, rows=["r1", "r2"]
    )
    new = _view(
        [], tb={"number": "P1", "revision": "01", "weight": "2 kg", "scale": "1 : 2"}, rows=["r2", "r3"]
    )
    out = compare(old, new)
    assert out["title_block"] == [
        {"field": "material", "old": "M.S.", "new": None},
        {"field": "revision", "old": "00", "new": "01"},
        {"field": "scale", "old": None, "new": "1 : 2"},
        {"field": "weight", "old": "1 kg", "new": "2 kg"},
    ]
    assert out["revision_rows"] == {"added": ["r3"], "removed": ["r1"]}
    assert out["old"] == {"id": "s", "name": "n", "number": "P1", "revision": "00"}


def test_notes():
    a = _view([_f("A", location="x")])
    b = _view([])
    assert compare(a, b)["notes"] == [
        "Both sheets say revision 00. The findings changed, so the drawing changed without a new revision."
    ]
    other = _view([], tb={"number": "P2", "revision": "01"})
    (note,) = compare(a, other)["notes"]
    assert "P1" in note and "P2" in note
    assert compare(a, _view([], tb={"number": "P1", "revision": "01"}))["notes"] == []


def test_no_revision_claim_when_the_title_block_was_not_read():
    # uploads on an unknown template have no number or revision: never claim they are the same drawing
    out = compare(_view([_f("A", location="x")], tb={}), _view([], tb={}))
    assert out["notes"] == ["The drawing number could not be read on one or both sheets."]
    one = compare(_view([_f("A", location="x")]), _view([], tb={"number": "P1"}))
    assert one["notes"] == []
