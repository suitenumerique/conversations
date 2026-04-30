"""
Tests for the document_search_rag tool.

Real components: Django ORM (factory-built conversation + attachments), real
AlbertRagBackend instance, RunContext built from a real ContextDeps.
The Albert HTTP endpoint is mocked at the wire level via respx.
"""

import json
import uuid
from urllib.parse import urljoin

import pytest
import respx
from asgiref.sync import sync_to_async
from httpx import Response
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.usage import RunUsage

from chat.clients.pydantic_ai import ContextDeps
from chat.factories import (
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
    UserFactory,
)
from chat.tools.document_search_rag import add_document_rag_search_tool

# transaction=True is required so writes done via sync_to_async (which run on
# threadpool connections distinct from the test's wrapping transaction) commit
# and are flushed via TRUNCATE between tests instead of leaking across them.
pytestmark = pytest.mark.django_db(transaction=True)


def _albert_response(*, data=None, usage=None):
    """Build an Albert /v1/search response body."""
    return {
        "data": data if data is not None else [],
        "usage": usage if usage is not None else {"prompt_tokens": 1, "completion_tokens": 0},
    }


def _albert_chunk(content="snippet", document_name="doc.pdf", score=0.9):
    return {
        "method": "semantic",
        "chunk": {"id": 1, "content": content, "metadata": {"document_name": document_name}},
        "score": score,
    }


@pytest.fixture(name="albert_settings")
def albert_settings_fixture(settings):
    """Point the RAG backend setting + Albert API at deterministic test values."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.ALBERT_API_URL = "https://albert.test"
    settings.ALBERT_API_KEY = "test-key"
    return settings


def _search_url(settings):
    return urljoin(settings.ALBERT_API_URL, "/v1/search")


@sync_to_async
def _make_conversation_and_attachments():
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user, collection_id="123")
    other = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="other.md",
        content_type="text/markdown",
        conversion_from=None,
    )
    target = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="report.pdf.md",
        content_type="text/markdown",
        conversion_from="123/attachments/report.pdf",
    )
    return user, conversation, other, target


def _run_context(conversation, user, *, session=None):
    return RunContext(
        model="test",
        usage=RunUsage(),
        deps=ContextDeps(conversation=conversation, user=user, session=session or {"trace": "x"}),
    )


def _tool_function():
    agent = Agent("test")
    add_document_rag_search_tool(agent)
    # pylint: disable=protected-access
    return agent._function_toolset.tools["document_search_rag"].function


def test_document_search_rag_schema_accepts_document_id():
    """The tool schema must expose document_id as an optional argument."""
    agent = Agent("test")
    add_document_rag_search_tool(agent)
    schema = agent._function_toolset.tools[  # pylint: disable=protected-access
        "document_search_rag"
    ].function_schema.json_schema

    assert "query" in schema["properties"]
    assert "document_id" in schema["properties"]
    assert schema["required"] == ["query"]


@pytest.mark.asyncio
@respx.mock
async def test_forwards_document_name_for_converted_attachment(albert_settings):
    """document_id resolves to the original (.md-stripped) file name in the request."""
    _, conversation, _, target = await _make_conversation_and_attachments()
    route = respx.post(_search_url(albert_settings)).mock(
        return_value=Response(200, json=_albert_response(data=[_albert_chunk()]))
    )

    result = await _tool_function()(
        _run_context(conversation, conversation.owner),
        query="what is the deadline?",
        document_id=str(target.id),
    )

    payload = json.loads(route.calls[0].request.content)
    assert payload["metadata_filters"] == {
        "key": "document_name",
        "value": "report.pdf",  # ".md" suffix stripped because conversion_from is set
        "type": "eq",
    }
    assert result.metadata == {"sources": {"doc.pdf"}}


@pytest.mark.asyncio
@respx.mock
async def test_forwards_document_name_for_non_converted_attachment(albert_settings):
    """For a native markdown doc (not converted) the file name is sent as-is."""
    _, conversation, other, _ = await _make_conversation_and_attachments()
    route = respx.post(_search_url(albert_settings)).mock(
        return_value=Response(200, json=_albert_response(data=[_albert_chunk()]))
    )

    await _tool_function()(
        _run_context(conversation, conversation.owner),
        query="q",
        document_id=str(other.id),
    )

    payload = json.loads(route.calls[0].request.content)
    assert payload["metadata_filters"]["value"] == "other.md"


@pytest.mark.asyncio
@respx.mock
async def test_no_document_id_sends_no_filter(albert_settings):
    """Without document_id the request body has no metadata_filters key."""
    _, conversation, _, _ = await _make_conversation_and_attachments()
    route = respx.post(_search_url(albert_settings)).mock(
        return_value=Response(200, json=_albert_response(data=[_albert_chunk()]))
    )

    await _tool_function()(_run_context(conversation, conversation.owner), query="q")

    payload = json.loads(route.calls[0].request.content)
    assert "metadata_filters" not in payload


@pytest.mark.asyncio
@respx.mock
async def test_filtered_search_empty_raises_model_retry(albert_settings):
    """When document_id is set and Albert returns no results, raise ModelRetry."""
    _, conversation, _, target = await _make_conversation_and_attachments()
    respx.post(_search_url(albert_settings)).mock(
        return_value=Response(200, json=_albert_response(data=[]))
    )

    with pytest.raises(ModelRetry) as exc:
        await _tool_function()(
            _run_context(conversation, conversation.owner),
            query="q",
            document_id=str(target.id),
        )
    msg = str(exc.value).lower()
    # Message must guide the model: retry without doc_id OR disclaim to user.
    assert "without document_id" in msg
    assert "does not contain" in msg


@pytest.mark.asyncio
@respx.mock
async def test_unfiltered_search_empty_returns_empty_tool_return(albert_settings):
    """No document_id + no results = ordinary empty ToolReturn, NOT ModelRetry."""
    _, conversation, _, _ = await _make_conversation_and_attachments()
    respx.post(_search_url(albert_settings)).mock(
        return_value=Response(200, json=_albert_response(data=[]))
    )

    result = await _tool_function()(_run_context(conversation, conversation.owner), query="q")

    assert result.return_value == []
    assert result.metadata == {"sources": set()}


@pytest.mark.asyncio
@respx.mock
async def test_usage_tokens_propagated_to_run_context(albert_settings):
    """Usage tokens reported by Albert are added to ctx.usage."""
    _, conversation, _, _ = await _make_conversation_and_attachments()
    respx.post(_search_url(albert_settings)).mock(
        return_value=Response(
            200,
            json=_albert_response(
                data=[_albert_chunk()], usage={"prompt_tokens": 42, "completion_tokens": 7}
            ),
        )
    )
    ctx = _run_context(conversation, conversation.owner)

    await _tool_function()(ctx, query="q")

    assert ctx.usage.input_tokens == 42
    assert ctx.usage.output_tokens == 7


@pytest.mark.asyncio
@respx.mock
async def test_document_id_accepts_canonical_uuid_variants(albert_settings):
    """document_id matches regardless of hyphens/case (uuid.UUID canonicalizes)."""
    _, conversation, _, target = await _make_conversation_and_attachments()
    route = respx.post(_search_url(albert_settings)).mock(
        return_value=Response(200, json=_albert_response(data=[_albert_chunk()]))
    )

    # Hyphen-less uppercase form
    weird = str(target.id).replace("-", "").upper()

    result = await _tool_function()(
        _run_context(conversation, conversation.owner),
        query="q",
        document_id=weird,
    )

    payload = json.loads(route.calls[0].request.content)
    assert payload["metadata_filters"]["value"] == "report.pdf"
    assert result.metadata == {"sources": {"doc.pdf"}}


@pytest.mark.asyncio
async def test_invalid_document_id_raises_model_retry(albert_settings):  # pylint: disable=unused-argument
    """Non-UUID document_id raises ModelRetry before any HTTP call."""
    _, conversation, _, _ = await _make_conversation_and_attachments()

    with pytest.raises(ModelRetry, match="Expected a valid UUID"):
        await _tool_function()(
            _run_context(conversation, conversation.owner),
            query="q",
            document_id="not-a-uuid",
        )


@pytest.mark.asyncio
async def test_unknown_document_id_raises_model_retry(albert_settings):  # pylint: disable=unused-argument
    """Valid UUID that doesn't match any attachment raises ModelRetry."""
    _, conversation, _, _ = await _make_conversation_and_attachments()

    with pytest.raises(ModelRetry, match="not found"):
        await _tool_function()(
            _run_context(conversation, conversation.owner),
            query="q",
            document_id=str(uuid.uuid4()),
        )
