"""Tests for the Albert RAG document search API."""
# pylint: disable=protected-access

from io import BytesIO
from unittest.mock import patch

import pytest
import responses
from requests import HTTPError

from chat.agent_rag.document_search.albert_api import AlbertRagDocumentSearch
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()


def test_albert_collection_id_property():
    """Test the _albert_collection_id property."""
    conversation = ChatConversationFactory()
    assert (
        AlbertRagDocumentSearch(conversation)._albert_collection_id
        == f"conversation-{conversation.pk}"
    )


def test_collection_id_property():
    """Test the collection_id property."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)

    # When collection_id is None
    conversation.collection_id = None
    assert search.collection_id is None

    # When collection_id is set
    conversation.collection_id = "123"
    assert search.collection_id == 123


@responses.activate
def test_create_collection_success():
    """Test _create_collection successfully creates a collection."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    responses.add(
        responses.POST,
        search._collections_endpoint,
        json={"id": "456"},
        status=201,
    )

    assert search._create_collection() is True
    assert conversation.collection_id == "456"


@responses.activate
def test_create_collection_failure():
    """Test _create_collection handles API errors."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    responses.add(
        responses.POST,
        search._collections_endpoint,
        status=500,
    )

    with pytest.raises(HTTPError):
        search._create_collection()


@responses.activate
def test_parse_pdf_document_success():
    """Test _parse_pdf_document successfully parses a PDF."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    responses.add(
        responses.POST,
        search._pdf_parser_endpoint,
        json={"data": [{"content": "Page 1"}, {"content": "Page 2"}]},
        status=200,
    )

    content = search._parse_pdf_document("test.pdf", "application/pdf", BytesIO(b"pdf_content"))
    assert content == "Page 1\n\nPage 2"


@responses.activate
def test_parse_pdf_document_failure():
    """Test _parse_pdf_document handles API errors."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    responses.add(
        responses.POST,
        search._pdf_parser_endpoint,
        status=500,
    )

    with pytest.raises(HTTPError):
        search._parse_pdf_document("test.pdf", "application/pdf", BytesIO(b"pdf_content"))


@patch("chat.agent_rag.document_search.albert_api.AlbertRagDocumentSearch._parse_pdf_document")
def test_parse_document_pdf(mock_parse_pdf):
    """Test parse_document for PDF content."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    mock_parse_pdf.return_value = "Parsed PDF content"
    result = search.parse_document("test.pdf", "application/pdf", BytesIO(b"pdf"))
    assert result == "Parsed PDF content"
    mock_parse_pdf.assert_called_once()


@patch("chat.agent_rag.document_search.albert_api.DocumentConverter")
def test_parse_document_other(mock_converter):
    """Test parse_document for other content types."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    mock_converter.return_value.convert_raw.return_value = "Converted content"
    result = search.parse_document("test.txt", "text/plain", BytesIO(b"text"))
    assert result == "Converted content"
    mock_converter.return_value.convert_raw.assert_called_once()


@responses.activate
def test_store_document_success():
    """Test _store_document successfully stores a document."""
    conversation = ChatConversationFactory(collection_id="123")
    search = AlbertRagDocumentSearch(conversation)
    responses.add(
        responses.POST,
        search._documents_endpoint,
        json={"id": "doc1"},
        status=201,
    )

    search._store_document("test_doc", "some content")
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == search._documents_endpoint


@responses.activate
@patch("chat.agent_rag.document_search.albert_api.AlbertRagDocumentSearch._create_collection")
def test_store_document_creates_collection(mock_create_collection):
    """Test _store_document creates a collection if one doesn't exist."""
    conversation = ChatConversationFactory(collection_id=None)
    search = AlbertRagDocumentSearch(conversation)

    def set_collection_id(*args, **kwargs):
        conversation.collection_id = "123"
        return True

    mock_create_collection.side_effect = set_collection_id

    responses.add(
        responses.POST,
        search._documents_endpoint,
        json={"id": "doc1"},
        status=201,
    )

    search._store_document("test_doc", "some content")
    mock_create_collection.assert_called_once()
    assert conversation.collection_id == "123"


@patch(
    "chat.agent_rag.document_search.albert_api.AlbertRagDocumentSearch._create_collection",
    return_value=False,
)
def test_store_document_create_collection_fails(mock_create_collection):
    """Test _store_document raises error if collection creation fails."""
    conversation = ChatConversationFactory(collection_id=None)
    search = AlbertRagDocumentSearch(conversation)
    with pytest.raises(RuntimeError, match="Failed to create or retrieve the collection."):
        search._store_document("test_doc", "some content")
    mock_create_collection.assert_called_once()


@patch("chat.agent_rag.document_search.albert_api.AlbertRagDocumentSearch.parse_document")
@patch("chat.agent_rag.document_search.albert_api.AlbertRagDocumentSearch._store_document")
def test_parse_and_store_document(mock_store, mock_parse):
    """Test parse_and_store_document orchestrates parsing and storing."""
    conversation = ChatConversationFactory()
    search = AlbertRagDocumentSearch(conversation)
    mock_parse.return_value = "parsed content"
    name = "test.txt"
    content_type = "text/plain"
    content = BytesIO(b"text")

    result = search.parse_and_store_document(name, content_type, content)

    assert result == "parsed content"
    mock_parse.assert_called_once_with(name, content_type, content)
    mock_store.assert_called_once_with(name, "parsed content")


@responses.activate
def test_search_success():
    """Test search successfully returns results."""
    conversation = ChatConversationFactory(collection_id="123")
    search = AlbertRagDocumentSearch(conversation)
    mock_response = {
        "data": [
            {
                "method": "semantic",
                "chunk": {
                    "id": 1,
                    "content": "Relevant content snippet.",
                    "metadata": {"document_name": "doc1.txt"},
                },
                "score": 0.9,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    responses.post(
        url=search._search_endpoint,
        json=mock_response,
        status=200,
    )

    results = search.search("test query")

    assert len(results.data) == 1
    assert results.data[0].content == "Relevant content snippet."
    assert results.data[0].url == "doc1.txt"
    assert results.data[0].score == 0.9
    assert results.usage.prompt_tokens == 10
    assert results.usage.completion_tokens == 20


@responses.activate
def test_search_failure():
    """Test search handles API errors."""
    conversation = ChatConversationFactory(collection_id="123")
    search = AlbertRagDocumentSearch(conversation)
    responses.post(
        url=search._search_endpoint,
        status=500,
    )

    with pytest.raises(HTTPError):
        search.search("test query")
