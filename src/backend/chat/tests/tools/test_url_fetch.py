"""Tests for the URL fetch tool."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.exceptions import ModelRetry

from chat.tools.url_fetch import add_url_fetch_tool, detect_urls, is_url_allowed


@pytest.fixture(name="url_fetch_settings")
def url_fetch_settings_fixture(settings):
    """Set up URL fetch settings for tests."""
    settings.URL_FETCH_BLOCKED_SCHEMES = ["http"]
    settings.URL_FETCH_BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
    settings.URL_FETCH_BLOCKED_TLDS = [".ru", ".cn", ".kp", ".ir"]


def test_settings_exist(url_fetch_settings, settings):
    """URL fetch settings exist with expected defaults."""
    assert settings.URL_FETCH_BLOCKED_SCHEMES == ["http"]
    assert "localhost" in settings.URL_FETCH_BLOCKED_HOSTS
    assert ".ru" in settings.URL_FETCH_BLOCKED_TLDS


def test_detect_urls_simple():
    """detect_urls finds a plain HTTPS URL."""
    result = detect_urls("Check out https://example.com for details")
    assert result == ["https://example.com"]


def test_detect_urls_multiple():
    """detect_urls finds multiple URLs."""
    result = detect_urls("See https://example.com and https://other.org/path?q=1")
    assert result == ["https://example.com", "https://other.org/path?q=1"]


def test_detect_urls_http():
    """detect_urls also detects plain HTTP URLs."""
    result = detect_urls("Visit http://example.com now")
    assert result == ["http://example.com"]


def test_detect_urls_empty():
    """detect_urls returns empty list when no URL present."""
    assert detect_urls("No URL here at all") == []


def test_detect_urls_ignores_non_http():
    """detect_urls ignores non-HTTP(S) schemes."""
    assert detect_urls("ftp://example.com and file:///etc/passwd") == []


def test_is_url_allowed_valid(url_fetch_settings):
    """A standard HTTPS URL is allowed."""
    assert is_url_allowed("https://docs.numerique.gouv.fr/page") is True


def test_is_url_allowed_blocks_http_scheme(url_fetch_settings):
    """HTTP URLs are blocked by scheme filter."""
    assert is_url_allowed("http://example.com/page") is False


def test_is_url_allowed_blocks_localhost(url_fetch_settings):
    """localhost is blocked by host filter."""
    assert is_url_allowed("https://localhost/api") is False


def test_is_url_allowed_blocks_internal_ip(url_fetch_settings):
    """127.0.0.1 is blocked by host filter."""
    assert is_url_allowed("https://127.0.0.1/secret") is False


def test_is_url_allowed_blocks_tld(url_fetch_settings):
    """A blocked TLD is rejected."""
    assert is_url_allowed("https://example.ru/page") is False


def test_is_url_allowed_malformed(url_fetch_settings):
    """Malformed URL returns False."""
    assert is_url_allowed("not-a-url") is False


def test_is_url_allowed_blocks_cloud_metadata(url_fetch_settings):
    """Cloud metadata IP is blocked by IP range check."""
    assert is_url_allowed("https://169.254.169.254/latest/meta-data/") is False


def test_is_url_allowed_blocks_private_ip_range(url_fetch_settings):
    """Private RFC-1918 IP is blocked by IP range check."""
    assert is_url_allowed("https://10.0.0.1/internal") is False


def test_is_url_allowed_blocks_private_ip_192(url_fetch_settings):
    """Private 192.168.x.x IP is blocked."""
    assert is_url_allowed("https://192.168.1.100/admin") is False


@pytest.fixture(name="mock_rag_backend")
def mock_rag_backend_fixture():
    """Mock RAG backend class and instance."""
    backend_instance = MagicMock()
    backend_instance.collection_id = "test-collection-123"
    backend_instance.astore_document = AsyncMock()
    backend_instance.asearch = AsyncMock()
    backend_instance.parse_and_store_document = MagicMock(return_value="parsed content")
    backend_instance.acreate_collection = AsyncMock(return_value="new-collection-id")
    backend_class = MagicMock(return_value=backend_instance)
    return backend_class, backend_instance


@pytest.fixture(name="mock_conversation")
def mock_conversation_fixture():
    """Mock conversation with collection_id."""
    conv = MagicMock()
    conv.collection_id = "test-collection-123"
    conv.pk = "conv-pk-1"
    conv.asave = AsyncMock()
    return conv


@pytest.fixture(name="mock_ctx")
def mock_ctx_fixture(mock_conversation):
    """Mock RunContext for url_fetch tool tests."""
    ctx = Mock(spec=RunContext)
    ctx.deps = Mock()
    ctx.deps.conversation = mock_conversation
    ctx.deps.user = Mock()
    ctx.deps.user.sub = "user-sub-123"
    ctx.deps.session = {}
    ctx.usage = RunUsage(input_tokens=0, output_tokens=0)
    ctx.retries = {}
    ctx.max_retries = 2
    ctx.tool_name = "url_fetch"
    user_msg = Mock()
    user_msg.kind = "request"
    user_prompt_part = Mock()
    user_prompt_part.part_kind = "user-prompt"
    user_prompt_part.content = "What does https://example.com say about Python?"
    user_msg.parts = [user_prompt_part]
    ctx.messages = [user_msg]
    return ctx


@pytest.fixture(name="rag_search_results")
def rag_search_results_fixture():
    """Mock RAG search results."""
    result = MagicMock()
    result.usage.prompt_tokens = 10
    result.usage.completion_tokens = 5
    chunk = MagicMock()
    chunk.url = "https://example.com"
    chunk.content = "Python is a great language."
    result.data = [chunk]
    return result


def _get_tool_fn(agent):
    """Helper: extract the url_fetch tool function from a Pydantic AI agent."""
    return agent._function_toolset.tools["url_fetch"].function


@pytest.mark.asyncio
async def test_url_fetch_html_success(url_fetch_settings, mock_ctx, mock_rag_backend):
    """url_fetch fetches HTML, stores via astore_document, returns confirmation."""
    backend_class, backend_instance = mock_rag_backend

    with (
        patch("chat.tools.url_fetch.import_string", return_value=backend_class),
        patch("chat.tools.url_fetch.settings") as mock_settings,
        patch("chat.tools.url_fetch.sync_to_async") as mock_sync_to_async,
        patch("chat.tools.url_fetch.asyncio.to_thread", new_callable=AsyncMock),
        patch(
            "chat.tools.url_fetch.models.ChatConversationAttachment.objects.acreate",
            new_callable=AsyncMock,
        ),
    ):
        mock_settings.RAG_DOCUMENT_SEARCH_BACKEND = "some.backend"
        mock_settings.URL_FETCH_BLOCKED_SCHEMES = ["http"]
        mock_settings.URL_FETCH_BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
        mock_settings.URL_FETCH_BLOCKED_TLDS = [".ru", ".cn", ".kp", ".ir"]
        mock_sync_to_async.return_value = AsyncMock(return_value="Python is a great language.")

        get_response = Mock()
        get_response.is_redirect = False
        get_response.headers = {"content-type": "text/html; charset=utf-8"}
        get_response.text = "<html><body>Python is a great language.</body></html>"
        get_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=get_response)

        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            agent = Agent("test")
            add_url_fetch_tool(agent)
            tool_fn = _get_tool_fn(agent)
            assert tool_fn is not None
            result = await tool_fn(mock_ctx, url="https://example.com")

    assert "indexed" in result.return_value
    backend_instance.astore_document.assert_called_once()
    backend_instance.asearch.assert_not_called()


@pytest.mark.asyncio
async def test_url_fetch_pdf_success(url_fetch_settings, mock_ctx, mock_rag_backend):
    """url_fetch downloads PDF bytes, calls parse_and_store_document, returns confirmation."""
    backend_class, backend_instance = mock_rag_backend

    with (
        patch("chat.tools.url_fetch.import_string", return_value=backend_class),
        patch("chat.tools.url_fetch.settings") as mock_settings,
        patch("chat.tools.url_fetch.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
        patch(
            "chat.tools.url_fetch.models.ChatConversationAttachment.objects.acreate",
            new_callable=AsyncMock,
        ),
    ):
        mock_settings.RAG_DOCUMENT_SEARCH_BACKEND = "some.backend"
        mock_settings.URL_FETCH_BLOCKED_SCHEMES = ["http"]
        mock_settings.URL_FETCH_BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
        mock_settings.URL_FETCH_BLOCKED_TLDS = [".ru", ".cn", ".kp", ".ir"]
        # to_thread calls: save pdf, parse_and_store_document (returns parsed text), save md
        mock_to_thread.side_effect = [None, "# Parsed PDF content", None]

        get_response = Mock()
        get_response.is_redirect = False
        get_response.headers = {"content-type": "application/pdf"}
        get_response.content = b"%PDF-1.4 fake pdf content"
        get_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=get_response)

        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            agent = Agent("test")
            add_url_fetch_tool(agent)
            tool_fn = _get_tool_fn(agent)
            result = await tool_fn(mock_ctx, url="https://example.com/doc.pdf")

    assert "indexed" in result.return_value
    assert mock_to_thread.call_count == 3  # save pdf, parse, save md
    backend_instance.asearch.assert_not_called()


@pytest.mark.asyncio
async def test_url_fetch_blocked_url(url_fetch_settings, mock_ctx):
    """Blocked URL returns error string (ModelCannotRetry caught by wrapper)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        result = await tool_fn(mock_ctx, url="http://localhost/evil")
        assert "not allowed for security reasons" in result


@pytest.mark.asyncio
async def test_url_fetch_401_raises_cannot_retry(url_fetch_settings, mock_ctx):
    """HTTP 401 returns auth error string (ModelCannotRetry caught by wrapper)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        mock_response = Mock()
        mock_response.status_code = 401
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("401", request=Mock(), response=mock_response)
        )
        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            result = await tool_fn(mock_ctx, url="https://private.example.com/doc")
        assert "requires authentication" in result


@pytest.mark.asyncio
async def test_url_fetch_403_raises_cannot_retry(url_fetch_settings, mock_ctx):
    """HTTP 403 returns auth error string (ModelCannotRetry caught by wrapper)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        mock_response = Mock()
        mock_response.status_code = 403
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("403", request=Mock(), response=mock_response)
        )
        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            result = await tool_fn(mock_ctx, url="https://private.example.com/doc")
        assert "requires authentication" in result


@pytest.mark.asyncio
async def test_url_fetch_404_raises_cannot_retry(url_fetch_settings, mock_ctx):
    """HTTP 404 returns not-found string (ModelCannotRetry caught by wrapper)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        mock_response = Mock()
        mock_response.status_code = 404
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=Mock(), response=mock_response)
        )
        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            result = await tool_fn(mock_ctx, url="https://example.com/missing")
        assert "was not found" in result


@pytest.mark.asyncio
async def test_url_fetch_5xx_raises_model_retry(url_fetch_settings, mock_ctx):
    """HTTP 500 raises ModelRetry (retryable)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        mock_response = Mock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=Mock(), response=mock_response)
        )
        with (
            patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(ModelRetry),
        ):
            await tool_fn(mock_ctx, url="https://example.com/broken")


@pytest.mark.asyncio
async def test_url_fetch_timeout_raises_model_retry(url_fetch_settings, mock_ctx):
    """Network timeout raises ModelRetry (retryable)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with (
            patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(ModelRetry, match="timed out"),
        ):
            await tool_fn(mock_ctx, url="https://slow.example.com/")


@pytest.mark.asyncio
async def test_url_fetch_unsupported_content_type(url_fetch_settings, mock_ctx):
    """Unsupported content type returns error string (ModelCannotRetry caught by wrapper)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        for unsupported_ct in [
            "video/mp4",
            "audio/mpeg",
            "image/png",
            "application/zip",
            "application/octet-stream",
        ]:
            mock_response = Mock()
            mock_response.is_redirect = False
            mock_response.headers = {"content-type": unsupported_ct}
            mock_response.raise_for_status = Mock()
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
                result = await tool_fn(mock_ctx, url="https://example.com/file")
            assert "cannot analyse" in result


@pytest.mark.asyncio
async def test_url_fetch_empty_trafilatura_extraction(
    url_fetch_settings, mock_ctx, mock_rag_backend
):
    """Empty trafilatura extraction raises ModelCannotRetry."""
    backend_class, backend_instance = mock_rag_backend

    with (
        patch("chat.tools.url_fetch.import_string", return_value=backend_class),
        patch("chat.tools.url_fetch.settings") as mock_settings,
        patch("chat.tools.url_fetch.sync_to_async") as mock_sync_to_async,
    ):
        mock_settings.RAG_DOCUMENT_SEARCH_BACKEND = "some.backend"
        mock_settings.URL_FETCH_BLOCKED_SCHEMES = ["http"]
        mock_settings.URL_FETCH_BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
        mock_settings.URL_FETCH_BLOCKED_TLDS = [".ru", ".cn", ".kp", ".ir"]
        mock_sync_to_async.return_value = AsyncMock(return_value=None)

        get_response = Mock()
        get_response.is_redirect = False
        get_response.headers = {"content-type": "text/html"}
        get_response.text = "<html></html>"
        get_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=get_response)

        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            agent = Agent("test")
            add_url_fetch_tool(agent)
            tool_fn = _get_tool_fn(agent)

            result = await tool_fn(mock_ctx, url="https://spa.example.com/")
            assert "did not return readable content" in result


@pytest.mark.asyncio
async def test_url_fetch_creates_collection_when_missing(url_fetch_settings, mock_rag_backend):
    """_ensure_collection creates collection when collection_id is empty."""
    backend_class, backend_instance = mock_rag_backend
    backend_instance.collection_id = ""  # no collection yet

    conv = MagicMock()
    conv.collection_id = ""
    conv.pk = "conv-pk-1"
    conv.asave = AsyncMock()

    ctx = Mock(spec=RunContext)
    ctx.deps = Mock()
    ctx.deps.conversation = conv
    ctx.deps.user = Mock()
    ctx.deps.user.sub = "user-sub-123"
    ctx.deps.session = {}
    ctx.usage = RunUsage(input_tokens=0, output_tokens=0)
    ctx.retries = {}
    ctx.max_retries = 2
    ctx.tool_name = "url_fetch"
    user_msg = Mock()
    user_msg.kind = "request"
    user_prompt_part = Mock()
    user_prompt_part.part_kind = "user-prompt"
    user_prompt_part.content = "Check https://example.com"
    user_msg.parts = [user_prompt_part]
    ctx.messages = [user_msg]

    with (
        patch("chat.tools.url_fetch.import_string", return_value=backend_class),
        patch("chat.tools.url_fetch.settings") as mock_settings,
        patch("chat.tools.url_fetch.sync_to_async") as mock_sync_to_async,
        patch("chat.tools.url_fetch.asyncio.to_thread", new_callable=AsyncMock),
        patch(
            "chat.tools.url_fetch.models.ChatConversationAttachment.objects.acreate",
            new_callable=AsyncMock,
        ),
    ):
        mock_settings.RAG_DOCUMENT_SEARCH_BACKEND = "some.backend"
        mock_settings.URL_FETCH_BLOCKED_SCHEMES = ["http"]
        mock_settings.URL_FETCH_BLOCKED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
        mock_settings.URL_FETCH_BLOCKED_TLDS = [".ru", ".cn", ".kp", ".ir"]
        mock_sync_to_async.return_value = AsyncMock(return_value="Python content.")

        get_response = Mock()
        get_response.is_redirect = False
        get_response.headers = {"content-type": "text/html"}
        get_response.text = "<html><body>Python content.</body></html>"
        get_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=get_response)

        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            agent = Agent("test")
            add_url_fetch_tool(agent)
            tool_fn = _get_tool_fn(agent)
            await tool_fn(ctx, url="https://example.com")

    backend_instance.acreate_collection.assert_called_once_with(name="conversation-conv-pk-1")
    conv.asave.assert_called_once_with(update_fields=["collection_id", "updated_at"])


@pytest.mark.asyncio
async def test_url_fetch_network_error_raises_model_retry(url_fetch_settings, mock_ctx):
    """Generic network error raises ModelRetry (retryable)."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        with (
            patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(ModelRetry, match="Network error"),
        ):
            await tool_fn(mock_ctx, url="https://down.example.com/")


@pytest.mark.asyncio
async def test_url_fetch_redirect_to_blocked_url(url_fetch_settings, mock_ctx):
    """Redirect to a blocked URL returns error string."""
    with patch("chat.tools.url_fetch.import_string"):
        agent = Agent("test")
        add_url_fetch_tool(agent)
        tool_fn = _get_tool_fn(agent)

        redirect_response = Mock()
        redirect_response.is_redirect = True
        redirect_response.headers = {"location": "http://169.254.169.254/meta-data/"}
        redirect_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=redirect_response)

        with patch("chat.tools.url_fetch.httpx.AsyncClient", return_value=mock_client):
            result = await tool_fn(mock_ctx, url="https://example.com/redirect")
        assert "not allowed" in result


def test_instructions_no_url_returns_empty(url_fetch_settings):
    """Instructions closure returns empty string when no URL in latest message."""
    agent = Agent("test")
    add_url_fetch_tool(agent)

    ctx = Mock()
    user_msg = Mock()
    user_msg.kind = "request"
    part = Mock()
    part.part_kind = "user-prompt"
    part.content = "Tell me about Python"
    user_msg.parts = [part]
    ctx.messages = [user_msg]

    instructions_fn = None
    for fn in agent._instructions:
        if "url_fetch" in getattr(fn, "__name__", ""):
            instructions_fn = fn
            break
    assert instructions_fn is not None
    result = instructions_fn(ctx)
    assert result == ""


def test_instructions_blocked_url_returns_empty(url_fetch_settings):
    """Instructions closure returns empty string when URL is blocked."""
    agent = Agent("test")
    add_url_fetch_tool(agent)

    ctx = Mock()
    user_msg = Mock()
    user_msg.kind = "request"
    part = Mock()
    part.part_kind = "user-prompt"
    part.content = "Check http://localhost/admin"
    user_msg.parts = [part]
    ctx.messages = [user_msg]

    instructions_fn = None
    for fn in agent._instructions:
        if "url_fetch" in getattr(fn, "__name__", ""):
            instructions_fn = fn
            break

    result = instructions_fn(ctx)
    assert result == ""


def test_instructions_injects_only_allowed_urls(url_fetch_settings):
    """Instructions closure lists only the allowed URL when message has a blocked one too."""
    agent = Agent("test")
    add_url_fetch_tool(agent)

    ctx = Mock()
    user_msg = Mock()
    user_msg.kind = "request"
    part = Mock()
    part.part_kind = "user-prompt"
    part.content = "See https://example.com and http://localhost"
    user_msg.parts = [part]
    ctx.messages = [user_msg]

    instructions_fn = None
    for fn in agent._instructions:
        if "url_fetch" in getattr(fn, "__name__", ""):
            instructions_fn = fn
            break

    result = instructions_fn(ctx)
    assert "https://example.com" in result
    assert "localhost" not in result
