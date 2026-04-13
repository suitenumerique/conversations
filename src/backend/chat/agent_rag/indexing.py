"""RAG indexing helpers for project-level attachments.

Project attachments are indexed proactively when the malware scan completes,
so the conversation agent can search across project files via the document
RAG tool without paying parsing cost at query time.
"""

import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.module_loading import import_string

from chat import models
from chat.constants import IMAGE_MIME_PREFIX

logger = logging.getLogger(__name__)


def is_indexable_for_rag(attachment: models.ChatConversationAttachment) -> bool:
    """Whether this attachment should be added to the project RAG collection."""
    return not attachment.content_type.startswith(IMAGE_MIME_PREFIX)


def _ensure_project_collection_id(project: models.ChatProject, document_store) -> str:
    """Return the project's RAG collection id, creating one on first use.

    Concurrent first-upload callbacks could otherwise both call create_collection
    on the backend, then race on save - leaving one backend collection orphaned.
    Serialize via SELECT FOR UPDATE on the project row.
    """
    # Fast path: once set, collection_id never reverts, so most calls skip the lock.
    if project.collection_id:
        return project.collection_id

    with transaction.atomic():
        # Row-level lock; concurrent callers block here until the holder commits.
        locked = models.ChatProject.objects.select_for_update().get(pk=project.pk)
        # Re-check under the lock: a previous winner may have already created one.
        if locked.collection_id:
            project.collection_id = locked.collection_id
            return locked.collection_id

        # Backend HTTP call runs while the lock is held, so a second
        # caller waiting at SELECT FOR UPDATE sees the committed id and skips create.
        collection_id = str(document_store.create_collection(name=f"project-{project.pk}"))
        project.collection_id = collection_id
        project.save(update_fields=["collection_id", "updated_at"])
        return collection_id


def index_project_attachment(attachment: models.ChatConversationAttachment) -> None:
    """Parse the attachment and store it in the project's RAG collection.

    Failures are logged but never raised - the upload itself remains valid even
    if indexing fails (the file just won't be searchable until a future re-index).

    The backend's per-document id (when available) is persisted on the attachment
    so the document can be removed from the collection on attachment delete.
    """
    if attachment.project_id is None:
        return
    if not is_indexable_for_rag(attachment):
        return

    try:
        backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
        document_store = backend_class()
        collection_id = _ensure_project_collection_id(attachment.project, document_store)
        document_store.collection_id = collection_id

        with default_storage.open(attachment.key, "rb") as file:
            content = file.read()

        document_id, _ = document_store.parse_and_store_document(
            name=attachment.file_name,
            content_type=attachment.content_type,
            content=content,
            user_sub=attachment.uploaded_by.sub,
        )
        if document_id is not None:
            attachment.rag_document_id = document_id
            attachment.save(update_fields=["rag_document_id", "updated_at"])
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to index project attachment %s into RAG collection",
            attachment.pk,
        )
