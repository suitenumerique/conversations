"""Tools for the chat agent."""

from pydantic_ai import Tool

from .fake_current_weather import get_current_weather
from .web_search_tavily import tavily_web_search


def get_pydantic_tools_by_name(name: str) -> Tool:
    """Get a Pydantic AI agent by its name."""
    tool_dict = {
        "get_current_weather": Tool(get_current_weather, takes_ctx=False),
        "tavily_web_search": Tool(tavily_web_search, takes_ctx=False),
    }

    return tool_dict[name]  # will raise on purpose if name is not found
