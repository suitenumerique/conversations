"""Eval config: tool selection behaviour (web_search, self_documentation, RAG, summarize)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic_ai import RunContext
from pydantic_evals.evaluators import HasMatchingSpan

from chat.clients.pydantic_ai import AIAgentService
from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import HasNoMatchingSpan
from chat.evals.production_agent import (
    EVAL_FAKE_DOCUMENT_LISTING,
    build_production_agent_service,
    production_agent_deps,
    stub_document_search_rag,
    stub_summarize,
    stub_web_search,
)
from chat.evals.tool_stub_responses import (
    get_current_tool_stubs,
    parse_tool_stub_responses,
    reset_current_tool_stubs,
    set_current_tool_stubs,
)

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "tool_selection.yaml"


def _build_cached_service(model_hrid: str, *, requires_documents: bool) -> AIAgentService:
    service = build_production_agent_service(
        model_hrid,
        rag_tools=requires_documents,
        document_context_instruction=EVAL_FAKE_DOCUMENT_LISTING if requires_documents else "",
        web_search_runtime_enabled=True,
    )

    def stub_web_search_impl(_ctx: RunContext, *args, **kwargs):
        return get_current_tool_stubs().web_search_return()

    stub_web_search(service, stub_web_search_impl)

    if requires_documents:

        def stub_rag_impl(_ctx: RunContext, _query: str, _document_id: str | None = None):
            return get_current_tool_stubs().document_search_rag_return()

        def stub_summarize_impl(_ctx: RunContext, **_kwargs):
            return get_current_tool_stubs().summarize_return()

        stub_document_search_rag(service, stub_rag_impl)
        stub_summarize(service, stub_summarize_impl)

    return service


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
        service = services[inputs.requires_documents]
        agent = service.conversation_agent
        deps = production_agent_deps(service)
        deps.web_search_enabled = True
        try:
            with patch(
                "chat.tools.self_documentation.load_db_self_documentation",
                new_callable=AsyncMock,
                return_value=stubs.self_documentation_db_text(),
            ):
                return (await agent.run(inputs.user_message, deps=deps)).output
        finally:
            reset_current_tool_stubs(token)

    return run_agent


TOOL_SELECTION = EvalConfig(
    name="tool_selection",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric=None,
    dataset_evaluator_types=[HasMatchingSpan, HasNoMatchingSpan],
    make_task_fn=make_tool_selection_task_fn,
)
