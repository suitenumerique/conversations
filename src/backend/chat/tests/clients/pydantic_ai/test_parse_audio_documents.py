"""Test that audio documents use pre-stored transcript in RAG pipeline."""

# pylint: disable=protected-access
import asyncio
from unittest import mock

from django.core.files.storage import default_storage

import pytest
from pydantic_ai.messages import DocumentUrl

from core.file_upload.enums import AttachmentStatus

from chat import models as chat_models
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(name="conversation")
def fixture_conversation():
    """Create a conversation."""
    return ChatConversationFactory()


TRANSCRIPT_CONTENT = "# Transcription \n\n## SPEAKER_00\n Hello world\n"


@pytest.fixture(name="audio_attachment")
def fixture_audio_attachment(conversation):
    """Create a READY audio attachment."""
    return ChatConversationAttachmentFactory(
        conversation=conversation,
        content_type="application/ogg",
        upload_state=AttachmentStatus.READY,
    )


@pytest.fixture(name="transcript_attachment")
def fixture_transcript_attachment(conversation, audio_attachment):
    """Create the text/markdown transcript attachment produced by the webhook."""
    return ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=audio_attachment.uploaded_by,
        key=f"{conversation.pk}/attachments/{audio_attachment.file_name}.md",
        file_name=f"{audio_attachment.file_name}.md",
        content_type="text/markdown",
        conversion_from=audio_attachment.key,
        upload_state=AttachmentStatus.READY,
    )


def test_audio_document_uses_transcript_not_parse_document(
    conversation, audio_attachment, transcript_attachment
):  # pylint: disable=unused-argument
    """Audio DocumentUrl uses transcript from S3, not parse_document()."""

    mock_store = mock.MagicMock()
    mock_store.collection_id = "test-collection"
    mock_store.astore_document = mock.AsyncMock(return_value=None)
    mock_store.parse_and_store_document = mock.MagicMock(return_value="")

    document = DocumentUrl(
        url=f"/media-key/{audio_attachment.key}",
        media_type="application/ogg",
        identifier=audio_attachment.file_name,
    )

    async def run():
        svc = AIAgentService.__new__(AIAgentService)
        svc.conversation = conversation
        svc.user = audio_attachment.uploaded_by
        svc._is_document_upload_enabled = True
        svc._audio_document_names = []

        with (
            mock.patch("chat.clients.pydantic_ai.document_store_backend", return_value=mock_store),
            mock.patch.object(
                default_storage,
                "open",
                return_value=mock.mock_open(read_data=TRANSCRIPT_CONTENT.encode())(),
            ),
        ):
            await svc._parse_input_documents([document])

    asyncio.run(run())

    mock_store.parse_and_store_document.assert_not_called()
    mock_store.astore_document.assert_called_once()
    # Verify transcript content was passed
    call_kwargs = mock_store.astore_document.call_args
    content = call_kwargs.kwargs.get("content") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else ""
    )
    assert "# Transcription" in content


def test_audio_document_transcription_failed_raises_error(conversation, audio_attachment):
    """When upload_state is TRANSCRIPTION_FAILED, a user-friendly ValueError is raised."""
    audio_attachment.upload_state = AttachmentStatus.TRANSCRIPTION_FAILED
    audio_attachment.save()

    mock_store = mock.MagicMock()
    mock_store.collection_id = "test-collection"

    document = DocumentUrl(
        url=f"/media-key/{audio_attachment.key}",
        media_type="application/ogg",
        identifier=audio_attachment.file_name,
    )

    error_raised = None

    async def run():
        nonlocal error_raised
        svc = AIAgentService.__new__(AIAgentService)
        svc.conversation = conversation
        svc.user = audio_attachment.uploaded_by
        svc._is_document_upload_enabled = True

        with mock.patch("chat.clients.pydantic_ai.document_store_backend", return_value=mock_store):
            try:
                await svc._parse_input_documents([document])
            except ValueError as exc:
                error_raised = exc

    asyncio.run(run())

    assert error_raised is not None
    assert "transcription" in str(error_raised).lower()
    mock_store.astore_document.assert_not_called()


def test_audio_document_transcript_attachment_created_by_webhook(
    conversation, audio_attachment, transcript_attachment
):  # pylint: disable=unused-argument
    """The webhook creates a text/markdown attachment; _parse_input_documents reads it via RAG."""
    mock_store = mock.MagicMock()
    mock_store.collection_id = "test-collection"
    mock_store.astore_document = mock.AsyncMock(return_value=None)

    document = DocumentUrl(
        url=f"/media-key/{audio_attachment.key}",
        media_type="application/ogg",
        identifier=audio_attachment.file_name,
    )

    async def run():
        svc = AIAgentService.__new__(AIAgentService)
        svc.conversation = conversation
        svc.user = audio_attachment.uploaded_by
        svc._is_document_upload_enabled = True
        svc._audio_document_names = []

        with (
            mock.patch("chat.clients.pydantic_ai.document_store_backend", return_value=mock_store),
            mock.patch.object(
                default_storage,
                "open",
                return_value=mock.mock_open(read_data=TRANSCRIPT_CONTENT.encode())(),
            ),
        ):
            await svc._parse_input_documents([document])

    asyncio.run(run())
    assert (
        chat_models.ChatConversationAttachment.objects.filter(
            conversation=conversation,
            conversion_from=audio_attachment.key,
        ).count()
        == 1
    )
    mock_store.astore_document.assert_called_once()
