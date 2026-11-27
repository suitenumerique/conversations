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
| `web_search_brave`                       | Web search using Brave Search API with optional summarization | [Details](tools/web_search_brave.md)                                        |
| `web_search_brave_with_document_backend` | Web search using Brave with RAG-based document processing     | [Details](tools/web_search_brave.md#web_search_brave_with_document_backend) |
| `web_search_staan`                       | Web search using the Staan Web Search for AI API              | [Details](tools/web_search_staan.md)                                        |

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

## Connectors (MCP)

Everything above describes tools built in this repository. A **connector** is
different: it is one remote MCP server a user has switched on for themselves,
and it *contributes* tools to the assistant rather than being one.

Connectors are declared by the deployment in `MCP_CONNECTORS` (see
[Declaring a connector](#declaring-a-connector)); the code lives in
`chat/connectors/`. A connector reaches the agent only when all three of these
hold:

| Gate | Where |
|------|-------|
| The deployment declares it | `MCP_CONNECTORS` (empty by default — nothing is then built and nothing contacted) |
| The user is in its cohort | the declaration's `feature_flag`, e.g. `FEATURE_FLAG_DATAGOUV_CONNECTOR` for data.gouv; no flag means everyone |
| The user allowed it | its slug in `User.allowed_connectors` (empty by default), set from Settings, **or** the user forced the connector for that turn from the chat box |

`UserConnector` in `chat/connectors/turn.py` holds all three for one connector,
and `TurnConnectors` holds every declared connector for the turn. The first two
are turn-independent and answered once per request as `enabled`; adding the third
gives `available`: a connector the user has actually consented to. The third
depends on the turn, because forcing stands in for the opt-in — which is why
`toolsets()` asks for `available or forced` rather than `available` alone. A force never satisfies the first two: it is consent,
not configuration, and one the gates deny is logged and dropped.

Two fields of the declaration bound how long a connector may hold a turn.
`init_timeout` (default `5` seconds) bounds the whole
connection: `enter_mcp_toolsets` is handed that budget and holds it itself rather
than leaving it to the MCP client, whose own `init_timeout` covers the protocol handshake but
not the transport connect underneath it. `read_timeout`
(default `30` seconds) then bounds each individual tool call, because a server
can complete the handshake and still stall on the call itself — the library's
own default there is five minutes. A call that times out reaches the model as a
failed tool result, so the model answers without it.

Setting either to `0` disables that bound (a negative value is refused), the way `0` and `None` mean "no
limit" elsewhere in Django and in the HTTP stack underneath.

Its tools reach the model under the connector's prefix, so the server's
`search_datasets` is offered to the agent as `datagouv_search_datasets`, the
prefix being the connector's `slug`.

The server's tool descriptions say how to use each tool, never when. So the
connector's toolset carries our own instruction on when to reach for them:
official French public data, or a request for a dataset, a file or an API. It is
supplied through the toolset's `get_instructions`, so it reaches the model
exactly when the tools do. The wording is the
declaration's `instructions`, never the server's (see
`include_instructions=False` below).

The connector's toolsets are attached per turn, inside `_run_agent`'s
`AsyncExitStack`. A connector that cannot be reached is logged and dropped for
that turn: the user still gets an answer, built without it. A third-party
service being down must never cost someone their turn.

What the user is told about that depends on whether they asked for it. A
connector the assistant merely *may* consult stays silent. A connector the user
**forced** and that we could not reach still produces an answer, but the model
is instructed to say what it could not consult, and the turn streams a
`connector_unavailable` notice, naming the connector's slug, that the frontend
raises as a toast. The model's forced and unreachable wordings are derived from
the connector's `name`. The event type is
mirrored as a constant on both sides (`CONNECTOR_UNAVAILABLE_EVENT_TYPE`, in
`chat/turn/event_mapper.py` and `useChat.tsx`); changing one without the other
silently drops the notice.

A connector the gates deny is not an outage: nothing was contacted, so forcing
one reports nothing at all.

Neither is every failed tool call. A server that answers the handshake and then
goes away mid-turn owes the same notice as one that never answered, but a tool
that simply replies with an error, or a call the model got the arguments wrong
for, does not — the server was reached. Both reach the stream as the same
retryable tool error, so the two are told apart at the tool-call boundary
instead: `ConnectorToolset` wraps the connector's toolset and reports only the
failures that never got an answer (`is_connector_unreachable`). Argument
validation fails before the call reaches that wrapper, so it cannot be mistaken
for an outage.

Every outage, whether a read timeout, a protocol error or a transport error the
MCP client passes through, is handed to the model as a failed tool result rather
than a retry: another attempt would wait out the same timeout, and running out of
retries would cost the user their turn. The turn continues, the notice is
streamed alongside that result, and the connector is not called again for the
rest of the turn.

### Declaring a connector

`MCP_CONNECTORS` is a JSON list, one object per connector. Adding a partner
connector is a configuration change: no code, no migration. data.gouv is
declared like any other:

```json
[
  {
    "slug": "datagouv",
    "name": "DataGouv",
    "url": "https://mcp.data.gouv.fr/mcp",
    "tier": "partner",
    "feature_flag": "datagouv_connector",
    "icon": "/assets/connectors/datagouv.svg",
    "description": {
      "en": "Let the Assistant search French public open data published on data.gouv.fr.",
      "fr": "Autoriser l'Assistant à rechercher dans les données publiques françaises publiées sur data.gouv.fr.",
      "nl": "Laat de Assistant zoeken naar Franse openbare gegevens die zijn gepubliceerd op data.gouv.fr.",
      "ru": "Пусть помощник ищет открытые данные на сайте data.gouv.fr, связанные с франкоязычным регионом.",
      "uk": "Нехай помічник виконує пошук публічних відкритих даних, опублікованих на data.gouv.fr, для франкомовного регіону."
    },
    "init_timeout": 5,
    "read_timeout": 30,
    "instructions": "The data.gouv.fr tools search France's open-data catalogue: datasets, the organisations that publish them, and public APIs. Use them when the answer depends on official French public data (statistics, registries, local facilities, prices, figures for a commune or département), or when the user asks for a dataset, a file or an API. Prefer them over answering such figures from memory. Do not use them for questions about other countries, general knowledge, administrative procedures, writing or coding tasks, or questions about the user's attached documents."
  }
]
```

| Field | Required | Meaning |
|-------|----------|---------|
| `slug` | yes | `^[a-z0-9_]{1,20}$`. Tool prefix and key of opt-ins, events and history: **never change it** once users opted in. A new operator or URL means a new slug. |
| `name` | yes | How the user and the model read it: one string, shown as-is in every language, with no separate display label. |
| `url` | yes | The server's streamable-HTTP endpoint. |
| `tier` | yes | `internal`, `partner` or `user` ([ADR 0001](adr/0001-connector-trust-tiers.md)). Recorded, not enforced yet. |
| `instructions` | yes | When the model should use the tools. Written by us, never taken from the server. The wordings derived from `name` for a forced or unreachable connector are in English, like the rest of the system prompt. |
| `feature_flag` | no | A `FeatureFlags` field gating the connector to a cohort. Absent: everyone. |
| `description` | no | What the connector does, shown under its switch in Settings: one text per language code (`en`, `fr`, `fr-fr`...). The user's language is used, then its base language, then English, then any text given. |
| `icon` | no | An http(s) URL, or a path the frontend serves (`/assets/connectors/...`). Only its shape is used: it is drawn in the text colour, like the other icons, so a multicoloured logo comes out in one colour. Absent: a generic icon. A remote URL is fetched by every user's browser, so prefer the frontend or your own host. |
| `init_timeout`, `read_timeout` | no | Seconds, defaults `5` and `30`; `0` means no limit. |

Any other field is refused. A declaration the registry
(`chat/connectors/registry.py`) cannot use — invalid JSON, not a list, an
unknown field, a missing or unknown `tier`, a bad, duplicate or overlapping
slug, an unknown feature flag, a malformed URL, description or icon, a negative
or non-finite timeout — is:

- reported as `chat.E101` by `manage.py check`, and by `migrate`, so the Helm
  migrate job fails and shows the error;
- logged as `connector_declaration_refused` and left out at runtime, so one
  typo never costs every user their turn. It is never offered with a weaker
  setting.

The declarations are read again on every turn. `GET /config/` lists them for
the UI (`slug`, `name`, `description`, `icon` and the frontend name of
`feature_flag`; never the URL), so the Settings switches and the chat-box
options need no frontend release for a new connector.

### Opting in

`User.allowed_connectors` is the list of slugs a user switched on in Settings.
The users API accepts only connectors offered to that user (declared, and in
their cohort), but keeps a slug the user already had, so a connector taken
offline for a while keeps its users' consent. Opt-ins are keyed on the slug
alone: a connector whose URL changes keeps them, which is why a new operator
means a new slug.

### Forcing a connector

`POST /chats/{id}/conversation/` takes a `force_connectors` query parameter, one
per forced connector (`?force_connectors=datagouv&force_connectors=sofia`),
alongside the existing `force_web_search`. It applies to that turn only, stands
in for the opt-in, and is never stored on the message or the conversation.

The request is per turn; the UI control is not reset by sending. A force the
user switches on stays on until they switch it off, kept in the browser's
`localStorage` so it survives a reload, as `force_web_search` already does.
Every message sent meanwhile carries it. A slug the user may no longer use is
dropped by the turn rather than refused, so a stale force never fails a message.

A force the gates deny — the deployment does not declare the connector, or
the user is outside its cohort — contacts nothing, so the user is told nothing
and no `connector_forced` event is recorded. It is logged instead: the chat
button is shown on the cohort flag alone, so a deployment that sets the flag
without declaring the connector has no other symptom.

Three PostHog events measure the connectors, each with the `connector_id` slug:
`connector_toggled` (`enabled`), sent by the backend for each connector a user
switches in Settings; `connector_force_toggled` (`enabled`), sent by the frontend
when a user switches a chat-box force, which the backend never sees on its own;
and `connector_forced` (`reachable`), sent by the backend once per forced turn, whose `reachable` property
is the connector's outage rate. It is deliberately not called `available`: that
word means the standing state of the connector for a user, not whether this turn
got through.

### Trust boundary

A connector is a remote MCP server, so the server — not this repository —
authors the tool names, descriptions and results that enter the model's
context. For data.gouv, a state-run service, we accept all three as-is: a
connector is trusted about as much as a web page the assistant reads.

We do not accept the server's own initialization instructions.
`include_instructions=False` is set explicitly rather than left to the library
default, so a connector can never append to the agent's instructions.

We considered an allowlist of reviewed tool names and rejected it: it silently
freezes a connector's capabilities and depends on a maintainer noticing when
the server publishes new ones.

This boundary was set for a government-run server and is the precedent for
every `partner` connector that follows (see
[ADR 0001](adr/0001-connector-trust-tiers.md)). Reconsider it before shipping a connector this
team does not operate or trust.

## See Also

- [Web Search Configuration](llm-configuration.md)
- [Slide Deck Generation](presentations.md)
- [Architecture](architecture.md)
- [Environment Variables](env.md)

