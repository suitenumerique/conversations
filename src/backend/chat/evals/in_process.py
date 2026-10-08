"""Task running a case in the eval process, the way production runs a conversation.

Each case gets a fresh ``AIAgentService`` on an unsaved conversation carrying the
case's project and history summary, so production's own setup injects the
project instructions and the summary. Attached and project files are markdown
fixtures (``<name>.md``):

- the document listing is production's (``build_documents_listing``: FIFO
  inlining, project files tool-call only), reading the fixtures instead of
  object storage;
- ``document_search_rag`` returns the full text of the documents searched: those
  not inlined in the listing (all of them when every one is inlined), or the one
  ``document_id`` names;
- ``summarize`` / ``summarize_project`` return a fixed summary per document
  (``<name>.summary.md``), whatever ``instructions`` the model passes.

Web search is the real tool when ``smart_web_search`` is on, and absent
otherwise (the production default).
"""

import functools
import re
import uuid
from pathlib import Path
from unittest.mock import patch

from django.conf import settings

from asgiref.sync import sync_to_async
from pydantic_ai import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturn,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_evals.dataset import set_eval_attribute

from chat import models as chat_models
from chat.agent_rag.constants import RAGWebResult
from chat.constants import ACCESS_FULL_CONTEXT
from chat.document_context_builder import (
    DocumentsListing,
    build_documents_listing,
    render_listing,
)
from chat.evals import EvalInputs, HistoryMessage
from chat.evals.production_agent import (
    build_production_agent_service,
    production_agent_deps,
    stub_document_search_rag,
    stub_summarize,
    stub_summarize_project,
)
from chat.evals.tool_output import capture_tool_output_from_run
from chat.llm_configuration import get_model_configuration

# Production users are French: the app passes the user's language to the agent.
EVAL_USER_LANGUAGE = "fr-fr"
_PASTE_RE = re.compile(r"\{\{paste:([\w-]+)\}\}")


class _Document:
    """A fixture document, shaped like the attachment production lists."""

    def __init__(self, documents_dir: Path, name: str):
        self.id = str(uuid.uuid4())
        self.inlined = False
        self.file_name = f"{name}.md"
        self.conversion_from = None
        self.text = (documents_dir / f"{name}.md").read_text(encoding="utf-8")
        self.summary = (documents_dir / f"{name}.summary.md").read_text(encoding="utf-8")


def expand_pastes(text: str, documents_dir: Path) -> str:
    """Replace each ``{{paste:<name>}}`` marker with the text of fixture ``<name>.md``."""
    return _PASTE_RE.sub(
        lambda match: (documents_dir / f"{match.group(1)}.md").read_text(encoding="utf-8"), text
    )


def to_model_messages(history: list[HistoryMessage], documents_dir: Path) -> list[ModelMessage]:
    """Convert a case's message history to the messages the agent receives."""
    messages: list[ModelMessage] = []
    for message in history:
        content = expand_pastes(message.content, documents_dir)
        if message.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages


def _select(documents: list[_Document], document_id: str | None) -> list[_Document]:
    if document_id is None:
        return documents
    selected = [document for document in documents if document.id == document_id]
    if not selected:
        raise ModelRetry(f"No document with document_id={document_id!r}.")
    return selected


def _rag_stub(documents: list[_Document]):
    # The model already has the inlined documents: search the others, like a top-k
    # search would mostly return them, unless every document is inlined.
    searched = [document for document in documents if not document.inlined] or documents

    def search(query: str, document_id: str | None = None) -> ToolReturn:  # pylint: disable=unused-argument
        selected = _select(documents, document_id) if document_id else searched
        results = [
            RAGWebResult(url=document.file_name, content=document.text, score=1.0)
            for document in selected
        ]
        return ToolReturn(
            return_value=results,
            content="",
            metadata={"sources": {result.url for result in results}},
        )

    return search


def _summarize_stub(documents: list[_Document], scope: str):
    def summarize(instructions: str | None = None, document_id: str | None = None):  # pylint: disable=unused-argument
        if not documents:
            # Production's message for an empty scope.
            return (
                f"No text documents found in the {scope}. "
                "You must explain this to the user and ask them to provide documents."
            )
        selected = _select(documents, document_id)
        if len(selected) == 1:
            text = selected[0].summary
        else:
            text = "\n\n".join(
                f"## {document.file_name}\n\n{document.summary}" for document in selected
            )
        return ToolReturn(
            return_value=text,
            metadata={"sources": {document.file_name for document in selected}},
        )

    return summarize


def _production_signature(service, name: str, implementation):
    """Run ``implementation`` behind the production tool's signature and docstring,
    which set the tool schema the model sees."""
    # pylint: disable=protected-access
    production = service.conversation_agent._function_toolset.tools[name].function  # noqa: SLF001

    @functools.wraps(production)
    async def stub(_ctx, *args, **kwargs):
        return implementation(*args, **kwargs)

    return stub


async def _read_fixture(document: _Document) -> tuple[str, str]:
    return document.file_name, document.text


async def _documents_listing(
    model_hrid: str, documents: list[_Document], project_documents: list[_Document]
) -> DocumentsListing | None:
    """Production's document listing, with the fixtures as attachment contents."""
    # Patching a module global around an await: fine as run_evals runs one case at a time.
    with patch("chat.document_context_builder.read_attachment_content", _read_fixture):
        listing = await build_documents_listing(
            conversation_id="eval",
            text_attachments=documents,
            project_text_attachments=project_documents,
            model_hrid=model_hrid,
            max_token_context=get_model_configuration(model_hrid).max_token_context,
            budget_ratio=settings.DOCUMENT_CONTEXT_BUDGET_RATIO,
            security_buffer_tokens=settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS,
        )
    if listing is not None:
        inlined = {
            doc.document_id for doc in listing.documents if doc.access == ACCESS_FULL_CONTEXT
        }
        for document in documents:
            document.inlined = document.id in inlined
        # Which documents the model got inline depends on the tested model's context size.
        set_eval_attribute(
            "documents",
            [
                {"title": doc.title, "access": doc.access}
                for doc in [*listing.documents, *(listing.project_documents or [])]
            ],
        )
    return listing


def _build_service(  # noqa: PLR0913  # pylint: disable=too-many-arguments
    model_hrid: str,
    inputs: EvalInputs,
    *,
    documents: list[_Document],
    project_documents: list[_Document],
    document_context_instruction: str,
    smart_web_search: bool,
):
    project = None
    if inputs.project_instructions is not None or project_documents:
        project = chat_models.ChatProject(llm_instructions=inputs.project_instructions or "")
    conversation = chat_models.ChatConversation(
        project=project, history_summary=inputs.history_summary or ""
    )
    has_documents = bool(documents or project_documents)
    service = build_production_agent_service(
        model_hrid,
        web_search_runtime_enabled=smart_web_search,
        rag_tools=has_documents,
        document_context_instruction=document_context_instruction,
        language=EVAL_USER_LANGUAGE,
        conversation=conversation,
    )
    if has_documents:
        all_documents = documents + project_documents
        stub_document_search_rag(
            service, _production_signature(service, "document_search_rag", _rag_stub(all_documents))
        )
        stub_summarize(
            service,
            _production_signature(service, "summarize", _summarize_stub(documents, "conversation")),
        )
    if project is not None and has_documents:
        stub_summarize_project(
            service,
            _production_signature(
                service, "summarize_project", _summarize_stub(project_documents, "project library")
            ),
        )
    return service


def _record_scored_turn(result, answers: list[str]) -> None:
    """Expose the scored turn's tool usage and every turn's answer to the evaluators."""
    tool_calls, sources = [], []
    for message in result.new_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                tool_calls.append({"name": part.tool_name, "args": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart) and isinstance(part.metadata, dict):
                sources.extend(sorted(part.metadata.get("sources") or []))
    set_eval_attribute("tool_calls", tool_calls)
    set_eval_attribute("turns", len(answers))
    set_eval_attribute("turn_texts", answers)
    set_eval_attribute("sources", sources)
    if (tool_output := capture_tool_output_from_run(result)) is not None:
        set_eval_attribute("tool_output", tool_output)


def make_in_process_task_fn(documents_dir: Path, *, smart_web_search: bool = False):
    """Return a TaskFactory running each case like a production conversation.

    ``smart_web_search`` is the user's opt-in for model-decided web search (off is
    the production default).
    """

    def factory(model_hrid: str):
        async def run_agent(inputs: EvalInputs) -> str:
            documents = [_Document(documents_dir, name) for name in inputs.attachments]
            project_documents = [
                _Document(documents_dir, name) for name in inputs.project_attachments
            ]
            listing = await _documents_listing(model_hrid, documents, project_documents)
            instruction = render_listing(listing) if listing is not None else ""
            # The eval user comes from the database: build in a sync thread.
            service = await sync_to_async(_build_service)(
                model_hrid,
                inputs,
                documents=documents,
                project_documents=project_documents,
                document_context_instruction=instruction,
                smart_web_search=smart_web_search,
            )
            agent, deps = service.conversation_agent, production_agent_deps(service)

            history = to_model_messages(inputs.message_history, documents_dir)
            answers: list[str] = []
            for text in (inputs.user_message, *inputs.follow_ups):
                result = await agent.run(text, deps=deps, message_history=history)
                history = result.all_messages()
                answers.append(result.output)
            _record_scored_turn(result, answers)
            return answers[-1]

        return run_agent

    return factory
