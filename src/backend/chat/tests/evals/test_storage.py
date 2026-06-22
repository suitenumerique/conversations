"""Unit tests for eval report aggregation and comparison."""

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.evaluators.evaluator import EvaluationReason

from chat.evals.compare import compare_runs, format_comparison
from chat.evals.report_builder import aggregate_report_cases, build_dataset_result


class _PassIfYes(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        return EvaluationReason(value=ctx.output == "yes", reason=None if ctx.output == "yes" else "no")


def test_aggregate_report_cases_averages_repeats():
    dataset = Dataset(
        name="test",
        cases=[Case(name="case_a", inputs="prompt")],
        evaluators=[_PassIfYes()],
    )
    outputs = iter(["yes", "no", "yes"])

    def task(_prompt: str) -> str:
        return next(outputs)

    report = dataset.evaluate_sync(task, repeat=3)
    aggregated = aggregate_report_cases(report)

    assert len(aggregated) == 1
    case = aggregated[0]
    assert case["name"] == "case_a"
    assert case["repeats"] == 3
    assert case["pass_rate"] == 0.6667
    assert case["passed"] is False
    assert case["avg_scores"]["_PassIfYes"] == 0.6667


def test_build_dataset_result_includes_avg_repeat_pass_rate():
    dataset = Dataset(
        name="test",
        cases=[Case(name="mixed", inputs="prompt")],
        evaluators=[_PassIfYes()],
    )
    outputs = iter(["yes", "no"])

    def task(_prompt: str) -> str:
        return next(outputs)

    report = dataset.evaluate_sync(task, repeat=2)
    result = build_dataset_result(report)

    assert result["cases_total"] == 1
    assert result["cases_passed"] == 0
    assert result["pass_rate"] == 0.0
    assert result["pass_rate_avg_repeats"] == 0.5


def test_compare_runs_detects_regression_and_dataset_hash_warning():
    before = {
        "run_id": "before",
        "comment": "baseline",
        "datasets": {
            "url_hallucination": {
                "pass_rate": 1.0,
                "pass_rate_avg_repeats": 1.0,
                "cases": [
                    {
                        "name": "easy",
                        "passed": True,
                        "pass_rate": 1.0,
                        "avg_scores": {"judge": 1.0},
                        "reasons": {},
                    },
                    {
                        "name": "hard",
                        "passed": True,
                        "pass_rate": 1.0,
                        "avg_scores": {"judge": 1.0},
                        "reasons": {},
                    },
                ],
            }
        },
        "dataset_hashes": {"url_hallucination": "sha256:aaa"},
    }
    after = {
        "run_id": "after",
        "comment": "current",
        "datasets": {
            "url_hallucination": {
                "pass_rate": 0.5,
                "pass_rate_avg_repeats": 0.75,
                "cases": [
                    {
                        "name": "easy",
                        "passed": True,
                        "pass_rate": 1.0,
                        "avg_scores": {"judge": 1.0},
                        "reasons": {},
                    },
                    {
                        "name": "hard",
                        "passed": False,
                        "pass_rate": 0.5,
                        "avg_scores": {"judge": 0.5},
                        "reasons": {"judge": "hallucinated"},
                    },
                ],
            }
        },
        "dataset_hashes": {"url_hallucination": "sha256:bbb"},
    }

    comparison = compare_runs(before, after)
    rendered = format_comparison(comparison)

    assert len(comparison.regressions) == 1
    assert comparison.regressions[0].case_name == "hard"
    assert "Dataset 'url_hallucination' changed between runs" in rendered
    assert "REGRESSION" in rendered
