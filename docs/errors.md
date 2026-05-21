# LLM Provider Error Handling

When the LLM provider fails, the backend emits a typed error code in the Vercel AI SDK stream. The frontend reads this code and displays a specific message.

## Error mapping

| Provider failure | pydantic-ai exception | Error code | User-facing message |
|---|---|---|---|
| HTTP 5xx except 503 (500, 502, 504…) | `ModelHTTPError` (`status_code >= 500`) | `model_unavailable` | "The AI inference provider is temporarily unavailable. Please try again later." |
| HTTP 503 (service busy) | `ModelHTTPError` (`status_code == 503`) | `model_busy` | "The AI inference provider is too busy. Please try again later." |
| HTTP 429 (rate limit) | `ModelHTTPError` (`status_code == 429`) | `model_rate_limited` | "The AI inference provider is overloaded. Please try again in a few minutes." |
| HTTP 404 (not found) | `ModelHTTPError` (`status_code == 404`) | `model_not_found` | "We encountered an internal error. Our team has been alerted. Please try again later." |
| HTTP 422 (validation error) | `HTTPValidationError` (`status_code == 422`) | `model_wrong_type` | "We encountered an internal error. Our team has been alerted. Please try again later." |
| No TCP connection, DNS failure, timeout | `ModelAPIError` | `model_connection_error` | "Unable to reach the AI inference provider. Please try again later." |
| Any other error | uncaught → generic Vercel AI SDK error | `generic` | "Sorry, an error occurred. Please try again." |

## Status page link

Set `STATUS_PAGE_URL` to display a "Check service status" link alongside provider availability errors (`model_unavailable`, `model_busy`, `model_rate_limited`, `model_connection_error`). Configuration errors (`model_not_found`, `model_wrong_type`) show a generic internal error message and do not display a status link.

```bash
STATUS_PAGE_URL=https://albert.sites.beta.gouv.fr/about/status/
```

The link is omitted when the variable is unset.

## Implementation

- **Backend:** `src/backend/chat/clients/pydantic_ai.py` — `_stream_content` catches provider exceptions and emits `ErrorPart` events.
- **Frontend:** `src/frontend/apps/conversations/src/features/chat/components/ChatError.tsx` — renders the message based on `errorType` prop.
- **Config:** `src/backend/conversations/settings.py` and `src/backend/core/api/viewsets.py` — `STATUS_PAGE_URL` is exposed via the `config/` API.
