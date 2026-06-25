"""Celery tasks for the chat app."""

import logging

from chat.agent_rag.indexing import index_project_attachment
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
