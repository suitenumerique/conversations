"""Tool calling utilities for the chat agent."""

import functools
import uuid
from typing import Any, Callable, Iterable

import structlog
from pydantic import ValidationError
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.exceptions import ModelHTTPError, ToolFailed
from pydantic_ai.messages import ToolCallPart

from chat import models
from chat.tools.exceptions import ModelCannotRetry, UserContentModelRetry

logger = structlog.get_logger(__name__)


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
            # A user-content message would put the user's data in the logs
            reason = None if isinstance(exc, UserContentModelRetry) else exc.message
            logger.warning("tool_retry_requested", tool_name=ctx.tool_name, reason=reason)
            if (ctx.retries.get(ctx.tool_name, 0) + 1) >= ctx.max_retries:
                # Only the cause's type and status: its message can carry urls or user content
                cause = exc.__cause__
                logger.error(
                    "tool_max_retries_reached",
                    tool_name=ctx.tool_name,
                    cause=type(cause).__name__ if cause else None,
                    status_code=cause.status_code if isinstance(cause, ModelHTTPError) else None,
                )
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


def soft_fail_last_invalid_tool_call(
    ctx: RunContext,
    *,
    call: ToolCallPart,
    error: ValidationError | ModelRetry,
    **_kwargs,
) -> Any:
    """`on_tool_validate_error` hook: on a tool's last try, report invalid arguments.

    pydantic-ai checks the arguments before calling the tool, so
    `last_model_retry_soft_fail` never sees these failures. Once the retries are
    used up it raises UnexpectedModelBehavior and the turn ends with an error,
    e.g. when the model keeps asking query_table for an operation it does not
    offer. On the last try this hands the model a failed tool result instead.
    """
    if (ctx.retries.get(call.tool_name, 0) + 1) < ctx.max_retries:
        raise error
    # The type only: the error quotes the model's arguments, which can carry user content
    logger.error(
        "tool_max_retries_reached",
        tool_name=call.tool_name,
        cause=type(error).__name__,
        status_code=None,
    )
    raise ToolFailed(
        f"The {call.tool_name} tool could not be called with valid arguments. The request "
        "probably needs something this tool cannot do. You must explain this to the user "
        "and not try to answer based on your knowledge."
    )
