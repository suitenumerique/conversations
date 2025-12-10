"""
Unit tests for document generic search RAG tool functionality.
"""

import json
import logging

import httpx
import pytest
import responses
import respx
from asgiref.sync import sync_to_async
from pydantic_ai import Agent, RunContext, RunUsage

from core.factories import UserFactory

from chat.tools.document_generic_search_rag import (
    add_document_rag_search_tool_from_setting,
    get_specific_rag_search_tool_config,
)

pytestmark = pytest.mark.django_db()


def test_get_specific_rag_search_tool_config_with_disabled_features(settings):
    """Test get_specific_rag_search_tool_config returns tools for enabled features."""
    user = UserFactory()

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "french_public_services": {
            "collection_ids": [784, 785],
            "feature_flag_value": "disabled",
            "tool_description": (
                "Use this tool when the user asks for information about French public services, "
                "the French labor market, employment laws, social benefits, or "
                "assistance with administrative procedures."
            ),
        },
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "disabled",
            "tool_description": "Use this tool to search French legal documents and laws.",
            "rag_backend_name": "chat.tests.tools.test_document_generic_search_rag.MockRagBackend",
        },
    }

    # The fixture tools are disabled by default
    assert get_specific_rag_search_tool_config(user) == {}


def test_get_specific_rag_search_tool_config_with_enabled_features(settings):
    """Test get_specific_rag_search_tool_config returns tools for enabled features."""
    user = UserFactory()

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "french_public_services": {
            "collection_ids": [784, 785],
            "feature_flag_value": "enabled",
            "tool_description": (
                "Use this tool when the user asks for information about French public services, "
                "the French labor market, employment laws, social benefits, or "
                "assistance with administrative procedures."
            ),
        },
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search French legal documents and laws.",
        },
    }

    assert get_specific_rag_search_tool_config(user) == {
        "french_public_services": {
            "collection_ids": [784, 785],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool when the user "
            "asks for information about "
            "French public services, the "
            "French labor market, "
            "employment laws, social "
            "benefits, or assistance with "
            "administrative procedures.",
        },
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search French legal documents and laws.",
        },
    }


@responses.activate
def test_get_specific_rag_search_tool_config_with_dynamic_features(settings, posthog):
    """Test get_specific_rag_search_tool_config with dynamic features."""
    user = UserFactory()

    responses.post(
        f"{posthog.host}/flags/?v=2",
        json={"flags": {"legal-documents": {"enabled": True}}},
        status=200,
    )

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "french_public_services": {
            "collection_ids": [784, 785],
            "feature_flag_value": "dynamic",
            "tool_description": (
                "Use this tool when the user asks for information about French public services, "
                "the French labor market, employment laws, social benefits, or "
                "assistance with administrative procedures."
            ),
        },
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "dynamic",
            "tool_description": "Use this tool to search French legal documents and laws.",
        },
    }

    assert get_specific_rag_search_tool_config(user) == {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "dynamic",
            "tool_description": "Use this tool to search French legal documents and laws.",
        }
    }


def test_add_document_rag_search_tool_from_setting_adds_tools(settings):
    """Test that add_document_rag_search_tool_from_setting adds tools to the agent."""
    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
    }

    user = UserFactory()

    agent = Agent("test")
    assert len(agent._function_toolset.tools) == 0  # pylint: disable=protected-access

    add_document_rag_search_tool_from_setting(agent, user)

    # Check that tools were added
    assert len(agent._function_toolset.tools) == 1  # pylint: disable=protected-access
    assert agent._function_toolset.tools["legal_documents"].name == "legal_documents"  # pylint: disable=protected-access
    assert (
        agent._function_toolset.tools["legal_documents"].description  # pylint: disable=protected-access
        == "Use this tool to search legal documents and laws."
    )
    assert agent._function_toolset.tools["legal_documents"].function_schema.json_schema == {  # pylint: disable=protected-access
        "additionalProperties": False,
        "properties": {
            "query": {"description": "The query to search information about.", "type": "string"}
        },
        "required": ["query"],
        "type": "object",
    }


def test_add_document_rag_search_tool_with_invalid_backend(settings, caplog):
    """Test that invalid backend import is handled gracefully."""
    caplog.set_level(logging.WARNING, logger="chat.tools.document_generic_search_rag")

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "rag_backend_name": "non.existent.Backend",
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
    }
    user = UserFactory()
    agent = Agent("test")

    add_document_rag_search_tool_from_setting(agent, user)

    # Tool should not be added due to import error
    assert len(agent._function_toolset.tools) == 0  # pylint: disable=protected-access

    # Check that warning was logged
    assert len(caplog.records) == 1
    assert "Could not import RAG backend non.existent.Backend" in caplog.records[0].message


def test_add_document_rag_search_tool_with_missing_collection_ids(settings, caplog):
    """Test that missing collection_ids is handled gracefully."""
    caplog.set_level(logging.WARNING, logger="chat.tools.document_generic_search_rag")

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
    }
    user = UserFactory()
    agent = Agent("test")

    add_document_rag_search_tool_from_setting(agent, user)

    # Tool should not be added due to import error
    assert len(agent._function_toolset.tools) == 0  # pylint: disable=protected-access

    # Check that warning was logged
    assert len(caplog.records) == 1
    assert "No collection IDs provided for tool legal_documents" in caplog.records[0].message


def test_add_document_rag_search_tool_with_missing_tool_description(settings, caplog):
    """Test that missing tool_description is handled gracefully."""
    caplog.set_level(logging.WARNING, logger="chat.tools.document_generic_search_rag")

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
        },
    }
    user = UserFactory()
    agent = Agent("test")

    add_document_rag_search_tool_from_setting(agent, user)

    # Tool should not be added due to import error
    assert len(agent._function_toolset.tools) == 0  # pylint: disable=protected-access

    # Check that warning was logged
    assert len(caplog.records) == 1
    assert "No tool description provided for tool legal_documents" in caplog.records[0].message


@respx.mock
def test_document_search_rag_tool_execution(settings):
    """Test that the generated RAG tool executes correctly."""
    search_mock = respx.post("https://albert.api.etalab.gouv.fr/v1/search").mock(
        return_value=httpx.Response(
            status_code=200,
            json={
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
            },
        )
    )
    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
        "legal_documents_2": {
            "collection_ids": [200],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
    }
    user = UserFactory()
    agent = Agent(model="test")

    add_document_rag_search_tool_from_setting(agent, user)

    result = agent.run_sync("What information can you find about French services?")

    # Verify the result
    assert json.loads(result.output) == {
        "legal_documents": {"0": {"snippets": "Relevant content snippet.", "url": "doc1.txt"}},
        "legal_documents_2": {"0": {"snippets": "Relevant content snippet.", "url": "doc1.txt"}},
    }

    assert len(search_mock.calls) == 2
    assert json.loads(search_mock.calls[0].request.content) == {
        "collections": [100, 101, 102],
        "k": 4,
        "prompt": "a",
        "score_threshold": 0.6,
    }
    assert json.loads(search_mock.calls[1].request.content) == {
        "collections": [200],
        "k": 4,
        "prompt": "a",
        "score_threshold": 0.6,
    }


def test_get_specific_rag_search_tool_config_with_empty_settings(settings):
    """Test get_specific_rag_search_tool_config with empty SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS."""
    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {}

    user = UserFactory()
    config = get_specific_rag_search_tool_config(user)

    assert config == {}


@pytest.mark.asyncio
@respx.mock
async def test_add_document_rag_search_tool_function_call(settings):
    """Test the function behavior."""
    search_mock = respx.post("https://albert.api.etalab.gouv.fr/v1/search").mock(
        return_value=httpx.Response(
            status_code=200,
            json={
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
            },
        )
    )
    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
    }

    user = await sync_to_async(UserFactory)()

    agent = Agent("test")
    add_document_rag_search_tool_from_setting(agent, user)

    result = await agent._function_toolset.tools["legal_documents"].function(  # pylint: disable=protected-access
        RunContext(model="test", usage=RunUsage(), deps={}),
        query="Find information about French laws.",
    )

    assert result.return_value == {
        "0": {"snippets": "Relevant content snippet.", "url": "doc1.txt"}
    }
    assert result.metadata == {"sources": {"doc1.txt"}}
    assert len(search_mock.calls) == 1
    assert json.loads(search_mock.calls[0].request.content) == {
        "collections": [100, 101, 102],
        "k": 4,
        "prompt": "Find information about French laws.",
        "score_threshold": 0.6,
    }


@pytest.mark.asyncio
@respx.mock
async def test_document_search_rag_http_status_error(settings, caplog):
    """Test that HTTPStatusError is properly handled and logged."""
    caplog.set_level(logging.ERROR, logger="chat.tools.document_generic_search_rag")

    # Mock the API to return a 500 error
    respx.post("https://albert.api.etalab.gouv.fr/v1/search").mock(
        return_value=httpx.Response(
            status_code=500,
            json={"error": "Internal server error"},
        )
    )

    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
    }

    user = await sync_to_async(UserFactory)()
    agent = Agent("test")
    add_document_rag_search_tool_from_setting(agent, user)

    # Call the tool function and expect a ModelRetry to be raised and caught
    tool_result = await agent._function_toolset.tools["legal_documents"].function(  # pylint: disable=protected-access
        RunContext(model="test", usage=RunUsage(), deps={}),
        query="Find information about French laws.",
    )

    # Verify the exception message
    assert tool_result == (
        "Document search service is currently unavailable: Server error '500 Internal "
        "Server Error' for url 'https://albert.api.etalab.gouv.fr/v1/search'\n"
        "For more information check: "
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500 You must "
        "explain this to the user and not try to answer based on your knowledge."
    )

    # Verify that error was logged
    assert "RAG document search failed for tool legal_documents" in caplog.records[0].message
    assert "Document search service is currently unavailable" in caplog.records[1].message
