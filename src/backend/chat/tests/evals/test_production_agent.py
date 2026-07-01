"""Tests that eval agents reuse production tool wiring."""

# pylint: disable=protected-access

import json

import pytest
from pydantic_ai.messages import ToolReturn

from chat.clients.pydantic_ai import AIAgentService
from chat.evals.configs.faithfulness_rag import (
    _build_faithfulness_rag_service,
    make_faithfulness_rag_task_fn,
)
from chat.evals.production_agent import (
    EVAL_FAKE_DOCUMENT_ID,
    build_production_agent_service,
    production_agent_deps,
    reset_eval_session_cache,
    stub_document_search_rag,
)
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings
from chat.tools.descriptions import (
    DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT,
    DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION,
    DOCUMENT_SUMMARIZE_SYSTEM_PROMPT,
    DOCUMENT_SUMMARIZE_TOOL_DESCRIPTION,
    SELF_DOCUMENTATION_SYSTEM_PROMPT,
    SELF_DOCUMENTATION_TOOL_DESCRIPTION,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_eval_session_cache_fixture():
    """Prevent stale cached ORM instances across tests."""
    reset_eval_session_cache()
    yield
    reset_eval_session_cache()


@pytest.fixture(autouse=True, name="ai_settings")
def ai_settings_fixture(settings):
    """Minimal LLM configuration for agent wiring tests."""
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


def _instruction_texts(agent) -> list[str]:
    texts = []
    for instruction in agent._instructions:
        texts.append(instruction() if callable(instruction) else instruction)
    return texts


def _tool_description(agent, name: str) -> str:
    return agent._function_toolset.tools[name].description.strip()


def test_self_documentation_eval_uses_production_wiring():
    """Eval agent should register the same instruction and tool description as prod."""
    service = build_production_agent_service("default-model")
    agent = service.conversation_agent

    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    reference = AIAgentService(conversation, user=user, model_hrid="default-model")
    reference._setup_self_documentation_tool()

    assert SELF_DOCUMENTATION_SYSTEM_PROMPT in _instruction_texts(agent)
    assert _instruction_texts(agent) == _instruction_texts(reference.conversation_agent)
    assert _tool_description(agent, "self_documentation") == (
        SELF_DOCUMENTATION_TOOL_DESCRIPTION.strip()
    )
    assert _tool_description(reference.conversation_agent, "self_documentation") == (
        SELF_DOCUMENTATION_TOOL_DESCRIPTION.strip()
    )


def test_eval_session_reuses_same_user_and_conversation():
    """Successive builds within one process must not create duplicate users."""
    service_a = build_production_agent_service("default-model")
    service_b = build_production_agent_service("default-model", rag_tools=True)

    assert service_a.user.pk == service_b.user.pk
    assert service_a.conversation.pk == service_b.conversation.pk
    assert service_a.user.sub == "eval-production-agent-session"


def test_stub_document_search_rag_replaces_without_conflict():
    """Stubbing must not re-register the tool (pydantic_ai name conflict)."""
    service = build_production_agent_service("default-model", rag_tools=True)

    async def stub(_ctx, _query, _document_id=None) -> ToolReturn:
        return ToolReturn(return_value="stub")

    stub_document_search_rag(service, stub)
    assert (
        service.conversation_agent._function_toolset.tools["document_search_rag"].function is stub
    )


def test_faithfulness_rag_eval_uses_production_wiring():
    """Eval agent with rag_tools should mirror production RAG setup."""
    run_agent = make_faithfulness_rag_task_fn("default-model")
    service = _build_faithfulness_rag_service("default-model")
    agent = service.conversation_agent
    deps = production_agent_deps(service)

    assert deps.web_search_enabled is False

    instructions = _instruction_texts(agent)
    assert DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT.strip() in [text.strip() for text in instructions]
    assert DOCUMENT_SUMMARIZE_SYSTEM_PROMPT.strip() in [text.strip() for text in instructions]
    assert any("Do not request re-upload of documents" in text for text in instructions)

    listing_prefix = "List of documents attached to this conversation:\n"
    resolved = next(text for text in instructions if listing_prefix in text)
    listing = json.loads(resolved.split(listing_prefix, 1)[1])
    assert listing["documents"][0]["title"] == "rapport-eval.pdf"
    assert listing["documents"][0]["document_id"] == EVAL_FAKE_DOCUMENT_ID

    assert _tool_description(agent, "document_search_rag") == (
        DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION.strip()
    )
    assert _tool_description(agent, "summarize") == DOCUMENT_SUMMARIZE_TOOL_DESCRIPTION.strip()
    assert set(agent._function_toolset.tools) >= {
        "self_documentation",
        "document_search_rag",
        "summarize",
    }
    assert run_agent is not None


def test_faithfulness_rag_hides_web_search_when_model_supports_it(ai_settings):
    """Web search must not be offered even when configured on the model."""
    ai_settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="provider/model",
            human_readable_name="Provider Model",
            is_active=True,
            icon=None,
            system_prompt="You are an assistant.",
            tools=[],
            web_search="chat.tools.web_search_brave.web_search_brave_llm_context",
            provider=LLMProvider(
                hrid="provider",
                base_url="https://example.com",
                api_key="key",
                kind="openai",
            ),
            settings=LLMSettings(max_tokens=1024),
        )
    }
    service = _build_faithfulness_rag_service("default-model")
    deps = production_agent_deps(service)

    assert deps.web_search_enabled is False
    web_search_tool = service.conversation_agent._function_toolset.tools["web_search"]
    assert web_search_tool.prepare is not None
