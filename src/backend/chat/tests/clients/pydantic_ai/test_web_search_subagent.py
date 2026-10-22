"""Spike: web search delegated to the web_researcher sub-agent."""

# pylint: disable=protected-access

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturn
from pydantic_ai.models.function import AgentInfo, FunctionModel

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db()

RELEVANT = "https://relevant.example/"
IRRELEVANT = "https://irrelevant.example/"
INVENTED = "https://invented.example/"


async def fake_web_search(_ctx: RunContext, query: str) -> ToolReturn:
    """Return two sources, only one of which the researcher keeps."""
    return ToolReturn(
        return_value={"0": {"url": RELEVANT, "snippets": [query]}},
        metadata={"sources": {RELEVANT, IRRELEVANT}},
    )


@pytest.fixture(name="service")
def service_fixture(settings):
    """Service for a model with web search delegated to the sub-agent."""
    settings.WEB_SEARCH_SUBAGENT_ENABLED = True
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            web_search=f"{__name__}.fake_web_search",
            provider=LLMProvider(hrid="unused", base_url="https://example.com", api_key="key"),
        ),
    }
    user = UserFactory(allow_smart_web_search=True)
    return AIAgentService(ChatConversationFactory(owner=user), user=user)


def parent_model(messages, _info: AgentInfo) -> ModelResponse:
    """Delegate once, then answer."""
    if len(messages) == 1:
        return ModelResponse(
            parts=[
                ToolCallPart("delegate_task", {"agent_name": "web_researcher", "task": "Who won?"})
            ]
        )
    return ModelResponse(parts=[TextPart(messages[-1].parts[0].content)])


def researcher_model(messages, info: AgentInfo) -> ModelResponse:
    """Search once, then report one searched source and one invented one."""
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("web_search", {"query": "winner"})])
    return ModelResponse(
        parts=[
            ToolCallPart(
                info.output_tools[0].name,
                {"answer": "Team A won.", "sources": [RELEVANT, INVENTED]},
            )
        ]
    )


def test_web_search_delegated_to_researcher(service):
    """The parent gets the researcher's answer; only searched, kept sources reach the UI."""
    service._setup_web_search_tool()
    tool_names = set(service.conversation_agent._function_toolset.tools)
    assert "web_search" not in tool_names

    with (
        service.conversation_agent.override(
            model=FunctionModel(parent_model), deps=service._context_deps
        ),
        service._web_researcher.override(model=FunctionModel(researcher_model)),
    ):
        result = service.conversation_agent.run_sync("Who won the match?")

    assert "Team A won." in result.output
    assert service._context_deps.web_research_sources == [RELEVANT]
