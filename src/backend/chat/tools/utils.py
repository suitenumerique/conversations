"""Tool calling utilities for the chat agent."""

import functools
import logging
from typing import Any, Callable

from django.core.files.storage import default_storage

from asgiref.sync import sync_to_async
from pydantic_ai import ModelRetry, RunContext

from chat.tools.exceptions import ModelCannotRetry

logger = logging.getLogger(__name__)


def last_model_retry_soft_fail(
    tool_func: Callable[..., Any],
) -> Callable[..., Any]:
    """
    Wrap a tool function to handle ModelRetry exceptions.

    If the tool function raises ModelRetry and the maximum number of retries
    has been reached, a ModelCannotRetry exception is raised instead.

    Args:
        tool_func: The original tool function to wrap.

    Returns:
        A wrapped tool function with retry handling.
    """

    @functools.wraps(tool_func)
    async def wrapper(ctx: RunContext, *args, **kwargs) -> Any:
        try:
            return await tool_func(ctx, *args, **kwargs)
        except ModelCannotRetry as exc:
            return str(exc.message)
        except ModelRetry as exc:
            logger.error("Tool '%s' raised ModelRetry: %s", ctx, exc.message)
            if (ctx.retries.get(ctx.tool_name, 0) + 1) >= ctx.max_retries:
                logger.error("Max retries reached for tool '%s'.", ctx.tool_name)
                # A bit of a hack to signal that we cannot retry here, while preventing
                # the LLM to generate an outdated answer.
                # We may define a more specific exception later base on ModelRetry which
                # adds a specific message for this case.
                return (
                    f"{exc.message} You must explain this to the user and "
                    "not try to answer based on your knowledge."
                )
            raise  # Re-raise to allow retrying

    return wrapper


@sync_to_async
def read_document_content(doc):
    """Read document content asynchronously."""
    with default_storage.open(doc.key) as f:
        return doc.file_name, f.read().decode("utf-8")
