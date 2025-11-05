# web_search_tavily Tool

## Overview

The `web_search_tavily` tool enables the conversation agent to search the web for up-to-date 
information using the [Tavily Search API](https://tavily.com/).

## Purpose

This tool allows the LLM to:
- Access current, real-time information beyond its training data
- Answer questions about recent events, news, or developments
- Provide factual information with sources
- Retrieve specific information from the web

## Configuration

### Prerequisites

1. **Tavily API Key**: Sign up at [Tavily](https://tavily.com/) to get an API key
2. **Environment Variables**: Configure the required settings

### Environment Variables

| Variable             | Required | Default | Description                                |
|----------------------|----------|---------|--------------------------------------------|
| `TAVILY_API_KEY`     | **Yes**  | None    | Your Tavily API key                        |
| `TAVILY_MAX_RESULTS` | No       | 5       | Maximum number of search results to return |
| `TAVILY_API_TIMEOUT` | No       | 10      | API request timeout in seconds             |

### Configuration Example

```bash
# .env file
TAVILY_API_KEY=tvly-your-api-key-here
TAVILY_MAX_RESULTS=5
TAVILY_API_TIMEOUT=10
```

### Add to Model

To enable this tool for a model, add it to the `tools` list in your LLM configuration:

```json
{
  "models": [
    {
      "hrid": "my-model",
      "tools": [
        "web_search_tavily"
      ]
    }
  ]
}
```

Or via environment variable when using local environment settings:

```ini
AI_AGENT_TOOLS=web_search_tavily
```

## Function Signature

```python
def web_search_tavily(query: str) -> list[dict]:
    """
    Search the web for up-to-date information

    Args:
        query (str): The query to search for.

    Returns:
        list[dict]: A list of search results, each represented as a dictionary.
    """
```

## Parameters

| Parameter | Type | Required | Description             |
|-----------|------|----------|-------------------------|
| `query`   | str  | Yes      | The search query string |

## Return Value

Returns a list of dictionaries, each containing:

```python
{
    "link": str,      # URL of the result
    "title": str,     # Title of the page
    "snippet": str    # Content snippet from the page
}
```

### Example Return Value

```python
[
    {
        "link": "https://example.com/article1",
        "title": "Introduction to Python",
        "snippet": "Python is a high-level programming language known for its simplicity..."
    },
    {
        "link": "https://example.com/article2",
        "title": "Python Best Practices",
        "snippet": "Follow these best practices to write clean and efficient Python code..."
    }
]
```

## How the LLM Uses It

When a user asks for current information or specific facts:

1. **LLM recognizes** the need for external information
2. **Formulates** an appropriate search query
3. **Calls** `web_search_tavily(query="search terms")`
4. **Receives** a list of search results
5. **Synthesizes** the information into a response
6. **Provides** the answer with source references

### Example Conversation

**User**: "What are the latest developments in quantum computing?"

**LLM** (internal): *Calls `web_search_tavily("latest developments quantum computing 2024")`*

**Tool Response**: 
```python
[
    {
        "link": "https://techcrunch.com/quantum-news",
        "title": "Major Breakthrough in Quantum Computing",
        "snippet": "Researchers announced a significant breakthrough..."
    },
    # ... more results
]
```

**LLM** (to user): "Based on recent sources, there have been several developments in quantum computing. 
Researchers recently announced a breakthrough in error correction. Additionally, new quantum processors 
with improved qubit stability have been unveiled..."

## Implementation Details

### Source Code

Located at: `src/backend/chat/tools/web_search_tavily.py`

```python
"""Web search tool using Tavily for the chat agent."""

from django.conf import settings

import requests


def web_search_tavily(query: str) -> list[dict]:
    """
    Search the web for up-to-date information

    Args:
        query (str): The query to search for.

    Returns:
        list[dict]: A list of search results, each represented as a dictionary.
    """
    url = "https://api.tavily.com/search"
    data = {
        "query": query,
        "api_key": settings.TAVILY_API_KEY,
        "max_results": settings.TAVILY_MAX_RESULTS,
    }
    response = requests.post(url, json=data, timeout=settings.TAVILY_API_TIMEOUT)
    response.raise_for_status()

    json_response = response.json()

    raw_search_results = json_response.get("results", [])

    return [
        {
            "link": result["url"],
            "title": result.get("title", ""),
            "snippet": result.get("content"),
        }
        for result in raw_search_results
    ]
```

### Registration

The tool is registered in `src/backend/chat/tools/__init__.py`:

```python
"web_search_tavily": Tool(
    web_search_tavily, 
    takes_ctx=False, 
    prepare=only_if_web_search_enabled
)
```

Note that:
- `takes_ctx=False` - This tool doesn't need the conversation context
- `prepare=only_if_web_search_enabled` - Only available when web search is enabled

## Django Settings

The tool uses these Django settings from `settings.py`:

```python
# Tavily API
TAVILY_API_KEY = values.Value(
    None,  # Tavily API key is not set by default
    environ_name="TAVILY_API_KEY",
    environ_prefix=None,
)
TAVILY_MAX_RESULTS = values.PositiveIntegerValue(
    default=5,
    environ_name="TAVILY_MAX_RESULTS",
    environ_prefix=None,
)
TAVILY_API_TIMEOUT = values.PositiveIntegerValue(
    default=10,  # seconds
    environ_name="TAVILY_API_TIMEOUT",
    environ_prefix=None,
)
```

## Error Handling

The tool may raise exceptions in the following cases:

### Missing API Key
```python
# If TAVILY_API_KEY is not set
AttributeError: 'Settings' object has no attribute 'TAVILY_API_KEY'
```

**Solution**: Set the `TAVILY_API_KEY` environment variable

### API Errors
```python
# If the API request fails
requests.exceptions.HTTPError: 401 Unauthorized
```

**Possible causes**:
- Invalid API key
- Exceeded rate limits
- API service unavailable

### Timeout Errors
```python
# If the request takes too long
requests.exceptions.Timeout
```

**Solution**: Increase `TAVILY_API_TIMEOUT` or check network connectivity

## Best Practices

### Query Formulation

The LLM should formulate queries that are:
- **Specific and focused** - Better results with targeted queries
- **Up-to-date** - Include year or "latest" when relevant
- **Clear** - Avoid ambiguous terms
- **Concise** - Remove unnecessary words

Good query examples:
- ✅ "quantum computing breakthroughs 2024"
- ✅ "latest Python 3.12 features"
- ✅ "climate change COP29 outcomes"

Poor query examples:
- ❌ "tell me about stuff happening" (too vague)
- ❌ "what is the weather like today in Paris on November 5th 2024 at 3pm" (too specific/long)

### Rate Limiting

Be aware of Tavily API rate limits:
- Free tier: Limited requests per month
- Paid tiers: Higher limits

Monitor your usage and implement caching if needed.

### Result Count

The `TAVILY_MAX_RESULTS` setting controls how many results are returned:
- **Lower values (3-5)**: Faster responses, less context for LLM
- **Higher values (8-10)**: More comprehensive, but slower and more expensive

Recommended: **5 results** for most use cases

## Troubleshooting

### Tool Not Being Called

**Symptoms**: LLM doesn't use web search even when appropriate

**Possible causes**:
1. Web search not enabled for the conversation
2. Tool not in model configuration
3. API key not set

**Solutions**:
1. Check conversation settings have `web_search_enabled=True`
2. Verify tool is in the model's `tools` list
3. Confirm `TAVILY_API_KEY` is set

### No Results Returned

**Symptoms**: Tool returns empty list

**Possible causes**:
1. Query too specific
2. No matching results
3. API filtering results

**Solutions**:
1. Try broader query terms
2. Check Tavily dashboard for query logs
3. Review API response in logs

### Slow Responses

**Symptoms**: Tool takes a long time to respond

**Possible causes**:
1. Network latency
2. Tavily API slow
3. Timeout too high

**Solutions**:
1. Check network connectivity
2. Monitor Tavily status page
3. Adjust `TAVILY_API_TIMEOUT` if needed

## Security Considerations

This tool is quite "raw", and was currently only used for test purpose, so be cautious about:
- the results returned by the web search
- the context size which might be large if many results are returned
- the query content which might include sensitive information
- ...

## Performance Optimization

### Query Optimization

You may want to help the LLM formulate better queries by including something like this in the system prompt:

```
When using web search:
- Use specific, focused queries
- Include relevant time periods if needed
- Avoid unnecessary words
- Combine related terms
```

## See Also

- [Tools Overview](../tools.md)
- [Brave Web Search Tool](web_search_brave.md)
- [Web Search Configuration](../llm-configuration.md)
- [Environment Variables](../env.md)

