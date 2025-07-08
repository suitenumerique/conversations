"""Tools for the chat agent."""
from agents import FunctionTool

from .fake_current_weather import agent_get_current_weather
from .web_search_tavily import agent_web_search_tavily


def get_tool_by_name(name: str) -> FunctionTool:
    """Get a tool by its name."""
    tool_dict = {
        "get_current_weather": agent_get_current_weather,
        "tavily_web_search": agent_web_search_tavily,
    }

    return tool_dict[name]  # will raise on purpose if name is not found
