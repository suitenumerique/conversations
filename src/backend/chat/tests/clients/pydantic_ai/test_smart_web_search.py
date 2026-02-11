"""Unit tests for add_document_rag_search_tool_from_setting integration with AIAgentService."""

# pylint: disable=redefined-outer-name, protected-access

import pytest
from pydantic_ai.models.test import TestModel

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db()


@pytest.fixture()
def _llm_config_with_websearch(settings):
    """Configure a single active model that includes the web search tool."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=["web_search_brave_with_document_backend"],
            provider=LLMProvider(
                hrid="unused",
                base_url="https://example.com",
                api_key="key",
            ),
        ),
    }


def test_smart_search_disabled_suppresses_tool_at_runtime(_llm_config_with_websearch):
    """
    When smart search is off, the tool must be suppressed at runtime.
    """
    user = UserFactory(allow_smart_web_search=False)
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    assert service._is_smart_search_enabled is False
    assert service._is_web_search_enabled is True

    # Replicate what _run_agent does before calling the model
    if not service._is_smart_search_enabled and service._is_web_search_enabled:
        service._context_deps.web_search_enabled = False

    with service.conversation_agent.override(model=TestModel(), deps=service._context_deps):
        response = service.conversation_agent.run_sync("Search the web for something.")

    assert response.output == "success (no tool calls)"


def test_smart_search_enabled_tool_is_called(_llm_config_with_websearch):
    """
    When smart search is on, the tool must be invoked.
    """
    user = UserFactory(allow_smart_web_search=True)
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    assert service._is_smart_search_enabled is True
    assert service._context_deps.web_search_enabled is True

    with service.conversation_agent.override(model=TestModel(), deps=service._context_deps):
        response = service.conversation_agent.run_sync("Search the web for something.")

    assert "web_search_brave_with_document_backend" in response.output


def test_force_websearch_overrides_smart_search_disabled(_llm_config_with_websearch):
    """
    When smart search is off, the tool must be enabled via force_web_search.
    """
    user = UserFactory(allow_smart_web_search=False)
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    assert service._is_smart_search_enabled is False
    assert service._context_deps.web_search_enabled is False

    service._setup_web_search(force_web_search=True)

    web_search_tool_name = service.conversation_agent.get_web_search_tool_name()
    assert service._context_deps.web_search_enabled is True
    assert any(
        callable(instr) and web_search_tool_name in instr()
        for instr in service.conversation_agent._instructions
    )
    with service.conversation_agent.override(model=TestModel(), deps=service._context_deps):
        response = service.conversation_agent.run_sync("Search the web for something.")
        assert "web_search_brave_with_document_backend" in response.output
