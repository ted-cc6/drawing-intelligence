"""Unit tests for eval.stability (A1, criterion 6). Synthetic data only."""

import pytest

from drawing_intelligence.eval.stability import score_stability


def _drawing(title_block, n_dims):
    return {
        "title_block": title_block,
        "dimensions": [{"id": f"D{i}"} for i in range(n_dims)],
    }


def test_identical_runs_are_stable():
    tb = {"material": "EN8", "part_number": "10K-001"}
    runs = [_drawing(tb, 21) for _ in range(3)]
    result = score_stability(runs)
    assert result["n_runs"] == 3
    assert result["title_block_stable"] is True
    assert result["dimension_count_stable"] is True
    assert result["title_block_variants"] == 1
    assert result["dimension_counts"] == {21: 3}


def test_title_block_disagreement_is_flagged():
    runs = [
        _drawing({"material": "EN8"}, 21),
        _drawing({"material": "EN9"}, 21),  # one run disagrees
    ]
    result = score_stability(runs)
    assert result["title_block_stable"] is False
    assert result["title_block_variants"] == 2
    assert result["dimension_count_stable"] is True


def test_dimension_count_disagreement_is_flagged():
    runs = [_drawing({"material": "EN8"}, 21), _drawing({"material": "EN8"}, 20)]
    result = score_stability(runs)
    assert result["title_block_stable"] is True
    assert result["dimension_count_stable"] is False
    assert result["dimension_counts"] == {21: 1, 20: 1}


def test_title_block_key_order_does_not_matter():
    a = _drawing({"material": "EN8", "part_number": "P1"}, 5)
    b = _drawing({"part_number": "P1", "material": "EN8"}, 5)
    result = score_stability([a, b])
    assert result["title_block_stable"] is True


def test_requires_at_least_one_run():
    with pytest.raises(ValueError):
        score_stability([])
