"""Tool to perform a document search using the configured RAG backend."""

import logging

from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.messages import ToolReturn

from chat.agent_rag.rag_collections import index_missing_attachments
from chat.tools.descriptions import (
    DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT,
    DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION,
)

logger = logging.getLogger(__name__)


def add_document_rag_search_tool(agent: Agent) -> None:
    """Add the document RAG tool to an existing agent."""

    @agent.tool(description=DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION)
    def document_search_rag(ctx: RunContext, query: str) -> ToolReturn:
        """
        Search indexed conversation documents using the configured RAG backend.

        Ensures all conversation attachments are indexed in the current backend
        before searching (handles backend switches transparently).

        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The query to search the documents for.
        """
        collection, document_store = index_missing_attachments(
            ctx.deps.conversation,
            user_sub=ctx.deps.user.sub,
        )

        if not collection:
            return ToolReturn(
                return_value=[],
                content="",
                metadata={"sources": set()},
            )

        rag_results = document_store.search(query, session=ctx.deps.session)

        ctx.usage += RunUsage(
            input_tokens=rag_results.usage.prompt_tokens,
            output_tokens=rag_results.usage.completion_tokens,
        )

        return ToolReturn(
            return_value=rag_results.data,
            content="",
            metadata={"sources": {result.url for result in rag_results.data}},
        )

    @agent.instructions
    def document_rag_instructions() -> str:
        """Dynamic system prompt function to add RAG instructions if any."""
        return DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT
