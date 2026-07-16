"""Tool to perform a document search using Albert RAG API."""

from django.conf import settings
from django.utils.module_loading import import_string

from asgiref.sync import sync_to_async
from pydantic_ai import Agent, RunContext, RunUsage
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from chat.constants import TEXT_MIME_PREFIX
from chat.tools.descriptions import (
    DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT,
    DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION,
)
from chat.tools.utils import resolve_attachment_by_id


def add_document_rag_search_tool(agent: Agent) -> None:
    """Add the document RAG tool to an existing agent."""

    @agent.tool(description=DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION)
    async def document_search_rag(
        ctx: RunContext,
        query: str,
        document_id: str | None = None,
    ) -> ToolReturn:
        # pylint: disable=line-too-long
        """
        Search indexed documents using the configured RAG backend.

        Searches the conversation's own collection and, when the conversation
        belongs to a project, the project's collection (read-only) so files
        shared at the project level are visible to every conversation in it.

        When ``document_id`` is provided, the search is scoped to a single
        attachment - resolved against this conversation's text attachments
        and, when applicable, the parent project's text attachments.

        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The query to search the documents for.
            document_id (str | None): Optional document filter, attachment UUID from context.

        Examples:
        user : "Based on the report, what is the deadline?"
        query : "what is the deadline?"
        document_id : id_from_context
        """
        # pylint: enable=line-too-long
        document_store_backend = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        conversation = ctx.deps.conversation
        project = getattr(conversation, "project", None)
        read_only_collection_id = (
            [project.collection_id] if project and project.collection_id else None
        )
        document_store = document_store_backend(
            conversation.collection_id,
            read_only_collection_id=read_only_collection_id,
        )

        document_name: str | None = None
        rag_document_id: str | None = None
        if document_id is not None:
            conv_attachments = await sync_to_async(list)(
                conversation.attachments.filter(content_type__startswith=TEXT_MIME_PREFIX).order_by(
                    "created_at", "id"
                )
            )
            project_attachments: list = []
            if project is not None:
                project_attachments = await sync_to_async(list)(
                    project.attachments.filter(content_type__startswith=TEXT_MIME_PREFIX).order_by(
                        "created_at", "id"
                    )
                )
            selected_attachment = resolve_attachment_by_id(
                conv_attachments + project_attachments, document_id
            )

            # Converted attachments are stored as markdown blobs (e.g. "report.pdf.md")
            # while RAG metadata keeps the original file name (e.g. "report.pdf").
            if getattr(selected_attachment, "conversion_from", None):
                document_name = selected_attachment.file_name.removesuffix(".md")
            else:
                document_name = selected_attachment.file_name

            # Albert prefers `document_id` over `document_name` when both are sent.
            rag_document_id = selected_attachment.rag_document_id

        rag_results = await document_store.asearch(
            query,
            session=ctx.deps.session,
            document_name=document_name,
            document_id=rag_document_id,
        )

        ctx.usage += RunUsage(
            input_tokens=rag_results.usage.prompt_tokens,
            output_tokens=rag_results.usage.completion_tokens,
        )

        if document_id is not None and not rag_results.data:
            raise ModelRetry(
                f"No results found in document filtered by document_id={document_id!r}. "
                "If the user's question was not specific to this document, retry "
                "document_search_rag with the same query but WITHOUT document_id to "
                "search across the full collection. In that case, your final answer "
                "to the user MUST explicitly state that the targeted document did "
                "not contain the requested information and that you broadened the "
                "search to the full collection. "
                "If the question was specific to this document, do not retry - "
                "inform the user that this document does not contain the requested "
                "information."
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
