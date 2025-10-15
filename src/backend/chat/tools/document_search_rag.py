"""Tool to perform a document search using Albert RAG API."""

from django.conf import settings
from django.utils.module_loading import import_string

from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.messages import ToolReturn


def add_document_rag_search_tool(agent: Agent) -> None:
    """Add the document RAG tool to an existing agent."""

    @agent.tool
    def document_search_rag(ctx: RunContext, query: str) -> ToolReturn:
        """
        Perform a search in the documents provided by the user.
        Must be used whenever the user asks for information that
        is not in the model's knowledge base and most of the time.
        The query must contain all information to find accurate results.

        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The query to search the documents for.
        """
        # Defensive: ctx.deps or ctx.deps.conversation may be unavailable in some flows (start of conversation)
        if not getattr(ctx, "deps", None) or not getattr(ctx.deps, "conversation", None):
            return ToolReturn(return_value=[], content="", metadata={"sources": set()})

        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        document_store = document_store_backend(ctx.deps.conversation.collection_id)

        rag_results = document_store.search(query)

        ctx.usage += RunUsage(
            input_tokens=rag_results.usage.prompt_tokens,
            output_tokens=rag_results.usage.completion_tokens,
        )

        return ToolReturn(
            return_value=rag_results.data,
            content="",
            metadata={"sources": {result.url for result in rag_results.data}},
        )

    @agent.system_prompt
    def document_rag_instructions() -> str:
        """Dynamic system prompt function to add RAG instructions if any."""
        return (
            "Use document_search_rag ONLY to retrieve specific passages from attached documents. "
            "Do NOT use it to summarize; for summaries, call the summarize tool instead."
        )
