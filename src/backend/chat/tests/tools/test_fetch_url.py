"""Tests for the fetch_url tool."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import respx
from pydantic_ai import RunContext, RunUsage

from chat.factories import ChatConversationFactory
from chat.tools.fetch_url import detect_url_in_conversation, fetch_url
from core.factories import UserFactory

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def fetch_url_settings(settings):
    """Define settings for fetch_url tests."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "test-albert-key"
    settings.ALBERT_API_TIMEOUT = 30
    settings.ALBERT_API_PARSE_TIMEOUT = 60


@pytest.fixture(name="mocked_context")
def fixture_mocked_context(conversation, user):
    """Fixture for a mocked RunContext with conversation and user."""
    mock_ctx = Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)
    mock_ctx.deps = Mock()
    mock_ctx.deps.conversation = conversation
    mock_ctx.deps.user = user
    return mock_ctx


@pytest.fixture(name="conversation")
def fixture_conversation():
    """Create a test conversation."""
    return ChatConversationFactory()


@pytest.fixture(name="user")
def fixture_user():
    """Create a test user."""
    return UserFactory()


def test_detect_url_in_conversation_with_ui_messages(conversation):
    """Test URL detection in ui_messages."""
    conversation.ui_messages = [
        {
            "role": "user",
            "parts": [{"type": "text", "text": "Check this: https://example.com/page"}],
        }
    ]
    urls = detect_url_in_conversation(conversation.ui_messages)
    assert "https://example.com/page" in urls


def test_detect_url_in_conversation_multiple_urls(conversation):
    """Test URL detection with multiple URLs."""
    conversation.ui_messages = [
        {
            "role": "user",
            "parts": [
                {
                    "type": "text",
                    "text": "See https://example.com/1 and https://example.com/2",
                }
            ],
        }
    ]
    urls = detect_url_in_conversation(conversation.ui_messages)
    assert len(urls) == 2
    assert "https://example.com/1" in urls
    assert "https://example.com/2" in urls


def test_detect_url_in_conversation_no_urls(conversation):
    """Test URL detection when no URLs are present."""
    conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": "No URL here"}]}
    ]
    urls = detect_url_in_conversation(conversation.ui_messages)
    assert urls == []


def test_detect_url_in_conversation_empty_conversation():
    """Test URL detection with None conversation."""
    urls = detect_url_in_conversation(None)
    assert urls == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_not_detected_in_conversation(mocked_context):
    """Test fetch_url when URL is not detected in conversation."""
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    result = await fetch_url(mocked_context, "https://example.com")

    assert result.return_value["error"] == "URL not detected in conversation"
    assert "not detected" in result.content


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_docs_numerique_gouv_fr_success(mocked_context):
    """Test fetch_url with docs.numerique.gouv.fr URL."""
    url = "https://docs.numerique.gouv.fr/docs/1ef86abf-f7e0-46ce-b6c7-8be8b8af4c3d/"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Check {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    # Mock the Docs API response
    docs_api_url = "https://docs.numerique.gouv.fr/api/v1.0/documents/1ef86abf-f7e0-46ce-b6c7-8be8b8af4c3d/content/?content_format=markdown"
    respx.get(docs_api_url).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"content": "# Test Document\n\nThis is test content."},
        )
    )

    result = await fetch_url(mocked_context, url)

    assert result.return_value["url"] == url
    assert result.return_value["source"] == "docs.numerique.gouv.fr"
    assert "content" in result.return_value
    assert "# Test Document" in result.return_value["content"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_docs_numerique_gouv_fr_large_content(mocked_context):
    """Test fetch_url with docs.numerique.gouv.fr when content is large."""
    url = "https://docs.numerique.gouv.fr/docs/1ef86abf-f7e0-46ce-b6c7-8be8b8af4c3d/"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Check {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    # Create large content (> 8000 chars)
    large_content = "# Large Document\n\n" + "x" * 10000

    docs_api_url = "https://docs.numerique.gouv.fr/api/v1.0/documents/1ef86abf-f7e0-46ce-b6c7-8be8b8af4c3d/content/?content_format=markdown"
    respx.get(docs_api_url).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"content": large_content},
        )
    )

    # Mock Albert API document storage
    respx.post("https://albert.api.etalab.gouv.fr/v1/documents").mock(
        return_value=httpx.Response(
            status_code=200,
            json={"id": 456},
        )
    )

    # Mock RAG backend
    with patch("chat.tools.fetch_url.import_string") as mock_import, patch(
        "chat.tools.fetch_url.models.ChatConversationAttachment.objects.acreate", new_callable=AsyncMock
    ) as mock_attachment_create, patch("chat.tools.fetch_url.default_storage.save") as mock_storage:
        mock_backend = Mock()
        mock_backend.collection_id = None  # Will trigger collection creation
        mock_backend.create_collection = Mock(return_value="123")
        mock_backend.parse_document = Mock(return_value=large_content)
        mock_backend.store_document = Mock()
        mock_import.return_value = Mock(return_value=mock_backend)

        # Mock conversation.asave for collection_id update
        mocked_context.deps.conversation.asave = AsyncMock()

        # Mock attachment creation
        mock_attachment = Mock()
        mock_attachment.upload_state = None
        mock_attachment.asave = AsyncMock()
        mock_attachment_create.return_value = mock_attachment

        result = await fetch_url(mocked_context, url)

        assert result.return_value["url"] == url
        assert result.return_value["stored_in_rag"] is True
        assert "content_preview" in result.return_value
        assert result.metadata["sources"] == {url}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_wikipedia_html(mocked_context):
    """Test fetch_url with Wikipedia HTML page."""
    url = "https://fr.wikipedia.org/wiki/%C3%89lectron"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Read {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    # Mock Wikipedia HTML response
    html_content = """
    <html>
    <head><title>Électron - Wikipédia</title></head>
    <body>
        <h1>Électron</h1>
        <p>L'électron est une particule élémentaire.</p>
    </body>
    </html>
    """
    respx.get(url).mock(
        return_value=httpx.Response(
            status_code=200,
            content=html_content.encode("utf-8"),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )

    # Mock trafilatura extraction
    with patch("chat.tools.fetch_url.trafilatura.extract") as mock_extract:
        mock_extract.return_value = "Électron\n\nL'électron est une particule élémentaire."

        result = await fetch_url(mocked_context, url)

        assert result.return_value["url"] == url
        assert result.return_value["status_code"] == 200
        assert "content" in result.return_value
        assert "Électron" in result.return_value["content"]
        assert result.metadata["sources"] == {url}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_arxiv_pdf(mocked_context):
    """Test fetch_url with arXiv PDF."""
    url = "https://arxiv.org/pdf/1706.08595"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Read {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    # Mock PDF response
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    respx.get(url).mock(
        return_value=httpx.Response(
            status_code=200,
            content=pdf_content,
            headers={"content-type": "application/pdf"},
        )
    )

    # Mock Albert API parse endpoint
    parsed_content = "# PDF Content\n\nExtracted text from PDF."
    respx.post("https://albert.api.etalab.gouv.fr/v1/parse-beta").mock(
        return_value=httpx.Response(
            status_code=200,
            json={"data": [{"content": parsed_content}]},
        )
    )

    # Mock Albert API document storage
    respx.post("https://albert.api.etalab.gouv.fr/v1/documents").mock(
        return_value=httpx.Response(
            status_code=200,
            json={"id": 456},
        )
    )

    # Mock RAG backend for PDF storage
    with patch("chat.tools.fetch_url.import_string") as mock_import, patch(
        "chat.tools.fetch_url.models.ChatConversationAttachment.objects.acreate", new_callable=AsyncMock
    ) as mock_attachment_create, patch("chat.tools.fetch_url.default_storage.save") as mock_storage:
        mock_backend = Mock()
        mock_backend.collection_id = "123"
        mock_backend.parse_document = Mock(return_value=parsed_content)
        mock_backend.store_document = Mock()
        mock_import.return_value = Mock(return_value=mock_backend)

        # Mock attachment creation
        mock_attachment = Mock()
        mock_attachment.upload_state = None
        mock_attachment.asave = AsyncMock()
        mock_attachment_create.return_value = mock_attachment

        result = await fetch_url(mocked_context, url)

        assert result.return_value["url"] == url
        assert result.return_value["stored_in_rag"] is True
        assert "content_preview" in result.return_value
        assert result.return_value["content_type"] == "application/pdf"
        assert result.metadata["sources"] == {url}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_http_error(mocked_context):
    """Test fetch_url with HTTP error."""
    url = "https://example.com/error"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Check {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    respx.get(url).mock(return_value=httpx.Response(status_code=404))

    result = await fetch_url(mocked_context, url)

    assert result.return_value["url"] == url
    assert "error" in result.return_value
    assert "404" in result.return_value["error"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_timeout(mocked_context):
    """Test fetch_url with timeout."""
    url = "https://example.com/slow"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Check {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    respx.get(url).mock(side_effect=httpx.TimeoutException("Request timed out"))

    result = await fetch_url(mocked_context, url)

    assert result.return_value["url"] == url
    assert "error" in result.return_value
    assert "Timeout" in result.return_value["error"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_url_docs_numerique_gouv_fr_empty_content(mocked_context):
    """Test fetch_url with docs.numerique.gouv.fr when content is empty."""
    url = "https://docs.numerique.gouv.fr/docs/1ef86abf-f7e0-46ce-b6c7-8be8b8af4c3d/"
    mocked_context.deps.conversation.ui_messages = [
        {"role": "user", "parts": [{"type": "text", "text": f"Check {url}"}]}
    ]
    mocked_context.deps.messages = mocked_context.deps.conversation.ui_messages

    docs_api_url = "https://docs.numerique.gouv.fr/api/v1.0/documents/1ef86abf-f7e0-46ce-b6c7-8be8b8af4c3d/content/?content_format=markdown"
    respx.get(docs_api_url).mock(
        return_value=httpx.Response(
            status_code=200,
            json={"content": ""},
        )
    )

    result = await fetch_url(mocked_context, url)

    assert result.return_value["url"] == url
    assert result.return_value["error"] == "Content empty or private"
    assert "n'est pas public" in result.content

