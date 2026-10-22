"""Spike: web search delegated to the web_researcher sub-agent."""

# pylint: disable=protected-access

import pytest
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturn
from pydantic_ai.models.function import AgentInfo, FunctionModel

from chat.agents import web_researcher
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db()

RELEVANT = "https://relevant.example/"
IRRELEVANT = "https://irrelevant.example/"
INVENTED = "https://invented.example/"


async def fake_web_search(_ctx: RunContext, query: str) -> ToolReturn:
    """Return two sources, only one of which the researcher keeps; "broken" fails."""
    if query == "broken":
        raise ModelRetry("The search service is down.")
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
    """Search two queries at once, then report a searched fact, an invented one and a gap."""
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("web_search", {"queries": ["winner", "broken"]})])
    # One query failing does not fail the batch: its error sits next to the other results.
    search_results = messages[-1].parts[0].content
    assert search_results["broken"] == "Search failed: The search service is down."
    assert RELEVANT in str(search_results["winner"])
    findings = {
        "findings": [
            {"fact": "Team A won 2-1.", "source": RELEVANT},
            {"fact": "Team B was disqualified.", "source": INVENTED},
        ],
        "gaps": "the attendance",
    }
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, findings)])


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

    search_return = result.all_messages()[2].parts[0].content  # parent: request, call, return
    assert "Team A won 2-1. (source: https://relevant.example/)" in search_return
    assert "Not found: the attendance" in search_return
    assert "disqualified" not in search_return
    assert service._context_deps.web_research_sources == [RELEVANT]


def test_researcher_is_instrumented_like_the_parent(service, settings):
    """With Langfuse on, the researcher's runs are traced too (nested under delegate_task)."""
    settings.LANGFUSE_ENABLED = True
    traced = AIAgentService(service.conversation, user=service.user)

    def capability_types(agent):
        return {type(cap) for cap in agent._root_capability.capabilities}

    assert Instrumentation in capability_types(traced.conversation_agent)
    assert Instrumentation in capability_types(traced._web_researcher)
    assert Instrumentation not in capability_types(service._web_researcher)


@pytest.mark.parametrize(
    "soft_limit", [("MAX_SEARCH_ROUNDS", 1), ("WRAP_UP_TOKENS", 1), ("WRAP_UP_SECONDS", 0)]
)
def test_researcher_reports_partial_findings_near_its_limits(service, monkeypatch, soft_limit):
    """Past its search rounds, or near its token or time limit, the researcher loses
    web_search and must report, instead of searching until a hard limit discards everything."""
    monkeypatch.setattr(web_researcher, *soft_limit)
    seen = []

    def endless_searcher(_messages, info: AgentInfo) -> ModelResponse:
        """Search for as long as web_search is offered, then report."""
        can_search = any(tool.name == "web_search" for tool in info.function_tools)
        seen.append((can_search, info.instructions))
        if can_search:
            return ModelResponse(parts=[ToolCallPart("web_search", {"queries": ["more"]})])
        findings = {"findings": [], "gaps": "who won"}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, findings)])

    with service._web_researcher.override(model=FunctionModel(endless_searcher)):
        result = service._web_researcher.run_sync("Who won?", deps=service._context_deps)

    assert result.output.gaps == "who won"
    can_search, instructions = seen[-1]
    assert not can_search
    assert "do not search any more" in instructions
