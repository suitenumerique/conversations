# get_current_weather Tool

## Overview

The `get_current_weather` tool is a **fake weather tool** designed for testing and demonstration purposes. It does not connect to any real weather API and always returns hardcoded weather data.

## Purpose

This tool is useful for:
- **Testing** the tool calling functionality of LLMs
- **Demonstrating** how tools work without requiring API keys
- **Development** and debugging of the agent system
- **Example implementation** for creating new tools

⚠️ **Warning**: This tool should **not** be used in production environments. It always returns fake data regardless of the location or conditions.

## Configuration

### Add to Model

To enable this tool for a model, add it to the `tools` list in your LLM configuration:

```json
{
  "models": [
    {
      "hrid": "my-model",
      "tools": [
        "get_current_weather"
      ]
    }
  ]
}
```

Or via environment variable when using local environment settings:
```ini
AI_AGENT_TOOLS=get_current_weather
```

### No Additional Settings Required

This tool does not require any API keys, environment variables, or additional configuration.

## Function Signature

```python
def get_current_weather(location: str, unit: str) -> dict:
    """
    Get the current weather in a given location.

    Args:
        location (str): The city and state, e.g. San Francisco, CA.
        unit (str): The unit of temperature, either 'celsius' or 'fahrenheit'.

    Returns:
        dict: A dictionary containing the location, temperature, and unit.
    """
```

## Parameters

| Parameter  | Type | Required | Description                                                     |
|------------|------|----------|-----------------------------------------------------------------|
| `location` | str  | Yes      | The city and state (e.g., "San Francisco, CA", "Paris, France") |
| `unit`     | str  | Yes      | Temperature unit: either "celsius" or "fahrenheit"              |

## Return Value

Returns a dictionary with the following structure:

```python
{
    "location": str,      # The location that was queried
    "temperature": int,   # Always 22°C or 72°F
    "unit": str          # The unit that was requested
}
```

## How the LLM Uses It

When a user asks about weather, the LLM will:

1. **Recognize** the weather-related query
2. **Extract** the location from the user's message
3. **Determine** the appropriate unit (often from context or user preference)
4. **Call** the `get_current_weather` tool
5. **Receive** the fake weather data
6. **Format** a response to the user

### Example Conversation

**User**: "What's the weather like in London?"

**LLM** (internal): *Calls `get_current_weather("London, UK", "celsius")`*

**Tool Response**: 
```json
{
  "location": "London, UK",
  "temperature": 22,
  "unit": "celsius"
}
```

**LLM** (to user): "The current weather in London, UK is 22°C."

## See Also

- [Tools Overview](../tools.md)
- [Adding a New Tool](../tools.md#adding-a-new-tool)
- [Testing Tools](../tools.md#testing-your-tools)

