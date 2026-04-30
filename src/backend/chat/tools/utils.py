"""Tool calling utilities for the chat agent."""

import functools
import logging
import uuid
from typing import Any, Callable, Iterable

from pydantic_ai import ModelRetry, RunContext

from chat import models
from chat.tools.exceptions import ModelCannotRetry

logger = logging.getLogger(__name__)


def resolve_attachment_by_id(
    attachments: Iterable[models.ChatConversationAttachment],
    document_id: str,
) -> models.ChatConversationAttachment:
    """
    Resolve a model-supplied ``document_id`` string to one of the listed attachments.

    Raises ``ModelRetry`` on invalid UUID or missing attachment so the model can
    correct itself within the tool-retry budget.
    """
    try:
        parsed_document_id = uuid.UUID(document_id)
    except ValueError as exc:
        raise ModelRetry("Invalid document_id. Expected a valid UUID.") from exc

    for attachment in attachments:
        if attachment.id == parsed_document_id:
            return attachment

    raise ModelRetry("document_id was not found among attached text documents.")


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
