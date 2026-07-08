"""Tests for chat Celery tasks.

Celery runs eagerly in the test settings (`CELERY_TASK_ALWAYS_EAGER`), so
`.delay()` executes the task synchronously in-process.
"""

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
import responses
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat import factories
from chat.enums import AttachmentIndexState
from chat.tasks import (
    index_project_attachment_task,
    parse_and_store_conversation_document_task,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure Albert backend + parser for the task tests."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.RAG_DOCUMENT_PARSER = "chat.agent_rag.document_converter.parser.AlbertParser"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


@responses.activate
def test_index_project_attachment_task_indexes_attachment():
    """The task resolves the id and indexes the file into the project collection."""
    saved_name = default_storage.save("task-rag-test.txt", ContentFile(b"Hello task content"))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="hello.txt",
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
    )
    try:
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/collections",
            json={"id": "42"},
            status=status.HTTP_200_OK,
        )
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/documents",
            json={"id": 1},
            status=status.HTTP_201_CREATED,
        )

        index_project_attachment_task.delay(attachment.pk)

        attachment.refresh_from_db()
        assert attachment.rag_document_id == "1"
        assert attachment.index_state == AttachmentIndexState.INDEXED
    finally:
        default_storage.delete(saved_name)


def test_index_project_attachment_task_ignores_missing_attachment():
    """A deleted attachment id is logged and skipped, never raised."""
    index_project_attachment_task.delay(999999)


@responses.activate
def test_parse_and_store_conversation_document_task_returns_parsed_and_id():
    """The task reads the file from storage, parses + stores it, and returns (content, id)."""
    saved_name = default_storage.save(
        "conv-task-test.txt", ContentFile(b"Hello conversation content")
    )
    try:
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/documents",
            json={"id": 7},
            status=status.HTTP_201_CREATED,
        )

        parsed_content, rag_document_id = parse_and_store_conversation_document_task.delay(
            "42",
            saved_name,
            "hello.txt",
            "text/plain",
            "user-sub-123",
        ).get()

        assert rag_document_id == "7"
        assert "Hello conversation content" in parsed_content
    finally:
        default_storage.delete(saved_name)
