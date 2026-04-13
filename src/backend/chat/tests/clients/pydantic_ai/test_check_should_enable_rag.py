"""Unit tests for AIAgentService._check_should_enable_rag."""
# pylint: disable=protected-access

import pytest
from asgiref.sync import async_to_sync

from core.feature_flags.flags import FeatureToggle
from core.file_upload.enums import AttachmentStatus

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import (
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def base_settings(settings):
    """Minimum LLM settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def _check(conversation, *, conversation_has_documents=False):
    service = AIAgentService(conversation, user=conversation.owner)
    return async_to_sync(service._check_should_enable_rag)(conversation_has_documents)


def test_returns_false_when_feature_disabled(feature_flags):
    """Feature flag short-circuits the check."""
    feature_flags.document_upload = FeatureToggle.DISABLED
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
    )

    assert _check(conversation, conversation_has_documents=False) is False
    assert _check(conversation, conversation_has_documents=True) is False


def test_returns_true_when_conversation_has_documents_arg():
    """Caller-provided in-message-document signal is enough."""
    conversation = ChatConversationFactory()

    assert _check(conversation, conversation_has_documents=True) is True


def test_returns_false_with_no_attachments():
    """No documents anywhere → no RAG."""
    conversation = ChatConversationFactory()

    assert _check(conversation) is False


def test_returns_true_with_conversation_ready_text_attachment():
    """A READY non-image conversation attachment enables RAG."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
    )

    assert _check(conversation) is True


def test_returns_false_with_conversation_ready_image_only():
    """Image-only attachments don't enable the RAG tool."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="image/png",
    )

    assert _check(conversation) is False


def test_returns_false_with_conversation_pending_attachment():
    """Non-READY attachments are ignored - they would be unsearchable."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.PENDING,
        content_type="text/plain",
    )

    assert _check(conversation) is False


def test_returns_false_for_conversion_artifact_only():
    """A markdown conversion artifact alone shouldn't trip the gate."""
    conversation = ChatConversationFactory()
    ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        conversion_from="some/original.pdf",
    )

    assert _check(conversation) is False


def test_returns_true_with_project_ready_text_attachment():
    """A READY non-image project attachment enables RAG for any conversation in the project."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
    )

    assert _check(conversation) is True


def test_returns_false_with_project_ready_image_only():
    """Image-only project attachments don't enable the RAG tool."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="image/jpeg",
    )

    assert _check(conversation) is False


def test_returns_false_with_project_pending_attachment():
    """Non-READY project attachments are ignored."""
    project = ChatProjectFactory()
    conversation = ChatConversationFactory(owner=project.owner, project=project)
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.SUSPICIOUS,
        content_type="text/plain",
    )

    assert _check(conversation) is False


def test_project_attachment_does_not_leak_to_unlinked_conversation():
    """Project attachments must not enable RAG on a conversation that's not in the project."""
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        upload_state=AttachmentStatus.READY,
        content_type="text/plain",
    )
    standalone_conversation = ChatConversationFactory(owner=project.owner)

    assert _check(standalone_conversation) is False
