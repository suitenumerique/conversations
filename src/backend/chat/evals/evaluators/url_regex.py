"""Regex-based evaluator: flags any URL in the response not
present in the tool output or user message."""

import re
from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.evaluators.evaluator import EvaluationReason

_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,!?;:*_`~|"


def _extract_urls(text: str) -> set[str]:
    return {url.rstrip(_TRAILING_PUNCT) for url in _URL_RE.findall(text)}


@dataclass(repr=False)
class UrlRegexEvaluator(Evaluator):
    """Pass when the response contains no URLs outside those
    found in tool_output or user_message."""

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        response_urls = _extract_urls(ctx.output)

        tool_output = (
            ctx.inputs.tool_output
            if hasattr(ctx.inputs, "tool_output")
            else (ctx.inputs or {}).get("tool_output")
        )
        user_message = (
            ctx.inputs.user_message
            if hasattr(ctx.inputs, "user_message")
            else (ctx.inputs or {}).get("user_message", "")
        )
        # Tool returns captured at runtime (set_eval_attribute in the task fn).
        runtime_tool_output = (ctx.attributes or {}).get("tool_output")
        allowed_urls = _extract_urls(tool_output) if isinstance(tool_output, str) else set()
        allowed_urls |= (
            _extract_urls(runtime_tool_output) if isinstance(runtime_tool_output, str) else set()
        )
        allowed_urls |= _extract_urls(user_message) if isinstance(user_message, str) else set()

        hallucinated = response_urls - allowed_urls
        if hallucinated:
            return EvaluationReason(
                value=False,
                reason=f"URLs not from tool_output/user_message: {', '.join(sorted(hallucinated))}",
            )
        return EvaluationReason(value=True, reason=None)
