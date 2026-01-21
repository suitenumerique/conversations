"""Tools for the chat agent."""

from pydantic_ai import Tool, ToolDefinition

from .data_analysis import data_analysis
from .fake_current_weather import get_current_weather
from .web_seach_albert_rag import web_search_albert_rag
from .web_search_brave import web_search_brave, web_search_brave_with_document_backend
from .web_search_tavily import web_search_tavily


async def only_if_data_analysis_enabled(ctx, tool_def: ToolDefinition) -> ToolDefinition | None:
    """Prepare function to include a tool only if data analysis is enabled in the context."""
    return tool_def if ctx.deps.data_analysis_enabled else None


async def only_if_web_search_enabled(ctx, tool_def: ToolDefinition) -> ToolDefinition | None:
    """Prepare function to include a tool only if web search is enabled in the context."""
    return tool_def if ctx.deps.web_search_enabled else None


def get_pydantic_tools_by_name(name: str) -> Tool:
    """Get a tool by its name."""
    tool_dict = {
        "get_current_weather": Tool(get_current_weather, takes_ctx=False),
        "web_search_brave": Tool(
            web_search_brave,
            takes_ctx=True,
            prepare=only_if_web_search_enabled,
            max_retries=2,
        ),
        "web_search_brave_with_document_backend": Tool(
            web_search_brave_with_document_backend,
            takes_ctx=True,
            prepare=only_if_web_search_enabled,
            max_retries=2,
        ),
        "web_search_tavily": Tool(
            web_search_tavily,
            takes_ctx=False,
            prepare=only_if_web_search_enabled,
            max_retries=2,
        ),
        "web_search_albert_rag": Tool(
            web_search_albert_rag,
            takes_ctx=True,
            prepare=only_if_web_search_enabled,
            max_retries=2,
        ),
        "data_analysis": Tool(
            data_analysis,
            takes_ctx=True,
            prepare=only_if_data_analysis_enabled,
            max_retries=2,
        ),
    }

    return tool_dict[name]  # will raise on purpose if name is not found
