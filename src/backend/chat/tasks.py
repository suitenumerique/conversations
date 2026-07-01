"""Celery tasks for the chat app."""

import logging

from chat.agent_rag.indexing import index_conversation_attachment, index_project_attachment
from chat.models import ChatConversationAttachment
from conversations.celery_app import app

logger = logging.getLogger(__name__)


@app.task
def index_project_attachment_task(attachment_id):
    """Parse and index a project attachment into its RAG collection.

    Enqueued by the malware safe-callback once the file is marked READY. The
    heavy work (parsing, backend store) is moved off the request/callback path
    onto a worker. `index_project_attachment` is idempotent and records its own
    outcome on the attachment (`index_state` / `processing_error`), so this
    wrapper only resolves the id and delegates; missing rows (already deleted)
    are ignored.
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
def index_conversation_attachment_task(attachment_id):
    """Parse and index a conversation attachment into its RAG collection.

    Conversation equivalent of `index_project_attachment_task`. Moves the parse +
    backend store off the Django web process (where it used to run at message
    time in `_parse_input_documents`) onto a worker, keeping the parser out of
    the process that holds the LLM/S3/DB/OIDC secrets. `index_conversation_attachment`
    is idempotent and records its own outcome on the attachment, so this wrapper
    only resolves the id and delegates; missing rows (already deleted) are ignored.
    """
    attachment = (
        ChatConversationAttachment.objects.select_related("conversation", "uploaded_by")
        .filter(pk=attachment_id)
        .first()
    )
    if attachment is None:
        logger.warning(
            "index_conversation_attachment_task: attachment %s no longer exists; skipping.",
            attachment_id,
        )
        return

    index_conversation_attachment(attachment)
