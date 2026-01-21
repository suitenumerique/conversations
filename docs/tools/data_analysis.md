## data_analysis Tool

### Overview

The `data_analysis` tool lets the assistant **analyze tabular files** (CSV / Excel) that the user has uploaded in the current conversation and, optionally, **generate plots** (time series, bar charts, etc.).

Behind the scenes it:
- finds a tabular attachment in the conversation,
- generates a **presigned S3 URL** for that file,
- calls an **external MCP server** (`data_analysis_tool`) with this URL and the user query,
- receives back a textual analysis and, optionally, a plot image, which is then stored and inserted directly into the conversation.

---

### Prerequisites

- Conversations running locally via `docker-compose` (so that MinIO is available on `minio:9000` in the backend).
- An MCP server implementing a `data_analysis_tool` HTTP endpoint, listening on:
  - `http://localhost:8000/mcp` on your host machine.
- A way for this MCP server to access your MinIO bucket from outside Docker:
  - we use **ngrok** to expose MinIO’s port `9000` over HTTPS.

---

### Environment Configuration

All the dev defaults are already present in `env.d/development/common`, but you may need to **adapt them to your environment**.

#### 1. Enable the tool and feature flag

In `env.d/development/common`:

- **Tools list**:

```ini
AI_AGENT_TOOLS=web_search_brave_with_document_backend,data_analysis
```

- **Feature flag**:

```ini
FEATURE_FLAG_DATA_ANALYSIS=ENABLED
```

This allows the model to call `data_analysis` when it thinks it is relevant.

#### 2. Expose MinIO to the MCP server (ngrok)

The MCP server runs **outside** Docker, but the files are stored in MinIO **inside** the `docker-compose` network.  
To let the MCP server download the file via a presigned URL, you must:

1. Expose MinIO port `9000` with ngrok (on your host):

```bash
ngrok http 9000
```

2. Take the HTTPS URL given by ngrok, e.g.:

```text
https://your-random-subdomain.ngrok-free.app
```

3. Set it as `AWS_S3_MCP_URL` in `env.d/development/common`:

```ini
AWS_S3_MCP_URL=https://your-random-subdomain.ngrok-free.app
```

This value is used here:
- in `data_analysis.py`, a dedicated S3 client is created with `endpoint_url=settings.AWS_S3_MCP_URL`;
- the presigned URL given to the MCP server points to this external endpoint, so the MCP process can fetch the file.

> **Important**: keep `AWS_S3_ENDPOINT_URL` pointing to `http://minio:9000` for the backend itself; only `AWS_S3_MCP_URL` needs to be the ngrok HTTPS URL.

#### 3. Data analysis MCP server URL

The URL of the external MCP server is configured in `src/backend/chat/mcp_servers.py`:

```python
DATA_ANALYSIS_MCP_SERVER = {
    "data-analysis": {
        "url": "http://host.docker.internal:8000/mcp",
    },
}
```

From inside the backend container, `host.docker.internal` resolves to your host machine.  
So you must run your MCP server on the host at `http://localhost:8000/mcp`:

```bash
# On the host machine (outside Docker)
uv run your_data_analysis_mcp_server --port 8000  # exemple
```

Adapt the command to how your MCP server is started; the important part is that it listens on `0.0.0.0:8000` (or `localhost:8000`) with the `/mcp` endpoint.

If you change the MCP server URL, update `DATA_ANALYSIS_MCP_SERVER` accordingly.

---

### How It Works (Backend Side)

High-level flow in `src/backend/chat/tools/data_analysis.py`:

1. **Find attachments**  
   The tool looks for `ChatConversationAttachment` objects in the current conversation:
   - only **original** files (`conversion_from` is `NULL` / empty),
   - excludes markdown conversions,
   - filters for tabular extensions: `.csv`, `.xls`, `.xlsx`.

2. **Select a document & generate presigned URL**  
   It picks the **first tabular file** and generates a presigned URL pointing to the S3 object,
   using the special MCP S3 client (endpoint = `AWS_S3_MCP_URL`).

3. **Call the MCP server**  
   It then calls the external MCP server:
   - tool name: `data_analysis_tool`
   - arguments:
     - `query`: the natural language instruction from the user,
     - `document`: the presigned S3 URL,
     - `document_name`: the original file name.

4. **Parse MCP response**  
   The MCP server is expected to return a JSON payload (as text), typically containing:
   - `result`: textual analysis / summary,
   - optionally `plot_image`: base64-encoded PNG of a plot,
   - optionally `query_code`: code used to produce the result (e.g. Python / pandas).

5. **Store plot image (optional)**  
   If `plot_image` is present:
   - the backend decodes it,
   - saves it into the same object storage as other media,
   - generates a browser URL for the frontend using `generate_retrieve_policy`,
   - stores that URL in `metadata["plot_url"]` of the `ToolReturn`.

6. **Return to the agent**  
   The `ToolReturn` contains:

   - `return_value` (what the model sees):
     - `{"result": "<texte d'analyse ...>"}`  
       (no `plot_url` — the model never sees the URL)
   - `metadata` (internal use, not seen by the model):
     - `{"plot_url": "<URL du graphique>", "query_code": "..."}` when a plot exists.

7. **Insertion of the plot in the conversation**  
   In `pydantic_ai.py`, when the agent receives a tool result from `data_analysis`:
   - it reads `plot_url` from `event.result.metadata`,
   - inserts a markdown image `![Graphique de l'analyse](plot_url)` **directly in the streamed response** to the frontend,
   - the model only has to comment on the results; it is not responsible for embedding the image.

---

### Enabling the Tool in a Model

In your LLM configuration (`conversations/configuration/llm/*.json`), ensure the tool is listed:

```json
{
  "models": [
    {
      "hrid": "my-model",
      "tools": [
        "data_analysis"
      ]
    }
  ]
}
```

Or, in a local dev environment, via `env.d/development/common`:

```ini
AI_AGENT_TOOLS=web_search_brave_with_document_backend,data_analysis
```

---

### Typical Usage From the User Perspective

1. The user uploads one or more **CSV / Excel** files in the conversation.
2. Then asks a question like:
   - “Fais une analyse des soldes par client dans ce fichier.”
   - “Trace l’évolution du chiffre d’affaires au cours du temps.”
3. The model detects that a tabular file is available and calls the `data_analysis` tool.
4. The MCP server:
   - downloads the file via the presigned URL,
   - runs the analysis (e.g. pandas),
   - renvoie un résultat structuré + un graphique encodé en base64.
5. The backend:
   - stocke l’image du graphique,
   - l’insère directement dans le message assistant,
   - donne au modèle uniquement le texte d’analyse à commenter.

From the user’s point of view, they just see:
- their question,
- the assistant’s answer with text **and** a generated chart, without manual configuration.

---

### Troubleshooting

- **The tool is never called**
  - Check that:
    - `FEATURE_FLAG_DATA_ANALYSIS=ENABLED` is set,
    - `AI_AGENT_TOOLS` includes `data_analysis`,
    - the model in your LLM config has `data_analysis` listed in `tools`.

- **File download error in the MCP**
  - Check that:
    - `ngrok http 9000` is running,
    - `AWS_S3_MCP_URL` is set to the ngrok **HTTPS** URL,
    - the MCP server can reach this URL (a quick test: `curl <presigned-url>` from the MCP server machine).

- **No plot returned even though a chart was requested**
  - Inspect the MCP server logs (can it read the file?),
  - Make sure it returns a `plot_image` field (base64 PNG) in its JSON response.

---

### See Also

- `src/backend/chat/tools/data_analysis.py`
- `src/backend/chat/mcp_servers.py`
- [Tools Overview](../tools.md)
- [Environment Variables](../env.md)

