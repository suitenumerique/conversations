"""Tests for the tool_selection eval wiring."""

# pylint: disable=protected-access

import json

import pytest
from pydantic_ai.messages import ToolReturn

from chat.evals.configs import REGISTRY
from chat.evals.production_agent import (
    EVAL_FAKE_DOCUMENT_ID,
    EVAL_FAKE_DOCUMENT_LISTING,
    build_production_agent_service,
    reset_eval_session_cache,
    stubbed_tools,
)
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings
from chat.tools.descriptions import WEB_SEARCH_TOOL_DESCRIPTION

pytestmark = pytest.mark.django_db

LISTING_PREFIX = "List of documents attached to this conversation:\n"


@pytest.fixture(autouse=True)
def reset_eval_session_cache_fixture():
    """Reset the eval session cache before and after each test."""
    reset_eval_session_cache()
    yield
    reset_eval_session_cache()


@pytest.fixture(autouse=True, name="ai_settings")
def ai_settings_fixture(settings):
    """Set up the AI settings for the tests."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="provider/model",
            human_readable_name="Provider Model",
            is_active=True,
            icon=None,
            system_prompt="You are an assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="provider",
                base_url="https://example.com",
                api_key="key",
                kind="openai",
            ),
            settings=LLMSettings(max_tokens=1024),
        )
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    return settings


def _stub(_ctx, *args, **kwargs) -> ToolReturn:
    return ToolReturn(return_value="stub")


def _resolve_instruction(service, name: str) -> str:
    matches = [
        fn
        for fn in service.conversation_agent._instructions
        if callable(fn) and fn.__name__ == name
    ]
    assert matches, f"instruction '{name}' not registered on the agent"
    return matches[0]()


def test_tool_selection_registered():
    """Test that the tool selection is registered."""
    assert "tool_selection" in REGISTRY
    assert REGISTRY["tool_selection"].name == "tool_selection"


def test_without_documents_excludes_rag_tools():
    """Test that the tool selection excludes RAG tools when no documents are attached."""
    service = build_production_agent_service("default-model", rag_tools=False)
    tools = {tool.name for tool in stubbed_tools(service, {"web_search": _stub})}
    assert "document_search_rag" not in tools
    assert "summarize" not in tools
    assert "self_documentation" in tools
    assert "web_search" in tools


def test_with_documents_registers_rag_tools_and_listing():
    """
    Test that the tool selection registers RAG tools and the document listing
    when documents are attached.
    """
    service = build_production_agent_service(
        "default-model",
        rag_tools=True,
        document_context_instruction=EVAL_FAKE_DOCUMENT_LISTING,
    )
    tools = set(service.conversation_agent._function_toolset.tools)
    assert {"document_search_rag", "summarize", "self_documentation"} <= tools

    resolved = _resolve_instruction(service, "attached_documents_note")
    assert LISTING_PREFIX in resolved
    listing = json.loads(resolved.split(LISTING_PREFIX, 1)[1])
    assert listing["documents"][0]["title"] == "Document 1"
    assert listing["documents"][0]["document_id"] == EVAL_FAKE_DOCUMENT_ID


def test_stubbed_tools_adds_web_search_when_model_lacks_it():
    """web_search is added, gated on deps like production, when the model has none."""
    service = build_production_agent_service("default-model")
    assert "web_search" not in service.conversation_agent._function_toolset.tools

    web_search = {tool.name: tool for tool in stubbed_tools(service, {"web_search": _stub})}[
        "web_search"
    ]

    assert web_search.function is _stub
    assert web_search.description == WEB_SEARCH_TOOL_DESCRIPTION
    assert web_search.prepare is not None
    assert "web_search" not in service.conversation_agent._function_toolset.tools


def test_stubbed_tools_swaps_implementation_and_keeps_production_tools():
    """Stubbed tools keep their production description; other tools pass through as-is."""
    service = build_production_agent_service(
        "default-model",
        rag_tools=True,
        document_context_instruction=EVAL_FAKE_DOCUMENT_LISTING,
    )
    production = service.conversation_agent._function_toolset.tools

    tools = {tool.name: tool for tool in stubbed_tools(service, {"summarize": _stub})}

    assert tools["summarize"].function is _stub
    assert tools["summarize"].description == production["summarize"].description
    assert tools["self_documentation"] is production["self_documentation"]
    assert production["summarize"].function is not _stub


def test_fake_listing_mentions_eval_document():
    """Test that the fake listing mentions the eval document."""
    assert "Document 1" in EVAL_FAKE_DOCUMENT_LISTING
    assert EVAL_FAKE_DOCUMENT_ID in EVAL_FAKE_DOCUMENT_LISTING
