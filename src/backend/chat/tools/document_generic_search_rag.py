"""
Helpers to add RAG document search tools to an agent based on settings.

The purpose is to provide a generic way to add multiple RAG document search tools
to an agent based on configuration in settings. Each tool can target specific
document collections and have its own description.

Our use case implies that different users might have access to different document collections,
so the tools added to the agent are also user-specific.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.module_loading import import_string

from httpx import HTTPStatusError
from pydantic_ai import Agent, ModelRetry, RunContext, RunUsage
from pydantic_ai.messages import ToolReturn

from core.feature_flags.helpers import is_feature_enabled

from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)

User = get_user_model()


def get_specific_rag_search_tool_config(user: User) -> dict:
    """
    Get the specific RAG search tool configuration from settings.

    Settings example:
    SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS = {
        "french_public_services": {
            "collection_ids": [784, 785],
            "feature_flag_value": "disabled",
            "tool_description": (
                "Use this tool when the user asks for information about French public services, "
                "the French labor market, employment laws, social benefits, or "
                "assistance with administrative procedures."
            ),
        },
    }
    """
    return {
        tool_name: tool_config
        for tool_name, tool_config in settings.SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS.items()
        if is_feature_enabled(user, tool_name)
    }


def _create_document_search_rag(agent, name, description, backend, ids):
    """Factory function to create a document search RAG tool."""

    @agent.tool(
        name=name,
        retries=1,
        require_parameter_descriptions=True,
        description=description,
    )
    @last_model_retry_soft_fail
    async def document_search_rag(ctx: RunContext, query: str) -> ToolReturn:
        """
        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The query to search information about.
        """
        document_store = backend(read_only_collection_id=ids)

        try:
            rag_results = await document_store.asearch(query)
        except HTTPStatusError as exc:
            logger.error(
                "RAG document search failed for tool %s with error: %s", name, exc, exc_info=True
            )
            raise ModelRetry(f"Document search service is currently unavailable: {exc}") from exc

        ctx.usage += RunUsage(
            input_tokens=rag_results.usage.prompt_tokens,
            output_tokens=rag_results.usage.completion_tokens,
        )

        return ToolReturn(
            return_value={
                str(idx): {
                    "url": result.url,
                    "snippets": result.content,
                }
                for idx, result in enumerate(rag_results.data)
            },
            metadata={"sources": {result.url for result in rag_results.data}},
        )

    return document_search_rag


def add_document_rag_search_tool_from_setting(agent: Agent, user: User) -> None:
    """
    This function takes a configuration setting and generates specific search RAG tools and add
    it to the agent.

    Args:
        agent (Agent): The agent to which the tool will be added.
        user (User): The user for whom the tool is being added.
    """

    for tool_name, tool_config in get_specific_rag_search_tool_config(user).items():
        document_store_backend_name = tool_config.get(
            "rag_backend_name", settings.RAG_DOCUMENT_SEARCH_BACKEND
        )
        try:
            document_store_backend = import_string(document_store_backend_name)
        except ImportError as exc:
            logger.warning(
                "Could not import RAG backend %s: %s",
                document_store_backend_name,
                exc,
                exc_info=True,
            )
            continue  # Skip if the backend is not available

        collection_ids = tool_config.get("collection_ids", [])
        if not collection_ids:
            logger.warning(
                "No collection IDs provided for tool %s, skipping.", tool_name
            )
            continue  # Skip if no collection IDs are provided

        tool_description = tool_config.get("tool_description")
        if not tool_description:
            logger.warning(
                "No tool description provided for tool %s, skipping.", tool_name
            )
            continue  # Skip if no tool description is provided

        _create_document_search_rag(
            agent, tool_name, tool_description, document_store_backend, collection_ids
        )
