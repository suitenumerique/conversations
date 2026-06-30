"""Compare saved eval runs and detect regressions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chat.evals.storage import load_baseline, resolve_run


@dataclass
class CaseChange:  # pylint: disable=too-many-instance-attributes
    """Per-case delta between two eval runs."""

    dataset: str
    case_name: str
    before_passed: bool
    after_passed: bool
    before_pass_rate: float
    after_pass_rate: float
    before_avg_scores: dict[str, float]
    after_avg_scores: dict[str, float]
    reasons: dict[str, str | None] = field(default_factory=dict)
    coverage_gap: bool = False


@dataclass
class DatasetComparison:
    """Aggregated comparison for one dataset across two runs."""

    dataset: str
    before_pass_rate: float
    after_pass_rate: float
    before_pass_rate_avg_repeats: float
    after_pass_rate_avg_repeats: float
    dataset_hash_match: bool
    case_changes: list[CaseChange] = field(default_factory=list)


@dataclass
class RunComparison:
    """Full comparison between a baseline run and a candidate run."""

    before_run_id: str
    after_run_id: str
    before_comment: str | None
    after_comment: str | None
    dataset_comparisons: list[DatasetComparison] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def regressions(self) -> list[CaseChange]:
        """Cases that passed before and fail after."""
        return [
            change
            for comparison in self.dataset_comparisons
            for change in comparison.case_changes
            if change.before_passed and not change.after_passed
        ]

    @property
    def improvements(self) -> list[CaseChange]:
        """Cases that failed before and pass after."""
        return [
            change
            for comparison in self.dataset_comparisons
            for change in comparison.case_changes
            if not change.before_passed and change.after_passed
        ]

    @property
    def coverage_gaps(self) -> list[CaseChange]:
        """Cases present in before but missing from after."""
        return [
            change
            for comparison in self.dataset_comparisons
            for change in comparison.case_changes
            if change.coverage_gap
        ]

    @property
    def has_regression_failures(self) -> bool:
        """Whether --fail-on-regression should exit non-zero."""
        return bool(self.regressions or self.coverage_gaps)


def _case_map(dataset_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index dataset case results by case name."""
    return {case["name"]: case for case in dataset_result.get("cases", [])}


def _missing_after_case_change(
    *,
    dataset_name: str,
    before_case: dict[str, Any],
) -> CaseChange:
    """Build a CaseChange for a case that is absent from the after run."""
    return CaseChange(
        dataset=dataset_name,
        case_name=before_case["name"],
        before_passed=before_case["passed"],
        after_passed=False,
        before_pass_rate=before_case["pass_rate"],
        after_pass_rate=0.0,
        before_avg_scores=before_case["avg_scores"],
        after_avg_scores={},
        reasons={"_coverage": "missing from after run"},
        coverage_gap=True,
    )


def _dataset_comparison_missing_after(
    dataset_name: str,
    before_dataset: dict[str, Any],
) -> DatasetComparison:
    """Build a dataset comparison when the after run has no results for it."""
    case_changes = [
        _missing_after_case_change(dataset_name=dataset_name, before_case=before_case)
        for before_case in sorted(before_dataset.get("cases", []), key=lambda case: case["name"])
    ]
    return DatasetComparison(
        dataset=dataset_name,
        before_pass_rate=before_dataset["pass_rate"],
        after_pass_rate=0.0,
        before_pass_rate_avg_repeats=before_dataset["pass_rate_avg_repeats"],
        after_pass_rate_avg_repeats=0.0,
        dataset_hash_match=False,
        case_changes=case_changes,
    )


def _cases_unchanged(
    before_case: dict[str, Any],
    after_case: dict[str, Any],
) -> bool:
    """Return whether pass status, pass rate, and scores are identical."""
    return (
        before_case["passed"] == after_case["passed"]
        and before_case["pass_rate"] == after_case["pass_rate"]
        and before_case["avg_scores"] == after_case["avg_scores"]
    )


def _case_change_for_pair(
    *,
    dataset_name: str,
    case_name: str,
    before_case: dict[str, Any],
    after_case: dict[str, Any],
) -> CaseChange:
    """Build a CaseChange for a case present in both runs with differing results."""
    return CaseChange(
        dataset=dataset_name,
        case_name=case_name,
        before_passed=before_case["passed"],
        after_passed=after_case["passed"],
        before_pass_rate=before_case["pass_rate"],
        after_pass_rate=after_case["pass_rate"],
        before_avg_scores=before_case["avg_scores"],
        after_avg_scores=after_case["avg_scores"],
        reasons=after_case.get("reasons", {}),
    )


def _compare_case(
    *,
    dataset_name: str,
    case_name: str,
    before_cases: dict[str, dict[str, Any]],
    after_cases: dict[str, dict[str, Any]],
) -> CaseChange | None:
    """Compare one case across runs; return a CaseChange when a delta exists."""
    before_case = before_cases.get(case_name)
    after_case = after_cases.get(case_name)
    if after_case is None:
        if before_case is not None:
            return _missing_after_case_change(
                dataset_name=dataset_name,
                before_case=before_case,
            )
        return None
    if before_case is None or _cases_unchanged(before_case, after_case):
        return None
    return _case_change_for_pair(
        dataset_name=dataset_name,
        case_name=case_name,
        before_case=before_case,
        after_case=after_case,
    )


def _compare_datasets(
    *,
    dataset_name: str,
    before_dataset: dict[str, Any],
    after_dataset: dict[str, Any],
    dataset_hash_match: bool,
) -> DatasetComparison:
    """Compare one dataset present in both runs."""
    before_cases = _case_map(before_dataset)
    after_cases = _case_map(after_dataset)
    case_changes = [
        change
        for case_name in sorted(set(before_cases) | set(after_cases))
        if (
            change := _compare_case(
                dataset_name=dataset_name,
                case_name=case_name,
                before_cases=before_cases,
                after_cases=after_cases,
            )
        )
        is not None
    ]

    return DatasetComparison(
        dataset=dataset_name,
        before_pass_rate=before_dataset["pass_rate"],
        after_pass_rate=after_dataset["pass_rate"],
        before_pass_rate_avg_repeats=before_dataset["pass_rate_avg_repeats"],
        after_pass_rate_avg_repeats=after_dataset["pass_rate_avg_repeats"],
        dataset_hash_match=dataset_hash_match,
        case_changes=case_changes,
    )


def compare_runs(before: dict[str, Any], after: dict[str, Any]) -> RunComparison:
    """Compare two saved run records and return structured deltas."""
    comparison = RunComparison(
        before_run_id=before["run_id"],
        after_run_id=after["run_id"],
        before_comment=before.get("comment") or before.get("label"),
        after_comment=after.get("comment") or after.get("label"),
    )

    all_datasets = sorted(set(before["datasets"]) | set(after["datasets"]))
    for dataset_name in all_datasets:
        before_dataset = before["datasets"].get(dataset_name)
        after_dataset = after["datasets"].get(dataset_name)
        if before_dataset is None:
            comparison.warnings.append(f"Dataset '{dataset_name}' is missing from before run.")
            continue
        if after_dataset is None:
            comparison.warnings.append(f"Dataset '{dataset_name}' is missing from after run.")
            comparison.dataset_comparisons.append(
                _dataset_comparison_missing_after(dataset_name, before_dataset)
            )
            continue

        before_hash = before.get("dataset_hashes", {}).get(dataset_name)
        after_hash = after.get("dataset_hashes", {}).get(dataset_name)
        dataset_hash_match = before_hash == after_hash
        if not dataset_hash_match:
            comparison.warnings.append(
                f"Dataset '{dataset_name}' changed between runs "
                f"({before_hash} → {after_hash}). Comparison may be misleading."
            )
        comparison.dataset_comparisons.append(
            _compare_datasets(
                dataset_name=dataset_name,
                before_dataset=before_dataset,
                after_dataset=after_dataset,
                dataset_hash_match=dataset_hash_match,
            )
        )

    return comparison


def compare_with_baseline(
    *,
    run_ref: str | None,
    baseline_name: str = "main",
) -> RunComparison:
    """Compare a run against a named baseline."""
    baseline_meta = load_baseline(baseline_name)
    before, _ = resolve_run(baseline_meta["run_id"])
    after, _ = resolve_run(run_ref)
    return compare_runs(before, after)


def _note(comment: str | None) -> str:
    return f" — {comment}" if comment else ""


def render_case_change(change: CaseChange) -> list[str]:
    """Render a single case change."""
    before_status = "PASS" if change.before_passed else "FAIL"
    after_status = "PASS" if change.after_passed else "FAIL"
    repeat_info = f"repeat pass rate {change.before_pass_rate:.0%}→{change.after_pass_rate:.0%}"
    lines = [f"    {change.case_name}: {before_status} → {after_status} ({repeat_info})"]
    for evaluator_name, after_score in sorted(change.after_avg_scores.items()):
        before_score = change.before_avg_scores.get(evaluator_name)
        if before_score is None or before_score == after_score:
            continue
        lines.append(f"      {evaluator_name}: {before_score:.2f} → {after_score:.2f}")
    for evaluator_name, reason in sorted(change.reasons.items()):
        if reason:
            lines.append(f"      reason ({evaluator_name}): {reason}")
    return lines


def render_dataset_comparison(dataset_comparison: DatasetComparison) -> list[str]:
    """Render a dataset comparison."""
    delta = dataset_comparison.after_pass_rate - dataset_comparison.before_pass_rate
    delta_pct = round(delta * 100, 1)
    if delta < 0:
        status = f"REGRESSION ({delta_pct:+.1f}pp)"
    elif delta > 0:
        status = f"IMPROVEMENT ({delta_pct:+.1f}pp)"
    else:
        status = "stable"

    lines = [
        f"Dataset: {dataset_comparison.dataset}",
        (
            "  Pass rate (all repeats must pass): "
            f"{dataset_comparison.before_pass_rate:.0%} → "
            f"{dataset_comparison.after_pass_rate:.0%}  {status}"
        ),
        (
            "  Avg repeat pass rate: "
            f"{dataset_comparison.before_pass_rate_avg_repeats:.0%} → "
            f"{dataset_comparison.after_pass_rate_avg_repeats:.0%}"
        ),
    ]

    if not dataset_comparison.case_changes:
        lines.append("  Cases changed: none")
    else:
        lines.append("  Cases changed:")
        for change in dataset_comparison.case_changes:
            lines.extend(render_case_change(change))
    lines.append("")
    return lines


def format_comparison(comparison: RunComparison) -> str:
    """Render a human-readable comparison report."""
    lines: list[str] = [
        (
            f"Comparing after {comparison.after_run_id}"
            + _note(comparison.after_comment)
            + f" vs before {comparison.before_run_id}"
            + _note(comparison.before_comment)
        ),
        "",
    ]

    for warning in comparison.warnings:
        lines.append(f"⚠  {warning}")
    if comparison.warnings:
        lines.append("")

    for dataset_comparison in comparison.dataset_comparisons:
        lines.extend(render_dataset_comparison(dataset_comparison))

    coverage_gaps = len(comparison.coverage_gaps)
    summary = (
        f"Summary: {len(comparison.regressions)} regression(s), "
        f"{len(comparison.improvements)} improvement(s)"
    )
    if coverage_gaps:
        summary += f", {coverage_gaps} coverage gap(s)"
    lines.append(summary)
    return "\n".join(lines)
