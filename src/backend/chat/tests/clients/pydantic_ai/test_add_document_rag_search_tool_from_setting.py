"""Unit tests for add_document_rag_search_tool_from_setting integration with AIAgentService."""

import pytest

from core.factories import UserFactory

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db()


def test_ai_agent_service_adds_rag_tools_from_settings(settings):
    """Test that AIAgentService adds RAG tools from SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
    }
    settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "legal_documents": {
            "collection_ids": [100, 101, 102],
            "feature_flag_value": "enabled",
            "tool_description": "Use this tool to search legal documents and laws.",
        },
        "french_public_services": {
            "collection_ids": [784, 785],
            "feature_flag_value": "enabled",
            "tool_description": (
                "Use this tool when the user asks for information about French public services."
            ),
        },
    }

    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)

    # Create the service
    service = AIAgentService(conversation, user=user)

    # Check that tools were added to the conversation_agent
    agent_tools = service.conversation_agent._function_toolset.tools  # pylint: disable=protected-access

    assert "legal_documents" in agent_tools
    assert "french_public_services" in agent_tools

    # Verify tool names and descriptions
    assert agent_tools["legal_documents"].name == "legal_documents"
    assert (
        agent_tools["legal_documents"].description
        == "Use this tool to search legal documents and laws."
    )

    assert agent_tools["french_public_services"].name == "french_public_services"
    assert (
        agent_tools["french_public_services"].description
        == "Use this tool when the user asks for information about French public services."
    )
