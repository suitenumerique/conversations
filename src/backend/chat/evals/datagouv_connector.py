"""The data.gouv.fr connector as the eval agent sees it: snapshot tools, staged results.

The tool definitions are a snapshot of what the real server publishes, captured
through pydantic_ai's MCP client, so the model is offered exactly what production
offers it (see the evals README to refresh it). Results come from named scenarios
of real, trimmed responses, staged per case; a tool the case did not stage answers
with the server's own "nothing found" text, which is what fallback cases rely on.

The toolset is wrapped like production's, so the prefix and the instruction for an
Available connector are production code, read at run time.
"""

import json
from collections import defaultdict
from functools import cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets import FunctionToolset

from chat.evals.tool_stub_responses import get_current_tool_stubs
from chat.mcp_servers import ConnectorToolset, DataGouvConnector

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The real server's answers when nothing matches, captured from data.gouv.fr MCP
# server 1.28.1. Placeholders are filled from the call's own arguments; one the
# call did not pass is left empty, as the server would.
NOT_FOUND_RESULTS = {
    "search_datasets": "No datasets found for query: '{query}'",
    "search_organizations": "No organizations found for query '{query}'",
    "search_dataservices": "No third-party APIs found for query: '{query}'",
    "get_dataservice_info": (
        "Error: Third-party API not found (dataservice_id='{dataservice_id}')."
    ),
    "get_dataservice_openapi_spec": (
        "Error: Third-party API not found (dataservice_id='{dataservice_id}')."
    ),
    "query_resource_data": (
        "Querying resource: Unknown\nResource ID: {resource_id}\n\n"
        "⚠️  This resource ID was not found in the Tabular API. Use search_datasets to find "
        "a dataset, then list_dataset_resources to obtain the correct resource ID."
    ),
    "get_dataset_info": "Error: Dataset with ID '{dataset_id}' not found.",
    "list_dataset_resources": (
        "Error: 404 Client Error: Not Found for url: "
        "https://www.data.gouv.fr/api/1/datasets/{dataset_id}/"
    ),
    "get_resource_info": (
        "Error: HTTP 404 - 404 Client Error: Not Found for url: "
        "https://www.data.gouv.fr/api/2/datasets/resources/{resource_id}/"
    ),
    "get_metrics": (
        "Dataset Metrics\nDataset ID: {dataset_id}\n\nNo metrics available for this dataset."
    ),
}


@cache
def load_tool_snapshot() -> dict[str, Any]:
    """The server's name, version and tool definitions, as captured."""
    return json.loads((_FIXTURES / "datagouv_tools.json").read_text(encoding="utf-8"))


@cache
def load_scenarios() -> dict[str, dict[str, str]]:
    """Scenario name to the text each (unprefixed) tool returns in it."""
    return yaml.safe_load((_FIXTURES / "datagouv_scenarios.yaml").read_text(encoding="utf-8"))


def datagouv_tool_result(tool_name: str, arguments: dict[str, Any]) -> str:
    """What a connector tool returns for the case being evaluated.

    Matches on the tool name only, never on arguments: the eval measures routing,
    not how well the model words its search.
    """
    scenario_name = get_current_tool_stubs().datagouv_scenario
    if scenario_name is not None:
        scenario = load_scenarios()[scenario_name]
        if tool_name in scenario:
            return scenario[tool_name]
    return NOT_FOUND_RESULTS[tool_name].format_map(defaultdict(str, arguments))


def _stub(tool_name: str):
    def call(**arguments: Any) -> str:
        return datagouv_tool_result(tool_name, arguments)

    return call


def build_datagouv_toolset() -> ConnectorToolset:
    """The connector's toolset for an Available connector, wrapped as production wraps it."""
    connector = DataGouvConnector(conversation_pk=uuid4(), enabled=True, opted_in=True)
    tools = [
        Tool.from_schema(
            _stub(tool["name"]),
            name=tool["name"],
            description=tool["description"],
            json_schema=tool["parameters_json_schema"],
        )
        for tool in load_tool_snapshot()["tools"]
    ]
    return ConnectorToolset(
        FunctionToolset(tools).prefixed(connector.connector_id),
        connector.record_call_outage,
        connector.instruction,
    )
