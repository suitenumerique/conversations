"""Evaluators for behavioral evals on ConversationAgent."""

from .span import HasNoMatchingSpan
from .text_checks import (
    EndsWith,
    ExactBullets,
    FactRecall,
    HasMarkdownTable,
    Language,
    MaxItems,
    MaxWords,
    MustNotMatch,
    Regex,
    StartsWith,
    ValidJson,
)
from .tools_used import SourcesCount, ToolCalled, ToolNotCalled, ToolsUsed
from .url_regex import UrlCount, UrlRegexEvaluator

# Every custom evaluator a dataset YAML may reference (pydantic_evals registers
# its built-ins, e.g. LLMJudge and HasMatchingSpan, itself).
CUSTOM_EVALUATOR_TYPES = (
    EndsWith,
    ExactBullets,
    FactRecall,
    HasMarkdownTable,
    HasNoMatchingSpan,
    Language,
    MaxItems,
    MaxWords,
    MustNotMatch,
    Regex,
    SourcesCount,
    StartsWith,
    ToolCalled,
    ToolNotCalled,
    ToolsUsed,
    UrlCount,
    UrlRegexEvaluator,
    ValidJson,
)

__all__ = [
    "CUSTOM_EVALUATOR_TYPES",
    "EndsWith",
    "ExactBullets",
    "FactRecall",
    "HasMarkdownTable",
    "HasNoMatchingSpan",
    "Language",
    "MaxItems",
    "MaxWords",
    "MustNotMatch",
    "Regex",
    "SourcesCount",
    "StartsWith",
    "ToolCalled",
    "ToolNotCalled",
    "ToolsUsed",
    "UrlCount",
    "UrlRegexEvaluator",
    "ValidJson",
]
