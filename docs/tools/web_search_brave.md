# Brave Web Search Tools

## Overview

The Brave web search tools enable the conversation agent to search the web using the [Brave Search API](https://brave.com/search/api/). 
Brave Search is a privacy-focused search engine that provides comprehensive web search results.

This documentation covers three related tools:
1. **`web_search_brave`** - Standard web search with optional summarization
2. **`web_search_brave_with_document_backend`** - Web search with RAG-based document processing
3. **`web_search_albert_rag`** - ⚠️ **Deprecated** - Use `web_search_brave_with_document_backend` instead

## Table of Contents

- [Common Configuration](#common-configuration)
- [web_search_brave](#web_search_brave)
- [web_search_brave_with_document_backend](#web_search_brave_with_document_backend)
- [Deprecated: web_search_albert_rag](#deprecated-web_search_albert_rag)
- [Comparison](#comparison)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Common Configuration

### Prerequisites

1. **Brave Search API Key**: Sign up at [Brave Search API](https://brave.com/search/api/) to get an API key
2. **Environment Variables**: Configure the required settings

### Common Environment Variables

All Brave tools share these common settings:

| Variable            | Required | Default | Description                                        |
|---------------------|----------|---------|----------------------------------------------------|
| `BRAVE_API_KEY`     | **Yes**  | None    | Your Brave Search API key                          |
| `BRAVE_API_TIMEOUT` | No       | 5       | API request timeout in seconds                     |
| `BRAVE_MAX_RESULTS` | No       | 8       | Maximum number of search results                   |
| `BRAVE_CACHE_TTL`   | No       | 1800    | Cache time-to-live in seconds (30 minutes)         |

### Search Parameters

Check on the Brave API documentation for more details on these parameters:

| Variable                      | Required | Default    | Description                                       |
|-------------------------------|----------|------------|---------------------------------------------------|
| `BRAVE_SEARCH_COUNTRY`        | No       | None       | Country code for search (e.g., "US", "FR")        |
| `BRAVE_SEARCH_LANG`           | No       | None       | Language code (e.g., "en", "fr")                  |
| `BRAVE_SEARCH_SAFE_SEARCH`    | No       | "moderate" | Safe search level: "off", "moderate", or "strict" |
| `BRAVE_SEARCH_SPELLCHECK`     | No       | True       | Enable spell checking                             |
| `BRAVE_SEARCH_EXTRA_SNIPPETS` | No       | True       | Fetch extra snippets from pages                   |


Note: even if `BRAVE_SEARCH_EXTRA_SNIPPETS` is enabled, the API may not include them if you don't have a plan for this.
This is why, in `web_search_brave`, we also fetch the page content ourselves when needed.

### Configuration Example

```bash
# .env file
BRAVE_API_KEY=BSA-your-api-key-here
BRAVE_MAX_RESULTS=8
BRAVE_MAX_WORKERS=4
BRAVE_SEARCH_COUNTRY=US
BRAVE_SEARCH_LANG=en
BRAVE_SEARCH_SAFE_SEARCH=moderate
```

### Django Settings

All Brave settings are defined in `src/backend/conversations/brave_settings.py`:

```python
class BraveSettings:
    """Brave settings for web_search_brave tool."""

    BRAVE_API_KEY = values.Value(
        default=None,
        environ_name="BRAVE_API_KEY",
        environ_prefix=None,
    )
    # ... more settings
```

---

## web_search_brave

### Overview

Standard Brave web search tool with optional LLM-based summarization of page content.

### Purpose

- Search the web for up-to-date information
- Extract content from web pages
- Optionally summarize content using an LLM
- Provide structured results with snippets

### Additional Configuration

| Variable                      | Required | Default | Description                                     |
|-------------------------------|----------|---------|-------------------------------------------------|
| `BRAVE_SUMMARIZATION_ENABLED` | No       | False   | Enable LLM-based summarization of fetched pages |

### Function Signature

```python
def web_search_brave(query: str) -> ToolReturn:
    """
    Search the web for up-to-date information

    Args:
        query (str): The query to search for.
        
    Returns:
        ToolReturn: Formatted search results with metadata
    """
```

### Return Value

Returns a `ToolReturn` object with:

```python
ToolReturn(
    return_value={
        "0": {
            "url": "https://example.com/page1",
            "title": "Example Page Title",
            "snippets": ["Extracted or summarized content..."]
        },
        "1": {
            "url": "https://example.com/page2",
            "title": "Another Page",
            "snippets": ["More content..."]
        }
    },
    metadata={
        "sources": {
            "https://example.com/page1",
            "https://example.com/page2"
        }
    }
)
```

### How It Works

1. **Query API**: Sends search query to Brave Search API
2. **Receive Results**: Gets list of matching web pages
3. **Fetch Content**: For results without extra_snippets:
   - Fetches the HTML content using `trafilatura`
   - Extracts the main text content
   - Caches the extracted content
4. **Summarize (Optional)**: If `BRAVE_SUMMARIZATION_ENABLED=True`:
   - Sends extracted content to summarization agent
   - Receives concise summary focused on the query
5. **Format Results**: Returns structured data with URLs, titles, and snippets

### Workflow Diagram

```
User Query
    ↓
Brave Search API
    ↓
Search Results (URLs, titles, descriptions)
    ↓
[For each result without snippets]
    ↓
Fetch HTML (trafilatura) → Extract Text → Cache
    ↓
[If BRAVE_SUMMARIZATION_ENABLED]
    ↓
Summarization Agent (LLM)
    ↓
Summary Text
    ↓
Format & Return
```

### Caching

Extracted content is cached to avoid repeated fetches:

```python
cache_key = f"web_search_brave:extract:{url}"
cache.set(cache_key, document, settings.BRAVE_CACHE_TTL)
```

**Cache Duration**: Controlled by `BRAVE_CACHE_TTL` (default: 30 minutes)

### Summarization

When enabled, the tool uses the `SummarizationAgent` to condense page content:

```python
prompt = f"""
Based on the following request, summarize the following text in a concise manner, 
focusing on the key points regarding the user request. 
The result should be up to 30 lines long.

<user request>
{query}
</user request>

<text to summarize>
{text}
</text to summarize>
"""
```

**Note**: Summarization is costly (additional LLM calls). 
Use only when necessary, we prefer the document vector search from `web_search_brave_with_document_backend`.

### Add to Model

```json
{
  "models": [
    {
      "hrid": "my-model",
      "tools": [
        "web_search_brave"
      ]
    }
  ]
}
```

### Example Usage

**User**: "What are the new features in Django 5.0?"

**Tool Call**: `web_search_brave("Django 5.0 new features")`

**Tool Response**:
```python
{
    "0": {
        "url": "https://docs.djangoproject.com/en/5.0/releases/5.0/",
        "title": "Django 5.0 release notes",
        "snippets": ["Django 5.0 introduces several new features including..."]
    },
    # ... more results
}
```

### Registration

```python
"web_search_brave": Tool(
    web_search_brave, 
    takes_ctx=False, 
    prepare=only_if_web_search_enabled
)
```

---

## web_search_brave_with_document_backend

### Overview

Advanced Brave web search tool that uses RAG (Retrieval-Augmented Generation) 
with a document backend for intelligent content processing and retrieval.

### Purpose

- Search the web and process results through a RAG system
- Store fetched documents in a temporary vector database
- Perform semantic search across fetched content
- Return the most relevant chunks based on the query

### Additional Configuration

| Variable                            | Required | Default          | Description                                  |
|-------------------------------------|----------|------------------|----------------------------------------------|
| `BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER` | No       | 10               | Number of chunks to retrieve from RAG search |
| `RAG_DOCUMENT_SEARCH_BACKEND`       | No       | AlbertRagBackend | Document backend for RAG processing          |

### Function Signature

```python
def web_search_brave_with_document_backend(ctx: RunContext, query: str) -> ToolReturn:
    """
    Search the web for up-to-date information

    Args:
        ctx (RunContext): The run context containing the conversation.
        query (str): The query to search for.
        
    Returns:
        ToolReturn: Formatted search results with RAG-enhanced snippets
    """
```

### How It Works

1. **Query API**: Sends search query to Brave Search API
2. **Receive Results**: Gets list of matching web pages
3. **Create Temporary Collection**: Creates a temporary vector database collection
4. **Fetch & Store**: For each result:
   - Fetches the HTML content
   - Extracts the main text
   - Stores in the temporary document backend
5. **RAG Search**: Performs semantic search across stored documents
6. **Map Results**: Maps RAG chunks back to original search results
7. **Format & Return**: Returns structured data with enhanced snippets
8. **Cleanup**: Temporary collection is automatically deleted

### Workflow Diagram

```
User Query
    ↓
Brave Search API
    ↓
Search Results (URLs)
    ↓
Create Temporary Vector Collection
    ↓
[For each URL]
    ↓
Fetch HTML → Extract Text → Store in Vector DB
    ↓
RAG Semantic Search
    ↓
Retrieve Most Relevant Chunks
    ↓
Map Chunks to Original URLs
    ↓
Format & Return
    ↓
Delete Temporary Collection
```

### Temporary Collection

The tool creates a temporary collection with a unique ID:

```python
with document_store_backend.temporary_collection(f"tmp-{uuid.uuid4()}") as document_store:
    # Fetch and store documents
    # Perform search
    # Collection is automatically deleted on exit
```

### RAG Search

The RAG backend performs semantic search to find the most relevant content:

```python
rag_results = document_store.search(
    query,
    results_count=settings.BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER,
)
```

Returns chunks ranked by relevance to the query, not just keyword matching.

### Token Usage Tracking

The tool tracks LLM tokens used during RAG processing:

```python
ctx.usage += RunUsage(
    input_tokens=rag_results.usage.prompt_tokens,
    output_tokens=rag_results.usage.completion_tokens,
)
```

### Document Backend

The default backend is `AlbertRagBackend`, but you can configure a different one:

```bash
RAG_DOCUMENT_SEARCH_BACKEND=chat.agent_rag.document_rag_backends.custom_backend.CustomBackend
```

### Add to Model

```json
{
  "models": [
    {
      "hrid": "my-model",
      "tools": [
        "web_search_brave_with_document_backend"
      ]
    }
  ]
}
```

### Example Usage

**User**: "Explain the concept of async views in Django"

**Tool Call**: `web_search_brave_with_document_backend(ctx, "Django async views explained")`

**Tool Response**:
```python
{
    "0": {
        "url": "https://docs.djangoproject.com/en/stable/topics/async/",
        "title": "Asynchronous support",
        "snippets": [
            "Django has support for writing asynchronous views...",
            "Async views are declared using Python's async def syntax..."
        ]
    },
    # ... more results with relevant chunks
}
```

### Registration

```python
"web_search_brave_with_document_backend": Tool(
    web_search_brave_with_document_backend,
    takes_ctx=True,
    prepare=only_if_web_search_enabled,
)
```

### Advantages Over Standard web_search_brave

| Feature           | web_search_brave               | web_search_brave_with_document_backend |
|-------------------|--------------------------------|----------------------------------------|
| Content Retrieval | Full page or summary           | Semantic chunks                        |
| Relevance         | Keyword-based                  | Semantic similarity                    |
| Token Efficiency  | May include irrelevant content | Only relevant chunks                   |
| Processing        | Simpler, faster                | More intelligent, slower               |
| Cost              | Lower                          | Higher (RAG processing)                |
| Best For          | General search                 | Deep research, technical queries       |

---

## Deprecated: web_search_albert_rag

### ⚠️ Deprecation Notice

The `web_search_albert_rag` tool is **deprecated** and should not be used in new implementations.

**Replacement**: Use `web_search_brave_with_document_backend` instead, which provides:
- Better performance
- More control over the RAG backend
- Temporary collections (no cleanup issues)
- Token usage tracking
- Parallel processing support

### Why Deprecated?

- Limited to Albert API only
- No control over document backend
- Less flexible than the new approach
- Maintenance burden

### Timeline

- **Current**: Still functional but not recommended
- **Future**: Will be removed in a future version

---

## Comparison

### When to Use Which Tool?

#### Use `web_search_brave`

✅ **Best for**:
- General web search queries
- Quick information retrieval
- When speed is important
- Lower cost requirements
- Simple fact-finding

❌ **Not ideal for**:
- Deep research requiring precise context
- Technical documentation queries
- When semantic relevance is crucial

#### Use `web_search_brave_with_document_backend`

✅ **Best for**:
- Complex technical queries
- Research requiring precise context
- When semantic relevance is important
- Questions needing deep understanding
- Documentation and how-to queries

❌ **Not ideal for**:
- Simple factual queries
- When speed is critical
- Budget-constrained scenarios
- High-volume usage

---

## Best Practices

### Query Formulation

Help the LLM formulate effective queries:

```python
# Good queries
"Python asyncio tutorial 2024"
"Django REST framework authentication"
"React hooks best practices"

# Poor queries
"tell me about programming"  # Too vague
"how do I do the thing with the stuff"  # Unclear
```

### Performance Optimization

#### 1. Optimize Cache

```bash
# Longer cache for stable content
BRAVE_CACHE_TTL=3600  # 1 hour

# Shorter cache for dynamic content
BRAVE_CACHE_TTL=300   # 5 minutes
```

#### 2. Control Result Count

```bash
# Fewer results = faster responses
BRAVE_MAX_RESULTS=5

# More results = more comprehensive
BRAVE_MAX_RESULTS=10
```

### Summarization Best Practices

Only enable summarization when needed:

```bash
# Enable for long-form content
BRAVE_SUMMARIZATION_ENABLED=True

# Disable for speed
BRAVE_SUMMARIZATION_ENABLED=False
```

**Cost consideration**: Summarization makes additional LLM calls for each result, 
significantly increasing costs (and execution time).

### RAG Configuration

For `web_search_brave_with_document_backend`:

```bash
# More chunks = more context, higher cost
BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER=10

# Fewer chunks = faster, less context
BRAVE_RAG_WEB_SEARCH_CHUNK_NUMBER=5
```

### Search Parameters

```bash
# Localize results
BRAVE_SEARCH_COUNTRY=FR
BRAVE_SEARCH_LANG=fr

# Safe search for public deployments
BRAVE_SEARCH_SAFE_SEARCH=strict

# Enable spell check for better results
BRAVE_SEARCH_SPELLCHECK=True
```

---

## Troubleshooting

### Common Issues

#### 1. No Results Returned

**Symptoms**: Empty results or no snippets

**Causes**:
- Query too specific
- Content extraction failed
- Trafilatura couldn't parse the pages

**Solutions**:
```bash
# Enable extra snippets
BRAVE_SEARCH_EXTRA_SNIPPETS=True

# Increase result count
BRAVE_MAX_RESULTS=10

# Check logs for extraction errors
```

#### 2. API Errors

**Symptoms**: HTTP errors, authentication failures

**Causes**:
- Invalid API key
- Rate limit exceeded
- API service issues

**Solutions**:
```bash
# Verify API key is set
echo $BRAVE_API_KEY

# Check Brave API dashboard for limits
# Implement rate limiting in your application
```

#### 3. The tool is not being called
**Symptoms**: LLM doesn't use the tool even when appropriate

**Causes**:
- Web search not enabled for the conversation
- Tool not in model configuration

**Solutions**:
- Check conversation settings have `web_search_enabled=True`
- Verify tool is in the model's `tools` list

---

## Security Considerations

This tool is quite "raw", so be cautious about:
- the results returned by the web search
- the context size which might be large when not using summarization or RAG if long results are returned
- the query content which might include sensitive information
- ...

### Content Validation

Be aware that fetched content may contain:
- Malicious scripts (mitigated by text extraction)
- Inappropriate content
- Misinformation
- Biased information

The LLM should evaluate sources critically.


---

## See Also

- [Tools Overview](../tools.md)
- [Tavily Web Search Tool](web_search_tavily.md)
- [LLM Configuration](../llm-configuration.md)
- [Environment Variables](../env.md)
- [Brave Search API Documentation](https://brave.com/search/api/)

