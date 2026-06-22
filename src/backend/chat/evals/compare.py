"""Compare saved eval runs and detect regressions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chat.evals.storage import load_baseline, resolve_run


@dataclass
class CaseChange:
    dataset: str
    case_name: str
    before_passed: bool
    after_passed: bool
    before_pass_rate: float
    after_pass_rate: float
    before_avg_scores: dict[str, float]
    after_avg_scores: dict[str, float]
    reasons: dict[str, str | None] = field(default_factory=dict)


@dataclass
class DatasetComparison:
    dataset: str
    before_pass_rate: float
    after_pass_rate: float
    before_pass_rate_avg_repeats: float
    after_pass_rate_avg_repeats: float
    dataset_hash_match: bool
    case_changes: list[CaseChange] = field(default_factory=list)


@dataclass
class RunComparison:
    before_run_id: str
    after_run_id: str
    before_comment: str | None
    after_comment: str | None
    dataset_comparisons: list[DatasetComparison] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def regressions(self) -> list[CaseChange]:
        return [
            change
            for comparison in self.dataset_comparisons
            for change in comparison.case_changes
            if change.before_passed and not change.after_passed
        ]

    @property
    def improvements(self) -> list[CaseChange]:
        return [
            change
            for comparison in self.dataset_comparisons
            for change in comparison.case_changes
            if not change.before_passed and change.after_passed
        ]


def _case_map(dataset_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["name"]: case for case in dataset_result.get("cases", [])}


def compare_runs(before: dict[str, Any], after: dict[str, Any]) -> RunComparison:
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
        if before_dataset is None or after_dataset is None:
            comparison.warnings.append(
                f"Dataset '{dataset_name}' is missing from "
                f"{'after' if before_dataset else 'before'} run."
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

        dataset_comparison = DatasetComparison(
            dataset=dataset_name,
            before_pass_rate=before_dataset["pass_rate"],
            after_pass_rate=after_dataset["pass_rate"],
            before_pass_rate_avg_repeats=before_dataset["pass_rate_avg_repeats"],
            after_pass_rate_avg_repeats=after_dataset["pass_rate_avg_repeats"],
            dataset_hash_match=dataset_hash_match,
        )

        before_cases = _case_map(before_dataset)
        after_cases = _case_map(after_dataset)
        for case_name in sorted(set(before_cases) | set(after_cases)):
            before_case = before_cases.get(case_name)
            after_case = after_cases.get(case_name)
            if before_case is None or after_case is None:
                continue
            if (
                before_case["passed"] == after_case["passed"]
                and before_case["pass_rate"] == after_case["pass_rate"]
                and before_case["avg_scores"] == after_case["avg_scores"]
            ):
                continue
            dataset_comparison.case_changes.append(
                CaseChange(
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
            )

        comparison.dataset_comparisons.append(dataset_comparison)

    return comparison


def compare_with_baseline(
    *,
    run_ref: str | None,
    baseline_name: str = "main",
) -> RunComparison:
    baseline_meta = load_baseline(baseline_name)
    before, _ = resolve_run(baseline_meta["run_id"])
    after, _ = resolve_run(run_ref)
    return compare_runs(before, after)


def format_comparison(comparison: RunComparison) -> str:
    lines: list[str] = []
    def _note(comment: str | None) -> str:
        return f" — {comment}" if comment else ""

    lines.append(
        f"Comparing after {comparison.after_run_id}"
        + _note(comparison.after_comment)
        + f" vs before {comparison.before_run_id}"
        + _note(comparison.before_comment)
    )
    lines.append("")

    for warning in comparison.warnings:
        lines.append(f"⚠  {warning}")
    if comparison.warnings:
        lines.append("")

    for dataset_comparison in comparison.dataset_comparisons:
        delta = dataset_comparison.after_pass_rate - dataset_comparison.before_pass_rate
        delta_pct = round(delta * 100, 1)
        status = "stable"
        if delta < 0:
            status = f"REGRESSION ({delta_pct:+.1f}pp)"
        elif delta > 0:
            status = f"IMPROVEMENT ({delta_pct:+.1f}pp)"

        lines.append(f"Dataset: {dataset_comparison.dataset}")
        lines.append(
            "  Pass rate (all repeats must pass): "
            f"{dataset_comparison.before_pass_rate:.0%} → "
            f"{dataset_comparison.after_pass_rate:.0%}  {status}"
        )
        lines.append(
            "  Avg repeat pass rate: "
            f"{dataset_comparison.before_pass_rate_avg_repeats:.0%} → "
            f"{dataset_comparison.after_pass_rate_avg_repeats:.0%}"
        )

        if not dataset_comparison.case_changes:
            lines.append("  Cases changed: none")
        else:
            lines.append("  Cases changed:")
            for change in dataset_comparison.case_changes:
                before_status = "PASS" if change.before_passed else "FAIL"
                after_status = "PASS" if change.after_passed else "FAIL"
                repeat_info = (
                    f"repeat pass rate {change.before_pass_rate:.0%}"
                    f"→{change.after_pass_rate:.0%}"
                )
                lines.append(
                    f"    {change.case_name}: {before_status} → {after_status} ({repeat_info})"
                )
                for evaluator_name, after_score in sorted(change.after_avg_scores.items()):
                    before_score = change.before_avg_scores.get(evaluator_name)
                    if before_score is None or before_score == after_score:
                        continue
                    lines.append(
                        f"      {evaluator_name}: {before_score:.2f} → {after_score:.2f}"
                    )
                for evaluator_name, reason in sorted(change.reasons.items()):
                    if reason:
                        lines.append(f"      reason ({evaluator_name}): {reason}")
        lines.append("")

    lines.append(
        f"Summary: {len(comparison.regressions)} regression(s), "
        f"{len(comparison.improvements)} improvement(s)"
    )
    return "\n".join(lines)
