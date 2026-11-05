# Logging

The backend logs with [structlog](https://www.structlog.org/) and [django-structlog](https://django-structlog.readthedocs.io/). Every line is an event name plus named fields, so lines can be filtered on fields (in Loki or with `jq`) rather than parsed.

## Format

| Configuration | Output |
|---|---|
| `Production` (and `Staging`, `PreProduction`, `Demo`) | one JSON object per line, tracebacks included |
| `Development`, `Test` | structlog's readable console renderer |

The handlers and formatters are defined in `conversations/observability_settings.py`; `Production` only switches the console handler to the `json` formatter (`conversations/settings.py`).

A production line looks like:

```json
{"code": 200, "request": "GET /api/v1.0/config/", "event": "request_finished", "request_id": "03618b74-1826-46f0-9331-778d5bf224cd", "user_id": null, "logger": "django_structlog.middlewares.request", "level": "info", "timestamp": "2026-11-05T14:07:33.287270Z"}
```

Every line has `event`, `logger`, `level` and `timestamp` (ISO 8601, UTC). Libraries that log through the standard `logging` module (Django, Celery, uvicorn...) go through the same formatters, so they come out as JSON too, with their message as `event`.

### Seeing the JSON lines locally

There is no switch: temporarily give the `Development` class the same override as `Production`, and do not commit it:

```python
class Development(Base):
    ...
    LOGGING = {
        **Base.LOGGING,
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    }
```

Then restart the backend (`docker compose restart app-dev celery-dev`) and follow it with `make logs`, or pretty-print and filter with `jq`:

```bash
docker compose logs -f --no-log-prefix app-dev | jq -R 'fromjson? // .'
docker compose logs -f --no-log-prefix app-dev | jq -R 'fromjson? | select(.request_id == "...")'
```

In tests, the `json_logs` fixture (`src/backend/conftest.py`) renders records with the production formatter and returns the parsed lines.

## Following a request, a chat turn or a task

### Requests

`core.middleware.RequestLogMiddleware` (django-structlog) logs `request_started` and `request_finished` (or `request_failed`) for each request, and `streaming_finished` at the end of a streamed response. The `request` field is the method and the path only:

- the query string is never logged: it carries user input (e.g. a search);
- the temporary key of a `file-stream` path is replaced by `[redacted]`: it grants access to the file. Django's own `django.request` lines ("Method Not Allowed: <path>", logged for each 4xx and 5xx response) are redacted the same way (`core.log_fields.RedactFileStreamKeys`);
- the client IP is not logged (`DJANGO_STRUCTLOG_IP_LOGGING_ENABLED = False`).

Every line logged during the request, whatever module writes it, carries:

| Field | Value |
|---|---|
| `request_id` | the request's id, see below |
| `user_id` | the user's primary key, `null` when anonymous |

**Where `request_id` comes from.** `DockerflowMiddleware` takes the `X-Request-ID` header set by the ingress, or generates a uuid4 when there is none, and the request logs reuse that id. So a request can be matched with the ingress access log, which logs the same id.

ingress-nginx forwards a client-sent `X-Request-ID` unchanged. An id that does not look like one (more than 64 characters, or characters other than letters, digits, `.`, `_` and `-`) is ignored, and the request gets a generated id instead. A well-formed id chosen by a client is still used as is.

### Chat turns

A chat turn adds, on every line from the view on:

| Field | Value |
|---|---|
| `conversation_id` | the conversation |
| `message_id` | the assistant message, from the `stream_opened` line on |

The `chat.turn` logger traces the turn step by step (`turn_requested`, `turn_stored`, `stream_opened`, `run_finished`, `stream_closed`...), each line with the seconds elapsed since the turn started (`elapsed_s`). `make logs-turn` follows only those lines.

The ids also reach the lines written outside the request's own task or thread while the turn streams (the keepalive, the sync/async bridges): those run in a copy of the request's context.

### Celery tasks

A task queued during a request logs under that request's `request_id` and `user_id`, plus its own `task_id`. django-structlog carries the ids in the task message headers, and `DjangoStructLogInitStep` (registered in `conversations/celery_app.py`) binds them in the worker.

The task lifecycle is logged by django-structlog:

| Event | Where |
|---|---|
| `task_enqueued` | the process that queued the task (`child_task_id`, `child_task_name`) |
| `task_started` | the worker |
| `task_succeeded` | the worker, with `duration_ms` |
| `task_retrying` | the worker |
| `task_failed` | the worker, with `duration_ms` and the traceback |

Celery's own logging setup is disabled (`keep_django_logging` in `celery_app.py`), so the worker uses Django's `LOGGING` and the `-l` / `--loglevel` option of the `celery worker` command has no effect: use the variables below.

## Levels

| Logger | Level |
|---|---|
| root (everything not listed below, including `chat`) | `LOGGING_LEVEL_LOGGERS_ROOT`, default `INFO` |
| `core` | `LOGGING_LEVEL_LOGGERS_APP`, default `INFO` |
| `conversations.security` | `LOGGING_LEVEL_LOGGERS_SECURITY`, default `INFO` |
| `httpx`, `httpx2` | `WARNING`: at `INFO` they log every request url, query string included (web search queries) |
| `celery.app.trace` | `CRITICAL`: its `INFO` success line logs task return values (parsed documents) and its `ERROR` failure line the exception text; django-structlog logs `task_succeeded` and `task_failed` instead |
| `request.summary` (Dockerflow), `uvicorn.access` | off: requests are logged by `RequestLogMiddleware`, and uvicorn's access log has the query string |
| `uvicorn` | `INFO`, through our handler |

## What must never be logged

Logs are read by more people, and kept longer, than the data they describe. Never log, at any level:

- prompts, messages, or text derived from them (titles, summaries, search queries);
- document or file names, file contents;
- urls a user or a tool supplied (search results, fetched pages), query strings;
- emails or other personal data;
- provider response bodies: an LLM or RAG provider's error can echo the prompt or document content.

Log ids, counts, sizes, durations, status codes and error types instead. For an exception, log its type and status code with `core.log_fields.safe_error_fields`:

```python
import structlog

from core.log_fields import safe_error_fields

logger = structlog.get_logger(__name__)

try:
    ...
except Exception as exc:
    logger.warning("summarize_merge_failed", conversation_id=conversation.pk, **safe_error_fields(exc))
```

Do not pass `error=str(exc)` for an error that may come from a provider.

**Provider errors are also scrubbed automatically.** A structlog line whose exception involves a provider error (`pydantic_ai`'s `ModelAPIError` and subclasses, `httpx.HTTPStatusError`), including one it was raised from or while handling, loses its message and traceback and keeps `error_type` and `status_code` (`scrub_provider_errors` in `observability_settings.py`). This applies to `logger.exception`, `exc_info=True` and the exceptions django-structlog logs for Celery tasks, and to libraries logging through the standard `logging` module. It removes the exception, not text a library wrote into the message itself (e.g. `logger.error("failed: %s", exc)`).

When a failure needs its full detail, store it where access is controlled rather than in the logs: indexing failures keep the provider's response in the attachment's `processing_error`, for instance.

## Writing log lines

- Get a logger with `structlog.get_logger(__name__)`.
- The event is a `snake_case` name for what happened (`project_attachment_index_failed`), not a sentence; put the details in fields.
- Do not repeat what is already bound (`request_id`, `user_id`, `conversation_id`, `message_id`, `task_id`).
- Use `logger.exception(...)` (or `exc_info=True`) when the traceback helps; it is rendered in the `exception` field.
- To check a line in a test, use the `json_logs` fixture and assert on the fields, including that a user value is absent:

```python
def test_a_failure_names_the_attachment_not_the_file(json_logs):
    ...
    [line] = [line for line in json_logs() if line["event"] == "project_attachment_index_failed"]
    assert line["attachment_id"] == attachment.pk
    assert "hello.txt" not in str(json_logs())
```

## Sentry

When `SENTRY_DSN` is set, `ERROR` and `CRITICAL` lines become Sentry events, and `INFO` and `WARNING` lines the breadcrumbs attached to them (Sentry's default logging integration). `before_send` and `before_breadcrumb` (`observability_settings.py`) make structlog lines read well there:

- the event is titled by the log event name, with the line's fields as `extra`;
- `request_id` is set as a tag, to find the event's log lines;
- a logged exception is attached with its stack trace, unless it involves a provider error: the line was scrubbed first, so the event only has `error_type` and `status_code` in `extra`;
- in any event, including the exceptions the Django and Celery integrations capture, a provider error's message is replaced by `status_code: <status>`.

Request bodies and stack frame local variables are not sent (`max_request_body_size="never"`, `include_local_variables=False`), and `django_structlog.middlewares.request` is ignored: Sentry already captures failed requests.

## Querying in Loki

The fields are not Loki labels: parse the line with `json`, then filter. With your own stream selector:

```logql
{<stream selector>} | json | request_id = "03618b74-1826-46f0-9331-778d5bf224cd"
{<stream selector>} | json | logger = "chat.turn" | conversation_id = "<conversation uuid>"
{<stream selector>} | json | event = "task_failed"
```
