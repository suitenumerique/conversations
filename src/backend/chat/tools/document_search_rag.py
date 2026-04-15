"""Tool to perform a document search using Albert RAG API."""

from django.conf import settings
from django.utils.module_loading import import_string

from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.messages import ToolReturn

from chat.tools.descriptions import (
    DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT,
    DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION,
)


def add_document_rag_search_tool(agent: Agent) -> None:
    """Add the document RAG tool to an existing agent."""

    @agent.tool(description=DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION)
    def document_search_rag(ctx: RunContext, query: str) -> ToolReturn:
        """
        Search indexed conversation documents using the configured RAG backend.

        This function queries the conversation collection associated with
        ``ctx.deps.conversation.collection_id`` and returns retrieved chunks.
        The query should be self-contained to maximize retrieval quality.

        Side effects:
            - Updates ``ctx.usage`` with token usage reported by the backend.

        Returns:
            ToolReturn: Retrieved passages in ``return_value`` and source URLs in
            ``metadata["sources"]``.

        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The query to search the documents for.
        """
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        document_store = document_store_backend(ctx.deps.conversation.collection_id)

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
