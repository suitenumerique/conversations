"""Span-tree evaluators that match tool calls by tool name, whatever the span schema.

The span name of a tool call depends on pydantic_ai's instrumentation version:
production pins version 2 when Langfuse is enabled, which names every tool span
"running tool", while later versions name it "execute_tool <tool name>". The
tool name attribute is set by every version, so these evaluators match on it,
by regex, so one check can cover a family of tools sharing a name prefix.
"""

import re
from dataclasses import dataclass, field

from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.otel.span_tree import SpanNode, SpanTree

TOOL_NAME_ATTRIBUTE = "gen_ai.tool.name"


def tool_call_spans(span_tree: SpanTree, name_regex: str) -> list[SpanNode]:
    """The spans of the tool calls whose tool name matches ``name_regex``.

    The pattern is searched anywhere in the name, not matched in full: anchor it
    (``^web_search$``) to match a single tool exactly.
    """
    pattern = re.compile(name_regex)

    def is_matching_tool_call(node: SpanNode) -> bool:
        tool_name = node.attributes.get(TOOL_NAME_ATTRIBUTE)
        return isinstance(tool_name, str) and pattern.search(tool_name) is not None

    return span_tree.find(is_matching_tool_call)


class NamedEvaluationMixin:
    """Report under ``evaluation_name`` when the case sets one, else the evaluator name.

    The ``evaluation_name`` field stays on each dataclass: declared here it would
    become the first field, which pydantic_evals uses for the compact one-argument
    YAML form.
    """

    evaluation_name: str | None

    def get_default_evaluation_name(self) -> str:
        """The name this evaluator's result is reported under."""
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()


@dataclass(repr=False)
class CalledTool(NamedEvaluationMixin, Evaluator):
    """Pass when a tool whose name matches ``name_regex`` ran."""

    name_regex: str
    evaluation_name: str | None = field(default=None)

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return bool(tool_call_spans(ctx.span_tree, self.name_regex))


@dataclass(repr=False)
class DidNotCallTool(NamedEvaluationMixin, Evaluator):
    """Pass when no tool whose name matches ``name_regex`` ran."""

    name_regex: str
    evaluation_name: str | None = field(default=None)

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return not tool_call_spans(ctx.span_tree, self.name_regex)

