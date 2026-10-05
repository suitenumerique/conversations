"""Celery tasks for the chat application."""

import io
import time
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from django.utils.module_loading import import_string

import structlog
from asgiref.sync import async_to_sync
from botocore.exceptions import BotoCoreError, ClientError
from celery.exceptions import SoftTimeLimitExceeded
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessagesTypeAdapter

from core.log_fields import safe_error_fields

from chat.agent_rag.indexing import index_project_attachment, parse_and_store_with_retry
from chat.agents.history_processors import (
    generate_history_summary,
    resolve_conversation_budget,
    safe_clean_tool_history,
    should_generate_conversation_summary,
)
from chat.constants import (
    DEINDEX_TASK_SOFT_TIME_LIMIT,
    DEINDEX_TASK_TIME_LIMIT,
    SUMMARIZATION_TASK_SOFT_TIME_LIMIT,
    SUMMARIZATION_TASK_TIME_LIMIT,
    TABULAR_MAX_OUTPUT_CHARS,
    TABULAR_MIME_TYPES,
    TABULAR_QUERY_MAX_ROWS,
    TABULAR_RESULT_WRITE_MARGIN_SECONDS,
    TABULAR_RESULTS_MAX_AGE_SECONDS,
    TABULAR_RESULTS_PREFIX,
    TABULAR_TASK_SOFT_TIME_LIMIT,
    TABULAR_TASK_TIME_LIMIT,
    TEXT_MIME_PREFIX,
)
from chat.llm_configuration import get_model_configuration
from chat.models import AttachmentStatus, ChatConversation, ChatConversationAttachment
from chat.tabular import (
    TableQuery,
    TabularError,
    TabularFile,
    build_dataset,
    cap_output,
    describe_tables,
    run_table_query,
)
from conversations.celery_app import app

logger = structlog.get_logger(__name__)

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
        logger.warning("project_attachment_gone", attachment_id=attachment_id)
        return

    index_project_attachment(attachment)


# Kept unchanged only so workers on this release can still serve web pods from the
# previous release during a rolling deploy. Remove it in the next release.
@app.task
def parse_and_store_conversation_document_task(collection_id, s3_key, name, content_type, user_sub):
    """Deprecated: superseded by `index_conversation_document_task`.

    Returns `(parsed_content, rag_document_id)` through the result backend, which
    puts whole parsed documents in Redis.
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


@app.task
def index_conversation_document_task(collection_id, s3_key, name, content_type, user_sub):
    """Parse a conversation document and store it in the conversation's RAG collection.

    Enqueued by `AIAgentService._parse_input_documents` during a chat turn, which
    blocks on the result. The heavy, hostile-input-exposed work (parsing the file,
    storing chunks in the RAG backend) runs here, off the web worker and under the
    Celery task time limits, so a malformed or malicious file cannot hang or exhaust
    the request process. The caller passes only the storage key; the task reads the
    file bytes itself so nothing large crosses the broker.

    For a non-text input the task also writes the Markdown companion to storage, so
    the parsed content never goes through the result backend either: a large parsed
    document (e.g. a big spreadsheet) written to Redis in one shot can stall it, and
    Celery logs task return values. Returns `(companion_key, rag_document_id)`, with
    `companion_key` None for text inputs; the caller does the DB writes.

    Registered under a different name than `parse_and_store_conversation_document_task`
    because the return value differs: during a rolling deploy, a worker that does not
    know this task rejects it instead of returning a result the caller misreads.
    """
    backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)(collection_id=collection_id)
    with default_storage.open(s3_key, "rb") as file:
        content = file.read()

    parsed_content, rag_document_id = parse_and_store_with_retry(
        backend,
        name=name,
        content_type=content_type,
        content=content,
        user_sub=user_sub,
    )

    companion_key = None
    if not content_type.startswith(TEXT_MIME_PREFIX):
        # A distinct key keeps the original file intact, as the project indexing
        # does (see agent_rag.indexing._write_markdown_companion).
        try:
            companion_key = default_storage.save(
                f"{s3_key}.md", io.BytesIO(parsed_content.encode("utf-8"))
            )
        except Exception:
            # The caller never gets the id if this task fails, so nothing would
            # reference the chunks just stored: remove them before failing.
            if rag_document_id:
                try:
                    backend.delete_document(rag_document_id)
                except Exception:  # pylint: disable=broad-except
                    logger.exception(
                        "rag_document_delete_failed",
                        rag_document_id=rag_document_id,
                        collection_id=collection_id,
                    )
            raise

    return companion_key, rag_document_id


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
        logger.info("history_summary_conversation_gone", conversation_id=conversation_id)
        return

    if not conversation.claim_history_summarization():
        logger.debug("history_summary_already_claimed", conversation_id=conversation_id)
        return

    try:
        model_hrid = conversation.model_hrid or settings.LLM_DEFAULT_MODEL_HRID
        try:
            model_configuration = get_model_configuration(model_hrid)
        except ImproperlyConfigured:
            logger.warning(
                "history_summary_model_not_configured",
                model_hrid=model_hrid,
                conversation_id=conversation_id,
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


@app.task(ignore_result=True)
def fetch_model_health_task(provider):
    """Run `fetch_model_health` for one provider from Celery beat.

    The command takes its own cache lock sized by
    `ModelHealthSettings.poll_interval_minutes`, so a shorter beat interval only
    produces cheap "Skipping" runs. A `CommandError` is logged with its
    traceback, not re-raised: the next tick retries anyway.
    """
    # Celery redirects stdout to the log at WARNING level, and the command
    # prints a "Skipping" line on most ticks; capture it and log at DEBUG instead.
    out = io.StringIO()
    try:
        call_command("fetch_model_health", "--provider", provider, stdout=out)
    except CommandError:
        logger.exception("model_health_fetch_failed", provider=provider)
    finally:
        output = out.getvalue()
        if output:
            logger.debug("model_health_fetch_output", output=output)


@app.task(
    ignore_result=True,
    soft_time_limit=DEINDEX_TASK_SOFT_TIME_LIMIT,
    time_limit=DEINDEX_TASK_TIME_LIMIT,
)
def deindex_inactive_collections_task():
    """Run `deindex_inactive_collections` from Celery beat on a cron schedule."""
    try:
        call_command("deindex_inactive_collections")
    except CommandError:
        logger.exception("deindex_inactive_collections_failed")


def _tabular_output(conversation_id: str, query: dict | None) -> tuple[bool, str]:
    """Load the conversation's spreadsheets, then describe them or run `query`.

    Returns `(ok, content)`; when `ok` is False, `content` is a query error meant
    for the model.
    """
    attachments = ChatConversationAttachment.objects.filter(
        conversation_id=conversation_id,
        content_type__in=TABULAR_MIME_TYPES,
        upload_state=AttachmentStatus.READY,
    ).order_by("created_at", "id")
    files = []
    for attachment in attachments:
        with default_storage.open(attachment.key, "rb") as file:
            files.append(TabularFile(attachment.file_name, attachment.content_type, file.read()))

    dataset = build_dataset(files)
    if query is None:
        return True, describe_tables(dataset)
    try:
        return True, run_table_query(
            dataset,
            TableQuery.model_validate(query),
            TABULAR_QUERY_MAX_ROWS,
            max_join_cells=settings.TABULAR_JOIN_MAX_CELLS,
        )
    except TabularError as exc:
        return False, str(exc)


@app.task(soft_time_limit=TABULAR_TASK_SOFT_TIME_LIMIT, time_limit=TABULAR_TASK_TIME_LIMIT)
def run_tabular_query_task(conversation_id: str, query: dict | None, deadline: float) -> dict:
    """Load the conversation's spreadsheets into DataFrames, then describe them or run `query`.

    Enqueued by the tabular tools, which block on the result. Loading untrusted
    files happens here, off the web worker and under the task time limits.
    Stateless: the files are reloaded on every call. `query` is a `TableQuery`
    dumped to JSON, or None to describe the tables.

    The output (capped in size) is written to storage, never returned: task
    results go through Redis, where a large value can stall it. Returns
    `{"ok": bool, "key": str | None}`; the caller reads the output at `key` and
    deletes it. When `ok` is False the output is an error message meant for the
    model. `deadline` (epoch seconds) is when the caller stops waiting: past it
    nothing is written, as nobody would delete it.

    Without an output, `key` is None and `error` says why: `deadline`,
    `time_limit` (soft time limit hit) or `failed`. The task never raises: a
    raised exception would put its message in Redis and in the Celery failure
    log, and a pandas or parser message can quote cells of the file.
    """
    if time.time() > deadline - TABULAR_RESULT_WRITE_MARGIN_SECONDS:
        return {"ok": False, "key": None, "error": "deadline"}
    try:
        ok, content = _tabular_output(conversation_id, query)
        if time.time() > deadline - TABULAR_RESULT_WRITE_MARGIN_SECONDS:
            return {"ok": False, "key": None, "error": "deadline"}
        key = default_storage.save(
            f"{TABULAR_RESULTS_PREFIX}{uuid4()}.md",
            ContentFile(cap_output(content, TABULAR_MAX_OUTPUT_CHARS).encode("utf-8")),
        )
    except SoftTimeLimitExceeded:
        logger.warning("tabular_query_time_limit")
        return {"ok": False, "key": None, "error": "time_limit"}
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        # Type only: the message and traceback can quote the file's cells.
        logger.error("tabular_query_failed", **safe_error_fields(exc))
        return {"ok": False, "key": None, "error": "failed"}
    return {"ok": ok, "key": key}


@app.task
def purge_tabular_results_task():
    """Delete the tabular outputs nobody will read. Run by Celery beat.

    The tabular tool deletes each output once read, and the task writes none
    after the tool's deadline. An output older than TABULAR_RESULTS_MAX_AGE_SECONDS
    was left by a web process that died between the write and the read. Deleting a
    conversation would not remove it: storage is cleaned by attachment key.
    """
    cutoff = timezone.now() - timedelta(seconds=TABULAR_RESULTS_MAX_AGE_SECONDS)
    _dirs, names = default_storage.listdir(TABULAR_RESULTS_PREFIX)
    deleted = 0
    for name in names:
        key = f"{TABULAR_RESULTS_PREFIX}{name}"
        try:
            if default_storage.get_modified_time(key) < cutoff:
                default_storage.delete(key)
                deleted += 1
        except BotoCoreError, ClientError, OSError:
            # Read and deleted by its tool since the listing, or a storage error:
            # the next run retries.
            continue
    logger.info("tabular_results_purged", deleted=deleted)
