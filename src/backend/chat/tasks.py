"""Celery tasks for the chat app."""

import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.module_loading import import_string

from chat.agent_rag.indexing import index_project_attachment, parse_and_store_with_retry
from chat.models import ChatConversationAttachment
from conversations.celery_app import app

logger = logging.getLogger(__name__)


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
