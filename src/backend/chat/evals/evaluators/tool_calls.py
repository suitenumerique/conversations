"""Span-tree evaluators that match tool calls by tool name, whatever the span schema.

The span name of a tool call depends on pydantic_ai's instrumentation version:
production pins version 2 when Langfuse is enabled, which names every tool span
"running tool", while later versions name it "execute_tool <tool name>". The
tool name attribute is set by every version, so these evaluators match on it,
by regex, which lets a connector's tools be matched by prefix without listing
names the server decides.
"""

import re
from dataclasses import dataclass, field

from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.otel.span_tree import SpanNode, SpanTree

TOOL_NAME_ATTRIBUTE = "gen_ai.tool.name"


def tool_call_spans(span_tree: SpanTree, name_regex: str) -> list[SpanNode]:
    """The spans of the tool calls whose tool name matches ``name_regex``."""
    pattern = re.compile(name_regex)

    def is_matching_tool_call(node: SpanNode) -> bool:
        tool_name = node.attributes.get(TOOL_NAME_ATTRIBUTE)
        return isinstance(tool_name, str) and pattern.search(tool_name) is not None

    return span_tree.find(is_matching_tool_call)


@dataclass(repr=False)
class CalledTool(Evaluator):
    """Pass when a tool whose name matches ``name_regex`` ran."""

    name_regex: str
    evaluation_name: str | None = field(default=None)

    def get_default_evaluation_name(self) -> str:
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return bool(tool_call_spans(ctx.span_tree, self.name_regex))


@dataclass(repr=False)
class DidNotCallTool(Evaluator):
    """Pass when no tool whose name matches ``name_regex`` ran."""

    name_regex: str
    evaluation_name: str | None = field(default=None)

    def get_default_evaluation_name(self) -> str:
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return not tool_call_spans(ctx.span_tree, self.name_regex)


@dataclass(repr=False)
class ToolCalledBefore(Evaluator):
    """Pass unless a tool matching ``then`` started before any tool matching ``first``.

    Passes when ``then`` never matched — there is nothing to order — and fails when
    ``then`` matched but ``first`` never did. Used for a fallback: the connector
    must be consulted before web search, never after it or instead of it.

    Spans are compared by start time. Two tool calls issued in the same model
    response run concurrently, so their order is arbitrary; this evaluator does
    not try to tell that case apart.
    """

    first: str
    then: str
    evaluation_name: str | None = field(default=None)

    def get_default_evaluation_name(self) -> str:
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        then_spans = tool_call_spans(ctx.span_tree, self.then)
        if not then_spans:
            return True
        first_spans = tool_call_spans(ctx.span_tree, self.first)
        if not first_spans:
            return False
        first_start = min(span.start_timestamp for span in first_spans)
        return first_start < min(span.start_timestamp for span in then_spans)
