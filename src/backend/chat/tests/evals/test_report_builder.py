"""Tests for eval report aggregation helpers."""

from chat.evals.report_builder import _repeat_passed


def test_repeat_passed_accepts_boolean_and_near_perfect_scores():
    """Test that repeat_passed accepts boolean and near perfect scores."""
    assert _repeat_passed({"assertion": (1.0, None)})
    assert _repeat_passed({"assertion": (1.0 - 1e-10, None)})
    assert not _repeat_passed({"assertion": (0.0, None)})
    assert not _repeat_passed({"assertion": (0.99, None)})


def test_repeat_passed_requires_all_evaluators_to_pass():
    """Test that repeat_passed requires all evaluators to pass."""
    results = {
        "assertion": (1.0, None),
        "score": (0.999999999, None),
        "weak": (0.5, "too low"),
    }
    assert _repeat_passed({k: results[k] for k in ("assertion", "score")})
    assert not _repeat_passed(results)
