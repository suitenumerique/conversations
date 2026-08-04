"""Extract and aggregate pydantic_evals reports for file-based storage."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from pydantic_evals.reporting import EvaluationReport, ReportCase


def _to_score(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _serialize_metadata(metadata: Any) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if hasattr(metadata, "model_dump"):
        return metadata.model_dump()
    if isinstance(metadata, dict):
        return metadata
    return {"value": str(metadata)}


def _case_evaluator_results(case: ReportCase) -> dict[str, tuple[float | None, str | None]]:
    results: dict[str, tuple[float | None, str | None]] = {}
    for source in (case.assertions, case.scores):
        if not source:
            continue
        for name, result in source.items():
            results[name] = (_to_score(result.value), result.reason)
    return results


_PASS_SCORE_TOLERANCE = 1e-9


def _score_passes(score: float) -> bool:
    """Single pass threshold shared by case- and evaluator-level aggregation."""
    return score >= 1.0 - _PASS_SCORE_TOLERANCE


def _repeat_passed(evaluator_results: dict[str, tuple[float | None, str | None]]) -> bool:
    scores = [score for score, _ in evaluator_results.values() if score is not None]
    if not scores:
        # No exploitable score (no evaluator ran, or all returned labels/None):
        # fail rather than silently pass a case that was never actually checked.
        return False
    return all(_score_passes(score) for score in scores)


def _case_group_key(case: ReportCase) -> str:
    return case.source_case_name or case.name.split(" [", 1)[0]


def _group_report_cases(report: EvaluationReport) -> dict[str, list[ReportCase]]:
    groups: dict[str, list[ReportCase]] = defaultdict(list)
    for case in report.cases:
        groups[_case_group_key(case)].append(case)
    return groups


def _collect_repeat_evaluator_stats(
    repeats: list[ReportCase],
) -> tuple[dict[str, list[float]], dict[str, list[str]], list[bool]]:
    evaluator_values: dict[str, list[float]] = defaultdict(list)
    evaluator_reasons: dict[str, list[str]] = defaultdict(list)
    repeat_pass_flags: list[bool] = []

    for repeat_case in repeats:
        repeat_results = _case_evaluator_results(repeat_case)
        repeat_pass_flags.append(_repeat_passed(repeat_results))
        for evaluator_name, (score, reason) in repeat_results.items():
            if score is not None:
                evaluator_values[evaluator_name].append(score)
            if reason:
                evaluator_reasons[evaluator_name].append(reason)

    return evaluator_values, evaluator_reasons, repeat_pass_flags


def _build_aggregated_case_entry(
    case_name: str,
    repeats: list[ReportCase],
    *,
    include_outputs: bool,
) -> dict[str, Any]:
    evaluator_values, evaluator_reasons, repeat_pass_flags = _collect_repeat_evaluator_stats(
        repeats
    )
    avg_scores = {name: round(mean(values), 4) for name, values in sorted(evaluator_values.items())}
    reasons = {name: values[-1] for name, values in sorted(evaluator_reasons.items()) if values}
    pass_rate = round(mean(1.0 if passed else 0.0 for passed in repeat_pass_flags), 4)

    entry: dict[str, Any] = {
        "name": case_name,
        "metadata": _serialize_metadata(repeats[0].metadata),
        "repeats": len(repeats),
        "pass_rate": pass_rate,
        "passed": all(repeat_pass_flags),
        "avg_scores": avg_scores,
        "reasons": reasons,
        "task_duration_ms": round(
            mean(repeat_case.task_duration * 1000 for repeat_case in repeats), 1
        ),
    }
    if include_outputs:
        entry["outputs"] = [repeat_case.output for repeat_case in repeats]
    return entry


def aggregate_report_cases(
    report: EvaluationReport,
    *,
    include_outputs: bool = False,
) -> list[dict[str, Any]]:
    """Group repeat runs by source case and compute averages."""
    groups = _group_report_cases(report)
    return [
        _build_aggregated_case_entry(case_name, groups[case_name], include_outputs=include_outputs)
        for case_name in sorted(groups)
    ]


def build_dataset_result(
    report: EvaluationReport,
    *,
    include_outputs: bool = False,
) -> dict[str, Any]:
    """Build a JSON-serializable summary for one dataset report."""
    cases = aggregate_report_cases(report, include_outputs=include_outputs)
    cases_total = len(cases)
    cases_passed = sum(1 for case in cases if case["passed"])

    evaluator_scores: dict[str, list[float]] = defaultdict(list)
    evaluator_pass_rates: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        for evaluator_name, score in case["avg_scores"].items():
            evaluator_scores[evaluator_name].append(score)
            evaluator_pass_rates[evaluator_name].append(1.0 if _score_passes(score) else 0.0)

    evaluators = {
        name: {
            "avg_score": round(mean(scores), 4),
            "pass_rate": round(mean(evaluator_pass_rates[name]), 4),
        }
        for name, scores in sorted(evaluator_scores.items())
    }

    return {
        "cases_total": cases_total,
        "cases_passed": cases_passed,
        "pass_rate": round(cases_passed / cases_total, 4) if cases_total else 0.0,
        "pass_rate_avg_repeats": round(mean(case["pass_rate"] for case in cases), 4)
        if cases
        else 0.0,
        "evaluators": evaluators,
        "cases": cases,
        "failures": len(report.failures),
    }
