# Tools for the Conversation Agent

The conversation agent can be extended with various tools that provide additional capabilities such as web search, 
weather information, and more. We currently only have web search tools, but more tools can be added as needed.
This document explains how to configure and use these tools.

## Overview

Tools are functions that the LLM can call during a conversation to access external data or perform specific actions. 
The agent decides when to use these tools based on the user's query and the conversation context.

## Configuring Tools for a Model

Tools are configured at the model level in the LLM configuration file. 
Each model can have its own set of available tools.

### Configuration File Location

Read the [LLM Configuration](llm-configuration.md) document to find out where the configuration file is located
and how to use it.

### Example Configuration

```json
{
  "models": [
    {
      "hrid": "default-model",
      "model_name": "gpt-4",
      "human_readable_name": "GPT-4 with Tools",
      "provider_name": "default-provider",
      "is_active": true,
      "system_prompt": "You are a helpful assistant.",
      "tools": [
        "web_search_brave",
        "get_current_weather"
      ]
    }
  ],
  "providers": [
    {
      "hrid": "default-provider",
      "base_url": "https://api.openai.com/v1",
      "api_key": "settings.AI_API_KEY",
      "kind": "openai"
    }
  ]
}
```

The `tools` field accepts either:
- A list of tool names: `["tool_name_1", "tool_name_2"]`
- A reference to a settings variable: `"settings.AI_AGENT_TOOLS"`

## Available Tools

To make a tool available to be in a model's configuration, it must be registered in the tool registry located at
`src/backend/chat/tools/__init__.py`.

This is not dynamic - any changes to the tool registry require a code deployment... 
We want to add dynamic loading in the future.

| Tool Name                                | Description                                                   | Documentation                                                               |
|------------------------------------------|---------------------------------------------------------------|-----------------------------------------------------------------------------|
| `get_current_weather`                    | Fake weather tool for testing purposes                        | [Details](tools/get_current_weather.md)                                     |
| `web_search_tavily`                      | Web search using Tavily API                                   | [Details](tools/web_search_tavily.md)                                       |
| `web_search_brave`                       | Web search using Brave Search API with optional summarization | [Details](tools/web_search_brave.md)                                        |
| `web_search_brave_with_document_backend` | Web search using Brave with RAG-based document processing     | [Details](tools/web_search_brave.md#web_search_brave_with_document_backend) |
| `web_search_albert_rag`                  | ⚠️ **Deprecated** - Web search using Albert API with RAG      | [Details](tools/web_search_brave.md#deprecated-web_search_albert_rag)       |

## Adding a New Tool

To add a new tool to the system, follow these steps:

### 1. Create the Tool Function

Create a new Python file in `src/backend/chat/tools/` with your tool function. The function should:

- Have clear type annotations
- Include a comprehensive docstring (the LLM uses this to understand when to use the tool)
- Accept `RunContext` as the first parameter if it needs access to conversation context
- Return appropriate data types

Example:
```python
"""My custom tool for the chat agent."""

from pydantic_ai import RunContext

def my_custom_tool(ctx: RunContext, param1: str, param2: int) -> dict:
    """
    Brief description of what the tool does.
    
    The LLM uses this description to decide when to call this tool.
    
    Args:
        ctx (RunContext): The run context containing the conversation.
        param1 (str): Description of parameter 1.
        param2 (int): Description of parameter 2.
    
    Returns:
        dict: Description of the return value.
    """
    # Your implementation here
    return {"result": "example"}
```

### 2. Register the Tool

Add your tool to the registry in `src/backend/chat/tools/__init__.py`:

```python
from .my_custom_tool import my_custom_tool

def get_pydantic_tools_by_name(name: str) -> Tool:
    """Get a tool by its name."""
    tool_dict = {
        "get_current_weather": Tool(get_current_weather, takes_ctx=False),
        "web_search_brave": Tool(
            web_search_brave, takes_ctx=False, prepare=only_if_web_search_enabled
        ),
        # Add your tool here
        "my_custom_tool": Tool(
            my_custom_tool, 
            takes_ctx=True,  # Set to True if your tool needs RunContext
            # prepare=only_if_web_search_enabled  # Optional: add conditions
        ),
    }
    return tool_dict[name]
```

### 3. Update Imports

Don't forget to import your tool function at the top of `__init__.py`:

```python
from .my_custom_tool import my_custom_tool
```

### 4. Add to Model Configuration

Add your tool name to the `tools` list in your LLM configuration file or 
to the `AI_AGENT_TOOLS` environment variable for local/test purpose.

## Tool Preparation: Conditional Tool Availability

Some tools should only be available under certain conditions. The `prepare` parameter in the `Tool` constructor 
allows you to specify a function that determines whether a tool should be included.

### The `only_if_web_search_enabled` Prepare Function

This is a built-in prepare function that checks if web search feature is enabled in the conversation context:

```python
async def only_if_web_search_enabled(ctx, tool_def: ToolDefinition) -> ToolDefinition | None:
    """Prepare function to include a tool only if web search is enabled in the context."""
    return tool_def if ctx.deps.web_search_enabled else None
```

### Usage

All web search tools use this prepare function:

```python
"web_search_brave": Tool(
    web_search_brave, 
    takes_ctx=False, 
    prepare=only_if_web_search_enabled
),
```

This ensures that web search tools are only available when the user or conversation settings have enabled web search functionality.

### Creating Custom Prepare Functions

You can create your own prepare functions for custom conditions:

```python
async def only_if_feature_enabled(ctx, tool_def: ToolDefinition) -> ToolDefinition | None:
    """Include tool only if a specific feature is enabled."""
    return tool_def if ctx.deps.feature_enabled else None
```

## Web Search Enable/Disable

Web search tools can be toggled on or off based on conversation settings. When web search is disabled:
- Web search tools are not included in the agent's available tools
- The LLM cannot make web search calls even if it tries
- This is enforced by the `only_if_web_search_enabled` prepare function

The `web_search_enabled` flag is typically set:
- Per conversation in the conversation settings
- Per user preference
- Through admin configuration

## Best Practices

1. **Keep tools focused** - Each tool should do one thing well
2. **Clear documentation** - The LLM relies on docstrings to understand when to use tools
3. **Error handling** - Tools should handle errors gracefully and return meaningful messages
4. **Performance** - Be mindful of API rate limits and timeout values
5. **Security** - Never log sensitive data (API keys, user data, etc.)
6. **Caching** - Use Django's cache framework for expensive operations when appropriate

## Troubleshooting

### Tool Not Being Called

If the LLM isn't calling your tool:
- Check that the tool is registered in `get_pydantic_tools_by_name`
- Verify the tool is in the model's `tools` configuration
- Review the tool's docstring - make it clearer when the tool should be used
- Check if any `prepare` function is preventing the tool from being included

### Tool Errors

If a tool is throwing errors:
- Check the logs for detailed error messages
- Verify all required environment variables are set
- Ensure the tool's dependencies are installed
- Test the tool function independently

We recommend wrapping external API calls in try/except blocks to handle potential issues gracefully and use
the Pydantic AI `ModelRetry` exception to let the LLM manage the errors.

### Tool Response Issues

If the LLM isn't using the tool response correctly:
- Ensure the return type is clear and well-structured
- Consider returning a `ToolReturn` object with metadata
- Check if the response format matches what the LLM expects

## See Also

- [Web Search Configuration](llm-configuration.md)
- [Architecture](architecture.md)
- [Environment Variables](env.md)

