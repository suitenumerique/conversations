"""Span-tree evaluators for tool-call behavioural evals."""

from dataclasses import dataclass, field

from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.otel import SpanQuery


@dataclass(repr=False)
class HasNoMatchingSpan(Evaluator):
    """Pass when no span in the tree matches the query.

    Use this instead of ``HasMatchingSpan`` with ``not_`` — that inverts per-node
    matching, so ``any(not_(tool))`` is true for every non-tool span (chat, case…)
    and always passes even when the tool ran.
    """

    query: SpanQuery
    evaluation_name: str | None = field(default=None)

    def get_default_evaluation_name(self) -> str:
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return not ctx.span_tree.any(self.query)
