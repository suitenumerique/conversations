"""Unit tests for AIAgentService._validate_input_documents.

Conversation documents are parsed and indexed on the Celery worker at upload time
(`index_conversation_attachment_task`), so the web process never parses a
document. At message time the service only validates the current message's
documents: inline bytes are rejected (they would need in-process parsing) and
`DocumentUrl`s must point at this conversation's media keys.

The end-to-end error emission of `_handle_input_documents` on a rejection (tool
result + finish + DocumentParsingResult) is covered in
`test_handle_input_documents_indexing.py`.
"""
# pylint: disable=protected-access

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import BinaryContent, DocumentUrl

from chat.clients.pydantic_ai import DOCUMENT_URL_PREFIX, AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Minimum settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


@pytest.mark.asyncio
async def test_validate_rejects_inline_binary_content():
    """Inline document bytes are rejected so the web process never parses them."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    document = BinaryContent(data=b"raw bytes", media_type="text/plain")

    with pytest.raises(ValueError, match="Inline document content is not supported"):
        service._validate_input_documents([document])


@pytest.mark.asyncio
async def test_validate_rejects_external_url():
    """A document URL without the media-key prefix is rejected."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    document = DocumentUrl(
        url="https://external.example.com/file.pdf", media_type="application/pdf"
    )

    with pytest.raises(ValueError, match="External document URL are not accepted yet."):
        service._validate_input_documents([document])


@pytest.mark.asyncio
async def test_validate_rejects_cross_conversation_url():
    """A media-key URL belonging to another conversation is rejected."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    document = DocumentUrl(
        url=f"{DOCUMENT_URL_PREFIX}other-conversation/attachments/file.txt",
        media_type="text/plain",
    )

    with pytest.raises(ValueError, match="Document URL does not belong to the conversation."):
        service._validate_input_documents([document])


@pytest.mark.asyncio
async def test_validate_accepts_own_document_url():
    """A media-key URL under this conversation passes validation (no parsing)."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    document = DocumentUrl(
        url=f"{DOCUMENT_URL_PREFIX}{conversation.pk}/attachments/file.txt",
        media_type="text/plain",
    )

    # Must not raise.
    service._validate_input_documents([document])
