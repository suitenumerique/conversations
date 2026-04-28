"""Tool to perform a document search using Albert RAG API."""

import uuid

from django.conf import settings
from django.utils.module_loading import import_string

from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from chat.tools.descriptions import (
    DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT,
    DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION,
)


def add_document_rag_search_tool(agent: Agent) -> None:
    """Add the document RAG tool to an existing agent."""

    @agent.tool(description=DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION)
    def document_search_rag(
        ctx: RunContext,
        query: str,
        document_id: str | None = None,
    ) -> ToolReturn:
        # pylint: disable=line-too-long
        """
        Search indexed conversation documents using the configured RAG backend.

        This function queries the conversation collection associated with
        ``ctx.deps.conversation.collection_id`` and returns retrieved chunks.
        The query should be self-contained to maximize retrieval quality.

        When ``document_id`` is provided, search is filtered to a single
        text attachment by UUID.

        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The query to search the documents for.
            document_id (str | None): Optional document filter, attachment UUID from context.

        Examples:
        user : "Based on the X, answer the question"
        query : "question"
        document_id : id_from_context
        """
        # pylint: enable=line-too-long
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        document_store = document_store_backend(ctx.deps.conversation.collection_id)
        document_name = None
        if document_id is not None:
            text_attachments = list(
                ctx.deps.conversation.attachments.filter(content_type__startswith="text/").order_by(
                    "created_at", "id"
                )
            )
            try:
                parsed_document_id = uuid.UUID(document_id)
            except ValueError as exc:
                raise ModelRetry("Invalid document_id. Expected a valid UUID.") from exc
            selected_attachment = next(
                (
                    attachment
                    for attachment in text_attachments
                    if getattr(attachment, "id", None) == parsed_document_id
                    or str(getattr(attachment, "id", "")) == document_id
                ),
                None,
            )
            if selected_attachment is None:
                raise ModelRetry("document_id was not found among attached text documents.")

            # Converted attachments are stored as markdown blobs (e.g. "report.pdf.md")
            # while RAG metadata keeps the original file name (e.g. "report.pdf").
            if getattr(selected_attachment, "conversion_from", None):
                document_name = selected_attachment.file_name.removesuffix(".md")
            else:
                document_name = selected_attachment.file_name

        rag_results = document_store.search(
            query,
            session=ctx.deps.session,
            document_name=document_name,
        )

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
