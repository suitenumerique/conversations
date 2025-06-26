"""Fake weather tool for the chat agent."""

from agents import function_tool
from openai.types.chat import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

current_weather = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name="get_current_weather",
        description="Get the current weather in a given location",
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                },
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location", "unit"],
        },
    ),
)


def get_current_weather(location: str, unit: str):
    """Get the current weather in a given location."""
    return {
        "location": location,
        "temperature": 22 if unit == "celsius" else 72,
        "unit": unit,
    }


@function_tool(name_override="get_current_weather")
def agent_get_current_weather(location: str, unit: str) -> dict:
    """Get the current weather in a given location."""
    return get_current_weather(location, unit)
