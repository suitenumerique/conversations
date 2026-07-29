"""Celery tasks for the chat application."""

import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

from asgiref.sync import async_to_sync
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessagesTypeAdapter

from chat.agent_rag.indexing import index_project_attachment, parse_and_store_with_retry
from chat.agents.history_processors import (
    generate_history_summary,
    resolve_conversation_budget,
    safe_clean_tool_history,
    should_generate_conversation_summary,
)
from chat.constants import (
    SUMMARIZATION_TASK_SOFT_TIME_LIMIT,
    SUMMARIZATION_TASK_TIME_LIMIT,
)
from chat.llm_configuration import get_model_configuration
from chat.models import ChatConversation, ChatConversationAttachment
from conversations.celery_app import app

logger = logging.getLogger(__name__)

# Transient provider failures worth retrying: every model-provider API error
# (HTTP 4xx/5xx, connection and timeout errors) raised by the summarization
# agent. Deterministic failures (empty output -> SummarizationRequiredError,
# application bugs) fall through and fail fast; the claim is released either way
# and the budget re-check makes stale retries no-ops. Note 4xx is not singled
# out here, so a bad-request/auth error would still retry (a known trade-off).
RETRYABLE_SUMMARIZATION_ERRORS = (ModelAPIError,)


@app.task(ignore_result=True)
def index_project_attachment_task(attachment_id):
    """Parse and index a project attachment into its RAG collection.

    Enqueued by the malware safe-callback once the file is marked READY. The
    heavy work (parsing, backend store) is moved off the request/callback path
    onto a worker. `index_project_attachment` is idempotent and records its own
    outcome on the attachment (`index_state` / `processing_error`), so this
    wrapper only resolves the id and delegates; missing rows (already deleted)
    are ignored.

    Fire-and-forget: callers never await the result and the outcome is recorded
    on the attachment row, so `ignore_result` keeps this task from writing a
    useless `celery-task-meta-*` tombstone into the result backend.
    """
    attachment = (
        ChatConversationAttachment.objects.select_related("project", "uploaded_by")
        .filter(pk=attachment_id)
        .first()
    )
    if attachment is None:
        logger.warning(
            "index_project_attachment_task: attachment %s no longer exists; skipping.",
            attachment_id,
        )
        return

    index_project_attachment(attachment)


@app.task
def parse_and_store_conversation_document_task(collection_id, s3_key, name, content_type, user_sub):
    """Parse a conversation document and store it in the conversation's RAG collection.

    Enqueued by `AIAgentService._parse_input_documents` during a chat turn, which
    blocks on the result. The heavy, hostile-input-exposed work (parsing the file,
    storing chunks in the RAG backend) runs here, off the web worker and under the
    Celery task time limits, so a malformed or malicious file cannot hang or exhaust
    the request process. The caller passes only the storage key; the task reads the
    file bytes itself so nothing large crosses the broker. Returns
    `(parsed_content, rag_document_id)`; the caller does the DB and companion writes.
    """
    backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)(collection_id=collection_id)
    with default_storage.open(s3_key, "rb") as file:
        content = file.read()

    return parse_and_store_with_retry(
        backend,
        name=name,
        content_type=content_type,
        content=content,
        user_sub=user_sub,
    )


@app.task(
    autoretry_for=RETRYABLE_SUMMARIZATION_ERRORS,
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=SUMMARIZATION_TASK_SOFT_TIME_LIMIT,
    time_limit=SUMMARIZATION_TASK_TIME_LIMIT,
)
def summarize_conversation_history(conversation_id: str) -> None:
    """Generate the running summary for a conversation's history.

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

        budget = resolve_conversation_budget(model_configuration)
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
