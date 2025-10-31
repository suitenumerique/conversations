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
            query (str): The term to search the internet for.
        """
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
            metadata={"sources": [result.url for result in rag_results.data]},
        )

    @agent.system_prompt
    def document_rag_instructions() -> str:
        """Dynamic system prompt function to add RAG instructions if any."""
        return (
            "If the user wants specific information from a document, invoke "
            "web_search_albert_rag with an appropriate query string."
            "Do not ask the user for the document; rely on the tool to locate "
            "and return relevant passages."
        )
