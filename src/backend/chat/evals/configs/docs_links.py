"""Eval config: how the agent uses pasted La Suite Docs links.

Each case lists the Docs links pasted in the user message and what reading them
returned. The agent gets the production notes (``chat.docs_snapshots``) and, for
read links, the attached snapshot in the production document listing. The stub
RAG and summarize tools return the snapshot content of the case.
"""

# pylint: disable=protected-access

import contextvars
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from django.test import override_settings

from pydantic_ai import RunContext
from pydantic_evals.evaluators import Contains, HasMatchingSpan

from chat.clients.pydantic_ai import AIAgentService
from chat.constants import ACCESS_FULL_CONTEXT
from chat.docs_client import DocsFetchFailure, docs_document_url, safe_file_stem
from chat.docs_snapshots import docs_failure_note, docs_read_note
from chat.document_context_builder import (
    TOOL_CALL_ONLY_CONTENT,
    _assemble_documents_listing,
    _DocumentEntry,
    _info_label_for,
    render_listing,
)
from chat.evals import EvalInputs
from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import HasNoMatchingSpan
from chat.evals.production_agent import (
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

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "docs_links.yaml"

# Fixed so the case URLs do not depend on the eval environment.
DOCS_BASE_URL = "https://docs.example.org/"
_DOCS_LINKS_NAMESPACE = uuid.UUID("6f1c2b1e-3d4a-4c5e-9f00-d0c5d0c5d0c5")

_CURRENT_DOCS_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "eval_docs_links_context", default=""
)


def docs_link_document_id(index: int) -> uuid.UUID:
    """Return the fixed Docs document id of the ``index``-th link of a case."""
    return uuid.uuid5(_DOCS_LINKS_NAMESPACE, f"docs-link-{index}")


@override_settings(DOCS_BASE_URL=DOCS_BASE_URL)
def build_docs_links_case(inputs: EvalInputs) -> tuple[str, str]:
    """Return the user message and the instructions of a case.

    ``{link0}``, ``{link1}``… in the user message are replaced by the Docs URLs.
    """
    urls = {
        f"link{index}": docs_document_url(docs_link_document_id(index))
        for index in range(len(inputs.docs_links))
    }
    notes = []
    entries = []
    for index, link in enumerate(inputs.docs_links):
        document_id = docs_link_document_id(index)
        if link.outcome != "read":
            notes.append(docs_failure_note(document_id, DocsFetchFailure(link.outcome)))
            continue
        file_name = f"{safe_file_stem(link.title)}.md"
        notes.append(docs_read_note(document_id, file_name))
        inlined = link.access == ACCESS_FULL_CONTEXT
        entries.append(
            _DocumentEntry(
                document_id=str(uuid.uuid5(document_id, "attachment")),
                title=file_name,
                content=(link.content or "") if inlined else TOOL_CALL_ONLY_CONTENT,
                token_count=0,
                inlineable=inlined,
                access=link.access,
            )
        )

    for position, entry in enumerate(entries, start=1):
        entry.info = _info_label_for(position, len(entries))
    instructions = "\n".join(notes)
    if entries:
        listing = render_listing(_assemble_documents_listing(entries, force_tool_call_only=False))
        instructions = f"{listing}\n\n{instructions}"
    return inputs.user_message.format(**urls), instructions


def _build_service(model_hrid: str, *, with_snapshots: bool) -> AIAgentService:
    """Production wiring; RAG tools are only registered when a link was read."""
    service = build_production_agent_service(
        model_hrid, rag_tools=with_snapshots, web_search_runtime_enabled=True
    )

    @service.conversation_agent.instructions
    def docs_links_note() -> str:
        """Inject the listing and the Docs notes of the current case."""
        return _CURRENT_DOCS_CONTEXT.get()

    def stub_web_search_impl(_ctx: RunContext, *args, **kwargs):
        return get_current_tool_stubs().web_search_return()

    stub_web_search(service, stub_web_search_impl)

    if with_snapshots:

        def stub_rag_impl(_ctx: RunContext, _query: str, _document_id: str | None = None):
            return get_current_tool_stubs().document_search_rag_return()

        def stub_summarize_impl(_ctx: RunContext, **_kwargs):
            return get_current_tool_stubs().summarize_return()

        stub_document_search_rag(service, stub_rag_impl)
        stub_summarize(service, stub_summarize_impl)

    return service


def make_docs_links_task_fn(model_hrid: str):
    """Build the task function with the per-case Docs notes and stubbed tools."""
    # Build agents in sync context — Django ORM cannot run inside async run_agent.
    services = {
        False: _build_service(model_hrid, with_snapshots=False),
        True: _build_service(model_hrid, with_snapshots=True),
    }

    async def run_agent(inputs: EvalInputs) -> str:
        user_message, instructions = build_docs_links_case(inputs)
        contents = [link.content or "" for link in inputs.docs_links if link.outcome == "read"]
        stubs = parse_tool_stub_responses(inputs.tool_output)
        if contents:
            stubs.document_search_rag = stubs.document_search_rag or "\n\n".join(contents)
            stubs.summarize = stubs.summarize or "\n\n".join(contents)
        stubs_token = set_current_tool_stubs(stubs)
        context_token = _CURRENT_DOCS_CONTEXT.set(instructions)
        service = services[bool(contents)]
        deps = production_agent_deps(service)
        deps.web_search_enabled = True
        try:
            with patch(
                "chat.tools.self_documentation.load_db_self_documentation",
                new_callable=AsyncMock,
                return_value=stubs.self_documentation_db_text(),
            ):
                # message_history=[] keeps each case isolated: the eval session
                # reuses one conversation, so never replay a prior case's turns.
                result = await service.conversation_agent.run(
                    user_message, deps=deps, message_history=[]
                )
                return result.output
        finally:
            _CURRENT_DOCS_CONTEXT.reset(context_token)
            reset_current_tool_stubs(stubs_token)

    return run_agent


DOCS_LINKS = EvalConfig(
    name="docs_links",
    dataset_path=_DATASET_PATH,
    dataset_evaluator_types=[Contains, HasMatchingSpan, HasNoMatchingSpan],
    make_task_fn=make_docs_links_task_fn,
)
