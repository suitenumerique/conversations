# Staan Web Search Tool

## Overview

`web_search_staan` lets the conversation agent search the web through the
[Staan Web Search for AI API](https://docs.staan.ai/docs/web-for-ai).

Unlike the classic Brave tool, Staan resolves the page content itself: with `extra_snippets`
enabled the API fetches the result pages and returns semantically scored chunks, so the backend
never fetches or extracts anything on its own.

> **Selection:** web search is not picked through a model's `tools` list. The agent exposes a
> single tool named `web_search`, whose implementation comes from the model's `web_search`
> setting (a dotted path, imported and registered at runtime):
> `"web_search": "chat.tools.web_search_staan.web_search_staan"`.

## Configuration

### Prerequisites

1. **Staan API key**: set `STAAN_API_KEY`. Without it the tool fails immediately and tells the
   user the search is unavailable.
2. **Staan base URL**: set `STAAN_API_URL` to the API root, for example `https://api.staan.ai`.
   It has no default, so the tool cannot work until it is set — pointing at a self-hosted or
   proxied instance is an explicit deployment choice, never a silent fallback to the vendor SaaS.
   It must use HTTPS, and the app refuses to start otherwise: the API key is sent as a bearer
   token on every search. `localhost` is exempted so a local mock can be used in development.
3. **Model configuration**: point the model's `web_search` setting at
   `chat.tools.web_search_staan.web_search_staan`.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `STAAN_API_KEY` | `None` | API key, sent as `Authorization: Bearer` |
| `STAAN_API_URL` | `None` | Base URL of the API, required (e.g. `https://api.staan.ai`) |
| `STAAN_API_TIMEOUT` | `20` | HTTP timeout in seconds |
| `STAAN_SEARCH_EXTRA_SNIPPETS` | `True` | Ask the API to fetch the pages and return scored chunks |
| `STAAN_MAX_SNIPPETS_PER_URL` | `3` | Sent as `max_snippets` (the API accepts 1 to 10). The only lever on search size — see below |
| `STAAN_MIN_SNIPPET_SCORE` | `0.1` | Sent as `min_score`; chunks below it are filtered by the API |

Only the base URL is configurable: the search path (`v2/search/web`) is fixed in
`STAAN_SEARCH_PATH` because `format_staan` parses that version's response shape.

`count` is deliberately **not** sent: the API only accepts `count=10`, its own default, and answers
`400 Bad Request` with `count must be equal to 10` for anything else. A search therefore always
returns ten results.

### How much text a search sends to the model

`STAAN_MAX_SNIPPETS_PER_URL` is the only lever, and it is applied **server-side**. Both other
dimensions are fixed by the API: the result count is always ten, and a chunk is a text segment of
roughly 300 to 1800 characters with its heading context preserved
([Staan docs](https://docs.staan.ai/docs/web-for-ai#extra_snippets)). So:

```
size ≈ 10 results × max_snippets chunks × ~1000 characters   (+ 10 main snippets, unbounded)
```

The 300 to 1800 character range is documented for the chunks only. Each result also carries a main snippet, a separate field with no published size
limit.

The ceiling holds as long as Staan honours its
documented chunk size, and it does not cover the main snippets at all. Raising `max_snippets`
raises the cost of every search in proportion, and a larger tool response also counts toward the
conversation summarization budget, so it can trigger summarization earlier in a conversation.

## Behaviour

- **Market**: resolved per conversation from the UI language (`ContextDeps.language`), falling
  back to Django's `LANGUAGE_CODE` when the conversation carries none.
- **Results**: results without a usable snippet are dropped, so they pollute neither the model
  context nor the citations shown in the UI.
- **Return shape**: results keyed by rank — so the model can cite a source by its index — each
  with `url`, `title`, `snippets` and `published_date`. Only `metadata["sources"]` is read
  programmatically, to build the citations shown in the UI; the rest goes to the model as-is.
- **Errors**: a missing `STAAN_API_KEY` or `STAAN_API_URL` raises `ModelCannotRetry` before any
  request is made, naming the settings at fault. Rate limiting, server errors, timeouts and
  connection errors raise `ModelRetry`, and so does an empty result set, so the model searches
  again rather than answering from memory. Client errors raise `ModelCannotRetry`, which
  `last_model_retry_soft_fail` turns into an explanatory string returned to the model — the tool
  never surfaces that exception to its caller. A `ModelRetry` raised on the last allowed attempt
  is returned the same way.
- **Logging**: search failures log the status code and the bare endpoint only. Neither the user's
  query nor the provider's response body is logged — httpx renders the full request url, query
  string included, into `str(exc)`, so the exception is deliberately not interpolated into the
  log line.

## Limitations compared to Brave

| Brave capability | Staan equivalent |
|---|---|
| `safesearch` (we run `moderate`) | **none** — switching to Staan means no SafeSearch filtering |
| `spellcheck` | **none** |
| `country` | covered by `market` |
| `result_filter` | only `include_domains` / `exclude_domains`, POST-only, not implemented here |

**Supported markets**: `fr-fr`, `en-us`, `de-de`. Any other UI language silently falls back to
`en-us`.

The API also exposes `full_content` (`markdown` or `html`) to return whole page bodies. It is not
used: whole pages are unbounded in size, which would defeat the sizing described above — scored
chunks are what keep a search predictable.
