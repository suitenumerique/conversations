"""Tools for the chat agent."""

from django.conf import settings

from agents import FunctionTool
from pydantic_ai import Agent, Tool

from .fake_current_weather import agent_get_current_weather, get_current_weather
from .web_search_tavily import agent_web_search_tavily, tavily_web_search


def get_tool_by_name(name: str) -> FunctionTool:
    """Get a tool by its name."""
    tool_dict = {
        "get_current_weather": agent_get_current_weather,
        "tavily_web_search": agent_web_search_tavily,
    }

    return tool_dict[name]  # will raise on purpose if name is not found


def get_pydantic_tools_by_name(name: str) -> Tool:
    """Get a Pydantic AI agent by its name."""
    tool_dict = {
        "get_current_weather": Tool(get_current_weather, takes_ctx=False),
        "tavily_web_search": Tool(tavily_web_search, takes_ctx=False),
    }

    return tool_dict[name]  # will raise on purpose if name is not found
