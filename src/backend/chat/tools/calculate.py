"""Arithmetic tool: the model writes the expression, chat.calculator computes it."""

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from chat.calculator import CalculationError, calculate
from chat.tools.utils import last_model_retry_soft_fail


@last_model_retry_soft_fail
async def calculate_expression(_ctx: RunContext, expression: str) -> str:
    """Compute an arithmetic expression exactly.

    Args:
        expression (str): e.g. "round((1250.40 - 980) / 980 * 100, 1)".
    """
    try:
        normalized, result = calculate(expression)
    except CalculationError as exc:
        raise ModelRetry(str(exc)) from exc
    return f"{normalized} = {result}"
