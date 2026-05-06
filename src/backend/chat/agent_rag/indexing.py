"""Index project attachments into the RAG backend.

Runs synchronously inside the malware safe-callback, after the file is marked
READY. This is the project equivalent of `_parse_input_documents` for
conversation files: same parser, same backend, same hidden markdown companion
attachment for non-text inputs. Differences from the conversation flow:

- Triggered at upload time (one-shot per file), not on every chat turn.
- Lazily creates the project's RAG collection the first time an indexable file
  lands, under `select_for_update` so concurrent uploads on a fresh project
  don't create competing collections.
- Idempotent: a non-empty `rag_document_id` on the attachment is treated as
  "already indexed" and the call returns without re-parsing. This makes the
  function safe to invoke from a malware backend that retries safe-callbacks.
- Failures are logged and swallowed: the file stays `READY` and downloadable
  but won't surface in RAG search until a future re-index.
"""

import logging
from io import BytesIO

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.module_loading import import_string

from core.file_upload.enums import AttachmentStatus

from chat.constants import IMAGE_MIME_PREFIX, TEXT_MIME_PREFIX
from chat.models import ChatConversationAttachment, ChatProject

logger = logging.getLogger(__name__)


def is_indexable_for_rag(attachment: ChatConversationAttachment) -> bool:
    """Return True if the attachment should be indexed in the RAG backend."""
    if attachment.upload_state != AttachmentStatus.READY:
        return False
    if not attachment.content_type:
        return False
    if attachment.content_type.startswith(IMAGE_MIME_PREFIX):
        return False
    if attachment.conversion_from:
        # Hidden markdown companion produced by an earlier index pass; the
        # original carries the RAG document id, the companion is just a
        # parsed-content cache for inlining/summarize.
        return False
    return True


def _ensure_project_collection(project: ChatProject):
    """Return a backend bound to the project's collection, creating it if needed.

    Creation is serialized via `select_for_update` on the project row so two
    concurrent first-uploads on an empty project can't each create a collection
    and orphan one of them at the backend.
    """
    backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

    with transaction.atomic():
        locked = ChatProject.objects.select_for_update().get(pk=project.pk)
        if not locked.collection_id:
            creator = backend_class()
            creator.create_collection(name=f"project-{locked.pk}")
            locked.collection_id = str(creator.collection_id)
            locked.save(update_fields=["collection_id", "updated_at"])
        collection_id = locked.collection_id

    return backend_class(collection_id=collection_id)


def index_project_attachment(attachment: ChatConversationAttachment) -> None:
    """Parse the attachment and store it in the project's RAG collection.

    Mirrors the conversation indexing path in `pydantic_ai._parse_input_documents`:
    text inputs go straight to the backend, non-text inputs additionally get a
    hidden `text/markdown` companion attachment so downstream code (system-prompt
    listing, summarize) can read parsed content from object storage. The
    backend-side document id (Albert) is recorded on the original attachment
    for later targeted search and per-document deletion.

    Failures are logged and never raised: the attachment stays `READY` and the
    user sees no error. Future iteration should surface a visible failure
    status (e.g. AttachmentStatus.INDEXING_FAILED) and a retry endpoint.
    """
    if not is_indexable_for_rag(attachment):
        logger.info(
            "Skipping RAG indexing for project attachment %s (state=%s, type=%s, "
            "conversion_from=%s)",
            attachment.pk,
            attachment.upload_state,
            attachment.content_type,
            attachment.conversion_from,
        )
        return

    if attachment.rag_document_id:
        logger.info(
            "Project attachment %s already indexed (rag_document_id=%s); skipping.",
            attachment.pk,
            attachment.rag_document_id,
        )
        return

    if not attachment.project_id:
        logger.error("Project attachment %s has no project_id; cannot index.", attachment.pk)
        return

    project = attachment.project

    # TODO(projects-files): swap the bare except below for a visible
    # AttachmentStatus.INDEXING_FAILED + retry endpoint.
    try:
        backend = _ensure_project_collection(project)

        with default_storage.open(attachment.key, "rb") as file:
            document_data = file.read()

        parsed_content, rag_document_id = backend.parse_and_store_document(
            name=attachment.file_name,
            content_type=attachment.content_type,
            content=document_data,
            user_sub=attachment.uploaded_by.sub,
        )

        # Persist the backend id BEFORE the companion side-effects below: the
        # chunks already exist in the RAG backend, so any later failure (S3
        # save, companion row create) must not leave us re-indexing on retry
        # and duplicating chunks. The early-return guard above keys off this
        # field.
        if rag_document_id:
            attachment.rag_document_id = rag_document_id
            attachment.save(update_fields=["rag_document_id", "updated_at"])

        # Create the hidden markdown companion for non-text inputs so summarize
        # and the system-prompt listing can read parsed content from S3 the
        # same way they do for conversation attachments. The companion is
        # written to a distinct S3 key (suffixed with `.md`) so the original
        # binary stays intact for direct retrieval and the row's `key` matches
        # the actual blob even on storages that do not overwrite same-name
        # uploads (`AWS_S3_FILE_OVERWRITE=False`). `default_storage.save`
        # returns the actual stored name, which we record on the row.
        if not attachment.content_type.startswith(TEXT_MIME_PREFIX):
            stored_key = default_storage.save(
                f"{attachment.key}.md", BytesIO(parsed_content.encode("utf-8"))
            )
            ChatConversationAttachment.objects.create(
                project=project,
                uploaded_by=attachment.uploaded_by,
                key=stored_key,
                file_name=f"{attachment.file_name}.md",
                content_type="text/markdown",
                conversion_from=attachment.key,
                upload_state=AttachmentStatus.READY,
            )

        logger.info(
            "Indexed project attachment %s (rag_document_id=%s, project=%s).",
            attachment.pk,
            rag_document_id,
            project.pk,
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to index project attachment %s in project %s",
            attachment.pk,
            project.pk,
        )
