"""Eval config: does the assistant consult an Available data.gouv.fr connector when it should."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.configs.tool_selection import build_tool_selection_service
from chat.evals.datagouv_connector import build_datagouv_toolset
from chat.evals.evaluators import CalledTool, DidNotCallTool, ToolCalledBefore
from chat.evals.production_agent import production_agent_deps
from chat.evals.tool_stub_responses import (
    parse_tool_stub_responses,
    reset_current_tool_stubs,
    set_current_tool_stubs,
)

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "datagouv_selection.yaml"


def make_datagouv_selection_task_fn(model_hrid: str):
    """Build the task function: production tools stubbed, the connector passed per run."""
    # Build agents in sync context — Django ORM cannot run inside async run_agent.
    services = {
        False: build_tool_selection_service(model_hrid, requires_documents=False),
        True: build_tool_selection_service(model_hrid, requires_documents=True),
    }
    datagouv_toolset = build_datagouv_toolset()

    async def run_agent(inputs: EvalInputs) -> str:
        stubs = parse_tool_stub_responses(inputs.tool_output)
        token = set_current_tool_stubs(stubs)
        service = services[inputs.requires_documents]
        deps = production_agent_deps(service)
        deps.web_search_enabled = True
        try:
            with patch(
                "chat.tools.self_documentation.load_db_self_documentation",
                new_callable=AsyncMock,
                return_value=stubs.self_documentation_db_text(),
            ):
                # Connector toolsets reach the run per turn, as in production's
                # _run_agent; message_history=[] keeps each case isolated.
                result = await service.conversation_agent.run(
                    inputs.user_message,
                    deps=deps,
                    message_history=[],
                    toolsets=[datagouv_toolset],
                )
                return result.output
        finally:
            reset_current_tool_stubs(token)

    return run_agent


DATAGOUV_SELECTION = EvalConfig(
    name="datagouv_selection",
    dataset_path=_DATASET_PATH,
    dataset_evaluator_types=[
        CalledTool,
        DidNotCallTool,
        ToolCalledBefore,
    ],
    make_task_fn=make_datagouv_selection_task_fn,
)
