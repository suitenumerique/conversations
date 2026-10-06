"""Tests for the datagouv_selection eval, driven end to end by a scripted model.

One seam: a dataset case is evaluated with the registered task function and its
YAML evaluators, while a FunctionModel plays a fixed script of tool calls. The
tests observe what the model was offered, what each tool call returned, and
which evaluators passed — never the agent's private attributes.
"""

# pylint: disable=protected-access
# Command._load_dataset is the eval command's own dataset loader; reusing it keeps
# the YAML parsing (config block stripping, custom evaluator types) identical.

from contextlib import ExitStack
from dataclasses import dataclass, field
from unittest.mock import patch
from uuid import uuid4

import logfire
import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from chat.evals.configs import REGISTRY, datagouv_selection
from chat.evals.datagouv_connector import load_scenarios, load_tool_snapshot
from chat.evals.production_agent import reset_eval_session_cache
from chat.evals.tool_stub_responses import parse_tool_stub_responses
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings
from chat.management.commands.run_evals import Command
from chat.mcp_servers import DataGouvConnector

pytestmark = pytest.mark.django_db

GEODAE_DATASET_ID = "61556e1e9d6adb2df86eb0fc"
GEODAE_RESOURCE_ID = "edb6a9e1-2f16-4bbf-99e7-c3eb6b90794c"


@pytest.fixture(autouse=True, name="eval_session")
def eval_session_fixture():
    """Rebuild the eval session user and conversation for every test."""
    reset_eval_session_cache()
    yield
    reset_eval_session_cache()


# Langfuse on (as in dev and production) pins pydantic_ai's version 2 span schema, where
# every tool span is named "running tool"; off, spans are named "execute_tool <tool>".
# Tool calls must be matched the same way under both.
@pytest.fixture(
    autouse=True,
    name="ai_settings",
    params=[True, False],
    ids=["langfuse_spans", "default_spans"],
)
def ai_settings_fixture(request, settings):
    """A model configuration the eval services can be built from; never called."""
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
    settings.LANGFUSE_ENABLED = request.param
    return settings


@pytest.fixture(autouse=True, name="span_capture")
def span_capture_fixture():
    """Record tool spans locally, as the run_evals command does, then stop."""
    logfire.configure(send_to_logfire=False, console=False, service_name="evals-tests")
    Agent.instrument_all()
    yield
    Agent.instrument_all(False)


@dataclass
class ScriptedModel:
    """Plays one list of tool calls per model turn, then answers; records what it saw."""

    turns: list[list[tuple[str, dict]]]
    seen: list[tuple[list[ModelMessage], AgentInfo]] = field(default_factory=list)

    def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Answer the model request for the current turn."""
        self.seen.append((messages, info))
        turn = sum(isinstance(message, ModelResponse) for message in messages)
        if turn < len(self.turns):
            return ModelResponse(
                parts=[ToolCallPart(name, arguments) for name, arguments in self.turns[turn]]
            )
        return ModelResponse(parts=[TextPart("Voici la réponse.")])

    @property
    def offered_tools(self) -> dict:
        """The tools offered on the first model request, by name."""
        return {tool.name: tool for tool in self.seen[0][1].function_tools}

    @property
    def instructions(self) -> str:
        """The instructions sent with the first model request."""
        return self.seen[0][1].instructions or ""

    @property
    def tool_results(self) -> list[tuple[str, str]]:
        """Every tool result the model was shown, in order, as (tool name, content)."""
        return [
            (part.tool_name, part.content)
            for message in self.seen[-1][0]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]


def evaluate_cases(*runs: tuple[str, ScriptedModel]) -> list[dict[str, bool]]:
    """Evaluate (case name, script) runs, in order, through ONE task function.

    Sharing the task function across runs is what run_evals does across cases and
    --runs repeats. Returns each run's evaluator results by evaluation name.
    """
    config = REGISTRY["datagouv_selection"]
    services = []
    build_service = datagouv_selection.build_tool_selection_service

    def capture_service(*args, **kwargs):
        service = build_service(*args, **kwargs)
        services.append(service)
        return service

    with patch.object(
        datagouv_selection, "build_tool_selection_service", side_effect=capture_service
    ):
        task = config.make_task_fn("default-model")

    results = []
    for case_name, script in runs:
        dataset = Command()._load_dataset(config, case_name)
        with ExitStack() as stack:
            for service in services:
                stack.enter_context(
                    service.conversation_agent.override(model=FunctionModel(script.respond))
                )
            report = dataset.evaluate_sync(task, max_concurrency=1, progress=False)
        assert not report.failures, report.failures
        results.append({name: result.value for name, result in report.cases[0].assertions.items()})
    return results


def evaluate_case(case_name: str, script: ScriptedModel) -> dict[str, bool]:
    """Evaluate one case with one script; its evaluator results by evaluation name."""
    return evaluate_cases((case_name, script))[0]


def _defibrillateurs_chain() -> list[list[tuple[str, dict]]]:
    """The three calls that reach the Nantes defibrillators."""
    return [
        [("datagouv_search_datasets", {"query": "défibrillateurs"})],
        [("datagouv_list_dataset_resources", {"dataset_id": GEODAE_DATASET_ID})],
        [
            (
                "datagouv_query_resource_data",
                {
                    "resource_id": GEODAE_RESOURCE_ID,
                    "filter_column": "c_com_nom",
                    "filter_value": "Nantes",
                },
            )
        ],
    ]


def test_available_connector_and_web_search_are_offered():
    """Every snapshot tool is offered under the connector prefix, beside web search."""
    script = ScriptedModel(turns=[])

    evaluate_case("defibrillateurs_nantes", script)

    snapshot = {tool["name"]: tool for tool in load_tool_snapshot()["tools"]}
    offered = script.offered_tools
    assert {f"datagouv_{name}" for name in snapshot} <= offered.keys()
    assert "web_search" in offered
    search = offered["datagouv_search_datasets"]
    assert search.description == snapshot["search_datasets"]["description"]
    assert search.parameters_json_schema == snapshot["search_datasets"]["parameters_json_schema"]


def test_the_available_instruction_reaches_the_model():
    """The model is told when to use the connector, not ordered to use it."""
    available = DataGouvConnector(conversation_pk=uuid4(), enabled=True, opted_in=True)
    forced = DataGouvConnector(conversation_pk=uuid4(), enabled=True, opted_in=True)
    forced.force()
    script = ScriptedModel(turns=[])

    evaluate_case("defibrillateurs_nantes", script)

    assert available.instruction() in script.instructions
    assert forced.instruction() not in script.instructions


def test_an_answered_chain_receives_the_scenario_and_passes():
    """Search, list, query: each call returns its scenario text; the case passes."""
    script = ScriptedModel(turns=_defibrillateurs_chain())

    results = evaluate_case("defibrillateurs_nantes", script)

    scenario = load_scenarios()["defibrillateurs_nantes"]
    assert script.tool_results == [
        ("datagouv_search_datasets", scenario["search_datasets"]),
        ("datagouv_list_dataset_resources", scenario["list_dataset_resources"]),
        ("datagouv_query_resource_data", scenario["query_resource_data"]),
    ]
    assert results == {"called_datagouv": True, "did_not_call_web_search": True}


def test_web_search_on_top_of_the_connector_fails_an_answered_case():
    """Doubling up on web search when data.gouv.fr answered is not allowed."""
    script = ScriptedModel(
        turns=[*_defibrillateurs_chain(), [("web_search", {"args": ["défibrillateurs Nantes"]})]]
    )

    results = evaluate_case("defibrillateurs_nantes", script)

    assert results == {"called_datagouv": True, "did_not_call_web_search": False}


def test_answering_without_the_connector_fails_an_answered_case():
    """Answering a figure from memory is what the answered cases catch."""
    results = evaluate_case("defibrillateurs_nantes", ScriptedModel(turns=[]))

    assert results == {"called_datagouv": False, "did_not_call_web_search": True}


def test_a_negative_case_passes_without_the_connector():
    """Out of DataGouv territory, not consulting the connector passes."""
    results = evaluate_case("population_allemagne", ScriptedModel(turns=[]))

    assert results == {"did_not_call_datagouv": True}


def test_consulting_the_connector_fails_a_negative_case_with_the_real_not_found():
    """An unstaged search answers like the real server, echoing the query."""
    script = ScriptedModel(
        turns=[[("datagouv_search_datasets", {"query": "population Allemagne"})]]
    )

    results = evaluate_case("population_allemagne", script)

    assert script.tool_results == [
        ("datagouv_search_datasets", "No datasets found for query: 'population Allemagne'")
    ]
    assert results == {"did_not_call_datagouv": False}


def test_every_connector_tool_answers_when_nothing_is_staged():
    """Each snapshot tool, called with only its required arguments, gets a not-found text."""
    calls = [
        (
            f"datagouv_{tool['name']}",
            dict.fromkeys(tool["parameters_json_schema"].get("required", []), "x"),
        )
        for tool in load_tool_snapshot()["tools"]
    ]
    script = ScriptedModel(turns=[calls])

    evaluate_case("population_allemagne", script)

    results = dict(script.tool_results)
    assert results.keys() == {name for name, _ in calls}
    assert all(content.strip() for content in results.values())


def test_an_attached_document_case_offers_the_connector_and_document_tools():
    """With a document attached, the connector is offered beside RAG and summarize."""
    script = ScriptedModel(turns=[[("summarize", {})]])

    results = evaluate_case("resume_document", script)

    assert "datagouv_search_datasets" in script.offered_tools
    assert {"document_search_rag", "summarize"} <= script.offered_tools.keys()
    assert results == {"did_not_call_datagouv": True, "called_document_tool": True}


def test_a_case_without_scenario_gets_not_found_after_a_scenario_case():
    """Staged results never leak from one case into the next run of the task."""
    first = ScriptedModel(turns=[_defibrillateurs_chain()[0]])
    second = ScriptedModel(turns=[[("datagouv_search_datasets", {"query": "défibrillateurs"})]])

    evaluate_cases(("defibrillateurs_nantes", first), ("population_allemagne", second))

    assert second.tool_results == [
        ("datagouv_search_datasets", "No datasets found for query: 'défibrillateurs'")
    ]


def _empty_search() -> list[tuple[str, dict]]:
    return [("datagouv_search_datasets", {"query": "ruches Dijon"})]


def _web_search() -> list[tuple[str, dict]]:
    return [("web_search", {"args": ["ruches Dijon"]})]


def test_web_search_after_an_empty_connector_is_a_fallback():
    """Connector first, found nothing, then web search: the fallback case passes."""
    script = ScriptedModel(turns=[_empty_search(), _web_search()])

    results = evaluate_case("ruches_dijon", script)

    assert script.tool_results[0] == (
        "datagouv_search_datasets",
        "No datasets found for query: 'ruches Dijon'",
    )
    assert results == {
        "called_datagouv": True,
        "called_web_search": True,
        "datagouv_before_web_search": True,
    }


def test_web_search_before_the_connector_is_not_a_fallback():
    """Consulting the connector as an afterthought fails the ordering check."""
    script = ScriptedModel(turns=[_web_search(), _empty_search()])

    results = evaluate_case("ruches_dijon", script)

    assert results == {
        "called_datagouv": True,
        "called_web_search": True,
        "datagouv_before_web_search": False,
    }


def test_web_search_without_the_connector_is_not_a_fallback():
    """Skipping the connector fails both the presence and the ordering checks."""
    results = evaluate_case("ruches_dijon", ScriptedModel(turns=[_web_search()]))

    assert results == {
        "called_datagouv": False,
        "called_web_search": True,
        "datagouv_before_web_search": False,
    }


def test_the_connector_alone_passes_the_ordering_check():
    """Without web search there is nothing to order; only the presence check fails."""
    results = evaluate_case("ruches_dijon", ScriptedModel(turns=[_empty_search()]))

    assert results == {
        "called_datagouv": True,
        "called_web_search": False,
        "datagouv_before_web_search": True,
    }


EXPECTED_EVALUATIONS = {
    "answered": {"called_datagouv", "did_not_call_web_search"},
    "stable_fact": {"called_datagouv", "did_not_call_web_search"},
    "fallback": {"called_datagouv", "called_web_search", "datagouv_before_web_search"},
    "other_country": {"did_not_call_datagouv"},
    "general_knowledge": {"did_not_call_datagouv"},
    "procedure": {"did_not_call_datagouv"},
    "writing_or_coding": {"did_not_call_datagouv"},
    "attached_document": {"did_not_call_datagouv", "called_document_tool"},
}


def test_every_case_is_well_formed():
    """Each case names a real scenario and carries its category's evaluations."""
    dataset = Command()._load_dataset(REGISTRY["datagouv_selection"], None)
    scenarios = load_scenarios()

    assert len(dataset.cases) == 23
    for case in dataset.cases:
        scenario = parse_tool_stub_responses(case.inputs.tool_output).datagouv_scenario
        assert scenario is None or scenario in scenarios, case.name
        names = {evaluator.get_default_evaluation_name() for evaluator in case.evaluators}
        assert names == EXPECTED_EVALUATIONS[case.metadata.category], case.name
