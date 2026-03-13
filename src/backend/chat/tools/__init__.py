"""Tools for the chat agent."""

from pydantic_ai import Tool  # noqa: I001
from .fake_current_weather import get_current_weather


def get_pydantic_tools_by_name(name: str) -> Tool:
    """Get a tool by its name."""
    tool_dict = {
        "get_current_weather": Tool(get_current_weather, takes_ctx=False),
    }

    return tool_dict[name]  # will raise on purpose if name is not found
