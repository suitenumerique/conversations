"""Tool to perform a document search using Albert RAG API."""

import logging

from django.conf import settings
from django.utils.module_loading import import_string

from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.messages import ToolReturn

from chat.agent_rag.indexing import (
    ensure_project_attachments_indexed,
    get_conversation_collection,
    get_project_collection,
    reindex_collection,
)
from chat.agent_rag.document_rag_backends.registry import get_backend_key

logger = logging.getLogger(__name__)


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
        current_key = get_backend_key(settings.RAG_DOCUMENT_SEARCH_BACKEND)
        conversation = ctx.deps.conversation

        # -- conversation collection --
        collection = get_conversation_collection(conversation)

        if not collection:
            # Check if a collection exists for another backend (needs re-index)
            collection = conversation.collections.first()

        if collection and collection.backend != current_key:
            collection = reindex_collection(
                conversation,
                user_sub=ctx.deps.user.sub,
            )

        # -- project collection (read-only, searched alongside conversation docs) --
        project_collection_ids = []
        project = getattr(conversation, "project", None)
        if project:
            ensure_project_attachments_indexed(project, user_sub=ctx.deps.user.sub)
            project_col = get_project_collection(project)
            if project_col and project_col.external_id:
                project_collection_ids.append(project_col.external_id)

        # If no collections are available, return empty results
        if not collection and not project_collection_ids:
            return ToolReturn(
                return_value=[],
                content="No documents are available for search yet.",
                metadata={"sources": set()},
            )

        if collection:
            backend_class = collection.get_backend_class()
        else:
            backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        document_store = backend_class(
            collection_id=collection.external_id if collection else None,
            read_only_collection_id=project_collection_ids or None,
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
        return (
            "Use document_search_rag ONLY to retrieve specific passages from attached documents. "
            "Do NOT use it to summarize; for summaries, call the summarize tool instead."
        )
