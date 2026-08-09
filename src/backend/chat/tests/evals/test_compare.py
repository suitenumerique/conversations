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


def test_to_payload_serializes_change_kinds():
    """to_payload must expose the Python-computed kind for each case change."""
    before = _run(
        run_id="before",
        datasets={
            "ds": _dataset(
                pass_rate=0.5,
                cases=[
                    _case(name="reg", passed=True),
                    _case(name="imp", passed=False),
                    _case(name="gone", passed=True),
                    _case(name="same", passed=True),
                ],
            )
        },
    )
    after = _run(
        run_id="after",
        datasets={
            "ds": _dataset(
                pass_rate=0.5,
                cases=[
                    _case(name="reg", passed=False),
                    _case(name="imp", passed=True),
                    _case(name="same", passed=True),
                ],
            )
        },
    )

    payload = compare_runs(before, after).to_payload()

    kinds = {c["name"]: c["kind"] for c in payload["datasets"]["ds"]["case_changes"]}
    assert kinds == {"reg": "regression", "imp": "improvement", "gone": "coverage_gap"}
    assert payload["before_run_id"] == "before"
    assert payload["after_run_id"] == "after"
    assert payload["datasets"]["ds"]["dataset_hash_match"] is True


def test_kind_partial_up_when_both_fail_but_rate_improves():
    """Both runs fail but the repeat pass rate improves: kind is partial_up."""
    partial_before = {
        "name": "p",
        "passed": False,
        "pass_rate": 0.2,
        "avg_scores": {},
        "reasons": {},
    }
    partial_after = {**partial_before, "pass_rate": 0.8}
    before = _run(run_id="before", datasets={"ds": _dataset(pass_rate=0.0, cases=[partial_before])})
    after = _run(run_id="after", datasets={"ds": _dataset(pass_rate=0.0, cases=[partial_after])})

    payload = compare_runs(before, after).to_payload()

    kinds = {c["name"]: c["kind"] for c in payload["datasets"]["ds"]["case_changes"]}
    assert kinds == {"p": "partial_up"}


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
