"""Eval config: tool selection behaviour (web_search, self_documentation, RAG, summarize)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic_ai import RunContext, Tool

from chat.clients.pydantic_ai import AIAgentService
from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.production_agent import (
    EVAL_FAKE_DOCUMENT_LISTING,
    build_production_agent_service,
    production_agent_deps,
    stubbed_tools,
)
from chat.evals.tool_stub_responses import (
    get_current_tool_stubs,
    parse_tool_stub_responses,
    reset_current_tool_stubs,
    set_current_tool_stubs,
)

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "tool_selection.yaml"


def _stub_web_search(_ctx: RunContext, *args, **kwargs):
    return get_current_tool_stubs().web_search_return()


def _stub_document_search_rag(_ctx: RunContext, **_kwargs):
    return get_current_tool_stubs().document_search_rag_return()


def _stub_summarize(_ctx: RunContext, **_kwargs):
    return get_current_tool_stubs().summarize_return()


def _build_cached_service(
    model_hrid: str, *, requires_documents: bool
) -> tuple[AIAgentService, list[Tool]]:
    """Production service and its function tools with the stubs swapped in."""
    service = build_production_agent_service(
        model_hrid,
        rag_tools=requires_documents,
        document_context_instruction=EVAL_FAKE_DOCUMENT_LISTING if requires_documents else "",
        web_search_runtime_enabled=True,
    )
    stubs = {"web_search": _stub_web_search}
    if requires_documents:
        stubs |= {
            "document_search_rag": _stub_document_search_rag,
            "summarize": _stub_summarize,
        }
    return service, stubbed_tools(service, stubs)


def make_tool_selection_task_fn(model_hrid: str):
    """Build the task function with per-case document context and stubbed tools."""
    # Build agents in sync context — Django ORM cannot run inside async run_agent.
    services = {
        False: _build_cached_service(model_hrid, requires_documents=False),
        True: _build_cached_service(model_hrid, requires_documents=True),
    }

    async def run_agent(inputs: EvalInputs) -> str:
        stubs = parse_tool_stub_responses(inputs.tool_output)
        token = set_current_tool_stubs(stubs)
        service, tools = services[inputs.requires_documents]
        agent = service.conversation_agent
        deps = production_agent_deps(service)
        deps.web_search_enabled = True
        try:
            with (
                patch(
                    "chat.tools.self_documentation.load_db_self_documentation",
                    new_callable=AsyncMock,
                    return_value=stubs.self_documentation_db_text(),
                ),
                agent.override(tools=tools),
            ):
                # message_history=[] keeps each case isolated: the eval session
                # reuses one conversation, so never replay a prior case's turns.
                return (await agent.run(inputs.user_message, deps=deps, message_history=[])).output
        finally:
            reset_current_tool_stubs(token)

    return run_agent


TOOL_SELECTION = EvalConfig(
    name="tool_selection",
    dataset_path=_DATASET_PATH,
    make_task_fn=make_tool_selection_task_fn,
)
