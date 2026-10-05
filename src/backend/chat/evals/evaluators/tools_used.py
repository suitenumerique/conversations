"""Evaluators on the target's tool usage and streamed sources for the scored turn."""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.evaluators.evaluator import EvaluationReason

SUMMARIZE_TOOLS = {"summarize", "summarize_project"}


def _describe(call: dict) -> str:
    name = call.get("name", "?")
    if name in SUMMARIZE_TOOLS:
        return f"{name}(instructions={(call.get('args') or {}).get('instructions')!r})"
    return name


@dataclass(repr=False)
class ToolsUsed(Evaluator):
    """Label the scored turn with the tools called; never affects pass/fail."""

    def evaluate(self, ctx: EvaluatorContext) -> str:
        calls = (ctx.attributes or {}).get("tool_calls") or []
        return ", ".join(_describe(call) for call in calls) or "none"


def _called(ctx: EvaluatorContext) -> list[str]:
    return [call.get("name", "?") for call in (ctx.attributes or {}).get("tool_calls") or []]


@dataclass(repr=False)
class ToolCalled(Evaluator):
    """Pass when the scored turn called tool `name`."""

    name: str = ""

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        called = _called(ctx)
        passed = self.name in called
        return EvaluationReason(
            value=passed, reason=None if passed else f"called: {', '.join(called) or 'none'}"
        )


@dataclass(repr=False)
class ToolNotCalled(Evaluator):
    """Pass when the scored turn did not call tool `name`."""

    name: str = ""

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        passed = self.name not in _called(ctx)
        return EvaluationReason(value=passed, reason=None if passed else f"{self.name} called")


@dataclass(repr=False)
class SourcesCount(Evaluator):
    """Pass when the scored turn streamed at least `minimum` distinct source URLs."""

    minimum: int = 1

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        found = len(set((ctx.attributes or {}).get("sources") or []))
        passed = found >= self.minimum
        return EvaluationReason(
            value=passed, reason=None if passed else f"{found} sources < {self.minimum}"
        )
