"""Unit tests for AIAgentService._parse_input_documents and _fetch_document_data."""
# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import BinaryContent, DocumentUrl

from chat.clients.pydantic_ai import DOCUMENT_URL_PREFIX, AIAgentService
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)


def _mock_backend(rag_document_id):
    """Return a mock backend class whose store returns the given rag_document_id."""
    store = MagicMock()
    store.collection_id = "col-existing"
    store.parse_and_store_document.return_value = ("parsed content", rag_document_id)
    return MagicMock(return_value=store)


@pytest.mark.asyncio
async def test_index_state_set_to_indexed_when_rag_document_id_returned():
    """index_state is saved as INDEXED when at least one document is successfully indexed."""
    conversation = await sync_to_async(ChatConversationFactory)(collection_id="col-1")
    service = AIAgentService(conversation, user=conversation.owner)

    document = BinaryContent(data=b"hello world", media_type="text/plain")
    with patch("chat.clients.pydantic_ai.document_store_backend", _mock_backend("doc-42")):
        await service._parse_input_documents([document])

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXED


@pytest.mark.asyncio
async def test_index_state_not_saved_when_rag_document_id_is_none():
    """index_state must not change when parse_and_store_document returns no rag_document_id."""
    conversation = await sync_to_async(ChatConversationFactory)(
        collection_id="col-1",
        index_state=CollectionIndexState.DEINDEXED,
    )
    service = AIAgentService(conversation, user=conversation.owner)

    document = BinaryContent(data=b"hello world", media_type="text/plain")
    with patch("chat.clients.pydantic_ai.document_store_backend", _mock_backend(None)):
        await service._parse_input_documents([document])

    await conversation.arefresh_from_db()
    assert conversation.index_state == CollectionIndexState.DEINDEXED


@pytest.mark.asyncio
async def test_fetch_document_data_returns_none_key_for_binary_content():
    """BinaryContent → key=None, data passed through unchanged."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    document = BinaryContent(data=b"raw bytes", media_type="text/plain")

    key, content = await service._fetch_document_data(document)

    assert key is None
    assert content == b"raw bytes"


@pytest.mark.asyncio
async def test_fetch_document_data_returns_key_and_bytes_for_document_url():
    """DocumentUrl → key extracted from URL, bytes read from storage."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)

    storage_key = f"{conversation.pk}/attachments/file.txt"
    await sync_to_async(default_storage.save)(storage_key, ContentFile(b"file content"))

    url = f"{DOCUMENT_URL_PREFIX}{storage_key}"
    document = DocumentUrl(url=url, media_type="text/plain")

    key, content = await service._fetch_document_data(document)

    assert key == storage_key
    assert content == b"file content"


@pytest.mark.asyncio
async def test_fetch_document_data_raises_for_external_url():
    """DocumentUrl with an external URL raises ValueError."""
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    document = DocumentUrl(
        url="https://external.example.com/file.pdf", media_type="application/pdf"
    )

    with pytest.raises(ValueError, match="External document URL are not accepted yet."):
        await service._fetch_document_data(document)
