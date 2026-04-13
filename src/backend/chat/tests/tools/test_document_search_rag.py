"""Unit tests for the conversation document RAG search tool."""

import json

import pytest
import responses
from pydantic_ai import Agent, RunContext, RunUsage
from rest_framework import status

from core.factories import UserFactory

from chat.clients.pydantic_ai import ContextDeps
from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.tools.document_search_rag import add_document_rag_search_tool

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure Albert backend for the search tool tests."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.RAG_DOCUMENT_PARSER = "chat.agent_rag.document_converter.parser.AlbertParser"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


def _build_ctx(conversation, user):
    """Build a RunContext exposing the same deps the agent uses in production."""
    return RunContext(
        model="test",
        usage=RunUsage(),
        deps=ContextDeps(conversation=conversation, user=user, session=None),
    )


def _agent_with_rag_tool():
    agent = Agent("test", deps_type=ContextDeps)
    add_document_rag_search_tool(agent)
    return agent


def _call_tool(agent, ctx, query="anything"):
    return agent._function_toolset.tools["document_search_rag"].function(  # pylint: disable=protected-access
        ctx, query=query
    )


def _mock_search(content="snippet", document_name="doc1.txt"):
    return responses.post(
        "https://albert.api.etalab.gouv.fr/v1/search",
        json={
            "data": [
                {
                    "method": "semantic",
                    "chunk": {
                        "id": 1,
                        "content": content,
                        "metadata": {"document_name": document_name},
                    },
                    "score": 0.9,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        },
        status=status.HTTP_200_OK,
    )


@responses.activate
def test_search_uses_only_conversation_collection_when_no_project():
    """Conversation without a project: only conversation.collection_id is sent."""
    search_mock = _mock_search()
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user, collection_id="11")
    agent = _agent_with_rag_tool()

    result = _call_tool(agent, _build_ctx(conversation, user))

    assert search_mock.call_count == 1
    payload = json.loads(search_mock.calls[0].request.body)
    assert payload["collections"] == [11]
    assert {r.url for r in result.return_value} == {"doc1.txt"}
    assert result.metadata == {"sources": {"doc1.txt"}}


@responses.activate
def test_search_includes_project_collection_when_set():
    """When the conversation belongs to a project with a collection, both are searched."""
    search_mock = _mock_search()
    user = UserFactory()
    project = ChatProjectFactory(owner=user, collection_id="22")
    conversation = ChatConversationFactory(owner=user, project=project, collection_id="11")
    agent = _agent_with_rag_tool()

    _call_tool(agent, _build_ctx(conversation, user))

    payload = json.loads(search_mock.calls[0].request.body)
    # Both collection ids land in the search payload (Albert casts to int).
    assert sorted(payload["collections"]) == [11, 22]


@responses.activate
def test_search_skips_project_collection_when_project_has_none():
    """A project without a collection_id (e.g. only images uploaded) is ignored."""
    search_mock = _mock_search()
    user = UserFactory()
    project = ChatProjectFactory(owner=user, collection_id=None)
    conversation = ChatConversationFactory(owner=user, project=project, collection_id="11")
    agent = _agent_with_rag_tool()

    _call_tool(agent, _build_ctx(conversation, user))

    payload = json.loads(search_mock.calls[0].request.body)
    assert payload["collections"] == [11]


@responses.activate
def test_search_uses_only_project_collection_when_conversation_has_none():
    """A project-only conversation (no own collection yet) still searches the project."""
    search_mock = _mock_search()
    user = UserFactory()
    project = ChatProjectFactory(owner=user, collection_id="22")
    conversation = ChatConversationFactory(owner=user, project=project, collection_id=None)
    agent = _agent_with_rag_tool()

    _call_tool(agent, _build_ctx(conversation, user))

    payload = json.loads(search_mock.calls[0].request.body)
    assert payload["collections"] == [22]


@responses.activate
def test_search_accumulates_token_usage():
    """Tokens reported by the backend are added to the run usage."""
    _mock_search()
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user, collection_id="11")
    agent = _agent_with_rag_tool()
    ctx = _build_ctx(conversation, user)

    _call_tool(agent, ctx)

    assert ctx.usage.input_tokens == 10
    assert ctx.usage.output_tokens == 20
