"""Tests for eval run comparison helpers."""

from chat.evals.compare import compare_runs


def _run(*, run_id: str, datasets: dict) -> dict:
    return {
        "run_id": run_id,
        "datasets": datasets,
        "dataset_hashes": {name: f"hash-{name}" for name in datasets},
    }


def _dataset(*, pass_rate: float, cases: list[dict]) -> dict:
    return {
        "pass_rate": pass_rate,
        "pass_rate_avg_repeats": pass_rate,
        "cases": cases,
    }


def _case(*, name: str, passed: bool) -> dict:
    return {
        "name": name,
        "passed": passed,
        "pass_rate": 1.0 if passed else 0.0,
        "avg_scores": {"faithfulness": 1.0 if passed else 0.0},
        "reasons": {},
    }


def test_missing_after_dataset_records_coverage_gaps():
    """Test that missing after dataset records coverage gaps."""
    before = _run(
        run_id="before",
        datasets={
            "ds": _dataset(
                pass_rate=1.0,
                cases=[_case(name="a", passed=True), _case(name="b", passed=False)],
            )
        },
    )
    after = _run(run_id="after", datasets={})

    comparison = compare_runs(before, after)

    assert len(comparison.coverage_gaps) == 2
    assert comparison.has_regression_failures
    assert len(comparison.regressions) == 1


def test_missing_after_case_records_coverage_gap():
    """Test that missing after case records coverage gaps."""
    before = _run(
        run_id="before",
        datasets={
            "ds": _dataset(
                pass_rate=0.5,
                cases=[_case(name="a", passed=True), _case(name="b", passed=False)],
            )
        },
    )
    after = _run(
        run_id="after",
        datasets={"ds": _dataset(pass_rate=1.0, cases=[_case(name="a", passed=True)])},
    )

    comparison = compare_runs(before, after)

    assert len(comparison.coverage_gaps) == 1
    assert comparison.coverage_gaps[0].case_name == "b"
    assert comparison.has_regression_failures
    assert not comparison.regressions


def test_missing_before_dataset_is_warning_only():
    """Test that missing before dataset is warning only."""
    before = _run(run_id="before", datasets={})
    after = _run(
        run_id="after",
        datasets={"ds": _dataset(pass_rate=1.0, cases=[_case(name="a", passed=True)])},
    )

    comparison = compare_runs(before, after)

    assert not comparison.coverage_gaps
    assert not comparison.has_regression_failures
    assert any("missing from before run" in warning for warning in comparison.warnings)
