"""Celery tasks for the chat application."""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from asgiref.sync import async_to_sync
from pydantic_ai.messages import ModelMessagesTypeAdapter

from chat.agents.history_processors import (
    generate_history_summary,
    safe_clean_tool_history,
    should_generate_conversation_summary,
)
from chat.constants import (
    SUMMARIZATION_TASK_SOFT_TIME_LIMIT,
    SUMMARIZATION_TASK_TIME_LIMIT,
)
from chat.llm_configuration import conversation_message_token_budget
from chat.models import ChatConversation
from conversations.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=SUMMARIZATION_TASK_SOFT_TIME_LIMIT,
    time_limit=SUMMARIZATION_TASK_TIME_LIMIT,
)
def summarize_conversation_history(conversation_id: str) -> None:
    """Generate the running summary for a conversation's history (see ADR 0002).

    Enqueued by the over-budget turn, which waits on the claim. Claims the
    conversation, re-checks the budget against current DB state, generates,
    and persists behind the checkpoint guard. The claim is always released:
    a retry re-claims, and the re-check makes stale retries no-ops.
    """
    try:
        conversation = ChatConversation.objects.get(pk=conversation_id)
    except ChatConversation.DoesNotExist:
        logger.info("Conversation %s gone before summarization ran.", conversation_id)
        return

    if not conversation.claim_history_summarization():
        logger.debug("Conversation %s already claimed, skipping.", conversation_id)
        return

    try:
        # Late import: pydantic_ai imports chat.tasks (enqueue), avoid the cycle.
        from chat.clients.pydantic_ai import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            get_model_configuration,
        )

        model_hrid = conversation.model_hrid or settings.LLM_DEFAULT_MODEL_HRID
        try:
            model_configuration = get_model_configuration(model_hrid)
        except ImproperlyConfigured:
            logger.warning(
                "Model %s no longer configured, skipping summarization for %s.",
                model_hrid,
                conversation_id,
            )
            return

        budget = conversation_message_token_budget(model_configuration)
        if budget <= 0:
            return

        messages = ModelMessagesTypeAdapter.validate_python(conversation.pydantic_messages)
        if not should_generate_conversation_summary(
            messages,
            summary_checkpoint=conversation.history_summary_checkpoint,
            message_token_budget=budget,
            context_messages=settings.CONVERSATION_SUMMARY_CONTEXT_MESSAGES,
        ):
            return

        cleaned = safe_clean_tool_history(messages)
        summary, checkpoint = async_to_sync(generate_history_summary)(
            cleaned,
            previous_summary=conversation.history_summary.strip() or None,
            summary_checkpoint=conversation.history_summary_checkpoint,
            summary_max_tokens=settings.CONVERSATION_SUMMARY_MAX_TOKENS,
        )
        conversation.persist_history_summary(summary, checkpoint)
    finally:
        conversation.release_history_summarization_claim()
