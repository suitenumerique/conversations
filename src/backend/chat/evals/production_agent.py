"""Build eval agents with the same tool wiring as production AIAgentService.

Tool implementations may be stubbed (no DB / external APIs), but instructions and
tool descriptions are registered via the production setup methods in
``chat.clients.pydantic_ai``.
"""

# ruff: noqa: SLF001
# pylint: disable=protected-access

from __future__ import annotations

from collections.abc import Awaitable, Callable

from django.contrib.auth.hashers import make_password

from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import Tool

from core.models import User

from chat import models as chat_models
from chat.clients.pydantic_ai import AIAgentService
from chat.clients.schema import ContextDeps
from chat.document_context_builder import (
    TOOL_CALL_ONLY_CONTENT,
    DocumentInfo,
    DocumentsListing,
    render_listing,
)
from chat.evals.tool_stub_responses import get_current_tool_stubs
from chat.tools.descriptions import WEB_SEARCH_TOOL_DESCRIPTION

EVAL_FAKE_DOCUMENT_ID = "00000000-0000-4000-8000-000000000001"

EVAL_FAKE_DOCUMENT_LISTING = render_listing(
    DocumentsListing(
        documents=[
            DocumentInfo(
                document_id=EVAL_FAKE_DOCUMENT_ID,
                title="rapport-eval.pdf",
                access="tool_call_only",
                content=TOOL_CALL_ONLY_CONTENT,
                info="first_uploaded_document",
            )
        ],
        note=(
            "Documents marked 'tool_call_only' are accessible through tools like "
            "RAG search or summary. "
        ),
    )
)

_EVAL_USER_SUB = "eval-production-agent-session"
_EVAL_CONVERSATION_TITLE = "eval-session"

EVAL_SESSION_USER: User | None = None
EVAL_SESSION_CONVERSATION: chat_models.ChatConversation | None = None


def reset_eval_session_cache() -> None:
    """Clear eval-session globals so tests rebuild fresh ORM objects."""
    global EVAL_SESSION_USER, EVAL_SESSION_CONVERSATION  # noqa: PLW0603  # pylint: disable=global-statement
    EVAL_SESSION_USER = None
    EVAL_SESSION_CONVERSATION = None


def _get_eval_session_user() -> User:
    """Return a single eval user reused for the lifetime of the Python process."""
    global EVAL_SESSION_USER  # pylint: disable=global-statement
    if EVAL_SESSION_USER is not None:
        return EVAL_SESSION_USER

    EVAL_SESSION_USER, _ = User.objects.get_or_create(
        sub=_EVAL_USER_SUB,
        defaults={
            "email": "eval-session@localhost",
            "full_name": "Eval Session",
            "allow_smart_web_search": True,
            "password": make_password(None),
        },
    )
    return EVAL_SESSION_USER


def _get_eval_session_conversation(user: User) -> chat_models.ChatConversation:
    """Return a single conversation for the eval session user."""
    global EVAL_SESSION_CONVERSATION  # pylint: disable=global-statement
    if EVAL_SESSION_CONVERSATION is not None:
        return EVAL_SESSION_CONVERSATION

    EVAL_SESSION_CONVERSATION, _ = chat_models.ChatConversation.objects.get_or_create(
        owner=user,
        title=_EVAL_CONVERSATION_TITLE,
    )
    return EVAL_SESSION_CONVERSATION


def build_production_agent_service(
    model_hrid: str,
    *,
    web_search_runtime_enabled: bool | None = None,
    rag_tools: bool = False,
    document_context_instruction: str = "",
) -> AIAgentService:
    """Return an AIAgentService configured like a production agent run.

    Mirrors the per-turn setup in ``AIAgentService._run_agent`` for a
    conversation without attached documents (``rag_tools=False``) or with
    documents available for RAG (``rag_tools=True``).
    """
    user = _get_eval_session_user()
    conversation = _get_eval_session_conversation(user)
    service = AIAgentService(conversation, user=user, model_hrid=model_hrid)

    service._setup_self_documentation_tool()
    service._setup_web_search_tool()

    if web_search_runtime_enabled is not None:
        service._context_deps.web_search_enabled = web_search_runtime_enabled
    elif service._is_web_search_enabled and service._is_smart_search_enabled:
        service._context_deps.web_search_enabled = True

    if rag_tools:
        service._setup_rag_tools(document_context_instruction=document_context_instruction)

    return service


def production_agent_deps(service: AIAgentService) -> ContextDeps:
    """Return context deps to pass to ``agent.run()`` (same as production)."""
    return service._context_deps


def _replace_tool(
    service: AIAgentService,
    name: str,
    implementation: Callable[..., Awaitable[ToolReturn]],
) -> None:
    toolset = service.conversation_agent._function_toolset
    existing = toolset.tools[name]
    toolset.tools[name] = Tool(
        implementation,
        name=name,
        description=existing.description,
        max_retries=existing.max_retries,
        prepare=existing.prepare,
        takes_ctx=existing.takes_ctx,
    )


def ensure_web_search_registered(service: AIAgentService) -> None:
    """Register a stub ``web_search`` tool when the model config has no web search."""
    if "web_search" in service.conversation_agent._function_toolset.tools:
        return

    async def only_if_web_search_enabled(ctx, tool_def):
        return tool_def if ctx.deps.web_search_enabled else None

    async def web_search(_ctx: RunContext, *args, **kwargs) -> ToolReturn:
        return get_current_tool_stubs().web_search_return()

    service.conversation_agent._function_toolset.tools["web_search"] = Tool(
        web_search,
        name="web_search",
        description=WEB_SEARCH_TOOL_DESCRIPTION,
        max_retries=1,
        prepare=only_if_web_search_enabled,
        takes_ctx=True,
    )
    service._web_search_tool_registered = True


def stub_web_search(
    service: AIAgentService,
    implementation: Callable[..., Awaitable[ToolReturn]],
) -> None:
    """Replace ``web_search`` implementation after production registration."""
    ensure_web_search_registered(service)
    _replace_tool(service, "web_search", implementation)


def stub_document_search_rag(
    service: AIAgentService,
    implementation: Callable[..., Awaitable[ToolReturn]],
) -> None:
    """Replace ``document_search_rag`` implementation after production registration."""
    _replace_tool(service, "document_search_rag", implementation)


def stub_summarize(
    service: AIAgentService,
    implementation: Callable[..., Awaitable[ToolReturn]],
) -> None:
    """Replace ``summarize`` implementation after production registration."""
    _replace_tool(service, "summarize", implementation)
