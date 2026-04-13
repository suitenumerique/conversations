"""Unit tests for project attachment RAG indexing."""

import logging

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
import responses
from rest_framework import status

from chat import factories
from chat.agent_rag.indexing import index_project_attachment, is_indexable_for_rag

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure Albert backend + parser for the indexing tests."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.RAG_DOCUMENT_PARSER = "chat.agent_rag.document_converter.parser.AlbertParser"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


@pytest.fixture(name="project_text_attachment")
def fixture_project_text_attachment():
    """Real project attachment with content stored in default_storage."""
    saved_name = default_storage.save("project-rag-test.txt", ContentFile(b"Hello project content"))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="hello.txt",
        content_type="text/plain",
    )
    yield attachment
    default_storage.delete(saved_name)


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("text/plain", True),
        ("text/markdown", True),
        ("application/pdf", True),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", True),
        ("image/png", False),
        ("image/jpeg", False),
        ("image/webp", False),
    ],
)
def test_is_indexable_for_rag(content_type, expected):
    """Indexable for RAG covers everything except images."""
    attachment = factories.ChatProjectAttachmentFactory.build(content_type=content_type)
    assert is_indexable_for_rag(attachment) is expected


@responses.activate
def test_index_skips_attachment_without_project():
    """Conversation-scoped attachments are silently skipped."""
    attachment = factories.ChatConversationAttachmentFactory(content_type="text/plain")

    index_project_attachment(attachment)

    assert len(responses.calls) == 0


@responses.activate
def test_index_skips_image_attachment(project_text_attachment):
    """Image attachments are skipped: no HTTP call, no collection created."""
    project_text_attachment.content_type = "image/png"
    project_text_attachment.save(update_fields=["content_type"])

    index_project_attachment(project_text_attachment)

    assert len(responses.calls) == 0
    project_text_attachment.project.refresh_from_db()
    assert project_text_attachment.project.collection_id is None


@responses.activate
def test_index_creates_collection_when_project_has_none(project_text_attachment):
    """First indexable file in a fresh project triggers collection creation."""
    create_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    documents_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    project_text_attachment.project.refresh_from_db()
    project_text_attachment.refresh_from_db()
    assert project_text_attachment.project.collection_id == "42"
    assert project_text_attachment.rag_document_id == "1"
    assert create_mock.call_count == 1
    assert documents_mock.call_count == 1


@responses.activate
def test_index_reuses_existing_project_collection(project_text_attachment):
    """A project that already has a collection_id is not asked to create another."""
    project_text_attachment.project.collection_id = "999"
    project_text_attachment.project.save(update_fields=["collection_id"])

    create_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "should-not-be-called"},
        status=status.HTTP_200_OK,
    )
    documents_mock = responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"id": 1},
        status=status.HTTP_201_CREATED,
    )

    index_project_attachment(project_text_attachment)

    project_text_attachment.project.refresh_from_db()
    assert project_text_attachment.project.collection_id == "999"
    assert create_mock.call_count == 0
    assert documents_mock.call_count == 1


@responses.activate
def test_index_swallows_backend_errors(project_text_attachment, caplog):
    """Backend failures must be logged but never raised."""
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/collections",
        json={"id": "42"},
        status=status.HTTP_200_OK,
    )
    responses.post(
        "https://albert.api.etalab.gouv.fr/v1/documents",
        json={"error": "kaboom"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    caplog.set_level(logging.ERROR, logger="chat.agent_rag.indexing")

    index_project_attachment(project_text_attachment)

    assert any("Failed to index project attachment" in record.message for record in caplog.records)
