"""Django configuration mixin for Sentry, Posthog, Langfuse and logging."""

import sys

import structlog
from configurations import values
from lasuite.configuration.values import SecretFileValue

from core.log_fields import find_provider_error, provider_errors_in_chain, safe_error_fields

# Run on every record, structlog or stdlib, before rendering. Stdlib `extra`
# attributes are deliberately not added: django.request passes the request object,
# whose repr carries the query string (?title=<user search>).
SHARED_LOG_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]


def _logged_exception(event_dict):
    """The exception a structlog event carries, however it was passed."""
    # django-structlog's Celery lines pass it itself: `task_failed` as
    # `exception` (with `error=str(exc)`), `task_retrying` as `reason`.
    for key in ("exception", "reason"):
        if isinstance(event_dict.get(key), BaseException):
            return event_dict[key]
    exc_info = event_dict.get("exc_info")
    if exc_info is True:  # logger.exception(), or exc_info=True
        return sys.exc_info()[1]
    if isinstance(exc_info, BaseException):
        return exc_info
    if isinstance(exc_info, tuple):
        return exc_info[1]
    return None


def scrub_provider_errors(_logger, _method_name, event_dict):
    """Name a provider error by type and status, never by message or traceback.

    A provider error's message carries the response body, which can echo the
    prompt or document content, and a traceback renders it along with every
    error it was raised from or while handling. So any line whose exception
    involves one keeps only its type and status. Other errors keep their
    traceback.
    """
    provider_error = find_provider_error(_logged_exception(event_dict))
    if provider_error is not None:
        for key in ("exception", "reason", "error", "exc_info"):
            event_dict.pop(key, None)
        event_dict.update(safe_error_fields(provider_error))
    return event_dict


def wrap_for_formatter(logger, name, event_dict):
    """`ProcessorFormatter.wrap_for_formatter`, also handing `exc_info` to stdlib.

    structlog keeps the exception in the event dict, where our formatters render
    it, but leaves the stdlib record's `exc_info` empty. Sentry's logging
    integration reads only the record, so `logger.exception()` would reach it as
    a bare message, without the exception or its stack trace.
    """
    args, kwargs = structlog.stdlib.ProcessorFormatter.wrap_for_formatter(logger, name, event_dict)
    exc_info = event_dict.get("exc_info")
    if exc_info:
        kwargs["exc_info"] = exc_info
    return args, kwargs


def configure_structlog():
    """Hand structlog events to stdlib logging, rendered by the LOGGING formatters."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *SHARED_LOG_PROCESSORS,
            scrub_provider_errors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# Event dict keys Sentry already shows on its own (message, level, logger, time).
SENTRY_LOG_META_KEYS = frozenset({"event", "exc_info", "timestamp", "level", "logger"})


def _structlog_event(hint):
    """The structlog event dict behind a Sentry event or breadcrumb, if any.

    A structlog line reaches Sentry as a stdlib record whose `msg` is the event
    dict, which Sentry would show as its repr: every field, as the title.
    """
    msg = getattr((hint or {}).get("log_record"), "msg", None)
    return msg if isinstance(msg, dict) else None


def _log_fields(log_event):
    """The fields of a structlog event, without the ones Sentry shows itself."""
    return {key: value for key, value in log_event.items() if key not in SENTRY_LOG_META_KEYS}


def scrub_sentry_event(event, hint):
    """Title structlog events by their name, and keep provider bodies out.

    A structlog line's fields go to `extra` and its `request_id` to a tag, so the
    event can be matched with its log lines. A provider error's message carries
    the response body, which can echo the prompt or document content: in the
    exception chain it is replaced by the HTTP status.
    """
    log_event = _structlog_event(hint)
    if log_event is not None:
        name = str(log_event.get("event"))
        event["logentry"] = {"message": name, "formatted": name, "params": []}
        event["extra"] = _log_fields(log_event)
        if log_event.get("request_id"):
            event.setdefault("tags", {})["request_id"] = log_event["request_id"]

    exc_info = (hint or {}).get("exc_info")
    errors = {
        type(error).__name__: error
        for error in provider_errors_in_chain(exc_info[1] if exc_info else None)
    }
    for value in event.get("exception", {}).get("values", []):
        error = errors.get(value.get("type"))
        if error is not None:
            value["value"] = f"status_code: {safe_error_fields(error)['status_code']}"
    return event


def scrub_sentry_breadcrumb(crumb, hint):
    """Name a structlog breadcrumb by its event, with its fields as data."""
    log_event = _structlog_event(hint)
    if log_event is not None:
        crumb["message"] = str(log_event.get("event"))
        crumb["data"] = _log_fields(log_event)
    return crumb


def scrub_transaction_queries(event, hint):  # pylint: disable=unused-argument
    """Drop query strings: integrations copy them whatever send_default_pii says."""
    event.get("request", {}).pop("query_string", None)
    for span in event.get("spans", []):
        data = span.get("data")
        if data:
            data.pop("http.query", None)
            data.pop("url.query", None)
    return event


class ObservabilitySettings:
    """Sentry, Posthog, Langfuse and logging."""

    # Sentry
    SENTRY_DSN = values.Value(None, environ_name="SENTRY_DSN", environ_prefix=None)
    SENTRY_TRACES_SAMPLE_RATE = values.FloatValue(
        None, environ_name="SENTRY_TRACES_SAMPLE_RATE", environ_prefix=None
    )

    # Posthog
    # Looks like "{'id': 'posthog_key', 'host': 'https://product.conversations.127.0.0.1.nip.io'}"
    POSTHOG_KEY = values.DictValue(None, environ_name="POSTHOG_KEY", environ_prefix=None)
    POSTHOG_MW_CAPTURE_EXCEPTIONS = values.BooleanValue(
        default=False, environ_name="POSTHOG_MW_CAPTURE_EXCEPTIONS", environ_prefix=None
    )

    # Client IPs are personal data: keep them out of the request logs
    DJANGO_STRUCTLOG_IP_LOGGING_ENABLED = False
    # Carry request_id/user_id into the Celery tasks a request enqueues
    DJANGO_STRUCTLOG_CELERY_ENABLED = True

    # Logging
    # Everything is logged to console; levels are set per logger with the
    # LOGGING_LEVEL_LOGGERS_* variables.
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        # Stdlib records (libraries using `logging`) only run through
        # `foreign_pre_chain`: scrub their provider errors there too.
        "formatters": {
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(),
                "foreign_pre_chain": [*SHARED_LOG_PROCESSORS, scrub_provider_errors],
            },
            # One JSON object per line, tracebacks included, for Loki.
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    # str, not the default repr: UUID ids must read as plain strings
                    structlog.processors.JSONRenderer(default=str),
                ],
                "foreign_pre_chain": [*SHARED_LOG_PROCESSORS, scrub_provider_errors],
            },
        },
        "filters": {
            "redact_file_stream_keys": {"()": "core.log_fields.RedactFileStreamKeys"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
            },
        },
        # Override root logger to send it to console
        "root": {
            "handlers": ["console"],
            "level": values.Value(
                "INFO", environ_name="LOGGING_LEVEL_LOGGERS_ROOT", environ_prefix=None
            ),
        },
        "loggers": {
            "core": {
                "handlers": ["console"],
                "level": values.Value(
                    "INFO",
                    environ_name="LOGGING_LEVEL_LOGGERS_APP",
                    environ_prefix=None,
                ),
                "propagate": False,
            },
            "conversations.security": {
                "handlers": ["console"],
                "level": values.Value(
                    "INFO",
                    environ_name="LOGGING_LEVEL_LOGGERS_SECURITY",
                    environ_prefix=None,
                ),
                "propagate": False,
            },
            # httpx (and httpx2, the OpenAI SDK transport) log every request url at
            # INFO, query string included: web search queries would reach the logs.
            # Set here rather than relying on langfuse doing it for httpx on import.
            "httpx": {"level": "WARNING"},
            "httpx2": {"level": "WARNING"},
            # Requests are logged by RequestLogMiddleware (django-structlog). Dockerflow's
            # summary would duplicate them, and uvicorn's access log has the query string.
            "request.summary": {"handlers": [], "propagate": False},
            "uvicorn.access": {"handlers": [], "propagate": False},
            # Its INFO success line logs task return values (parsed documents), and its
            # ERROR failure line the exception repr (a provider error's body).
            # django-structlog logs task_succeeded and task_failed instead; only
            # internal errors (CRITICAL) still come from here.
            "celery.app.trace": {"level": "CRITICAL"},
            # It logs each 4xx and 5xx response with its path: a file-stream path
            # carries a temporary key, live if the request was refused (405, 429).
            "django.request": {"filters": ["redact_file_stream_keys"]},
            # uvicorn configures its own handlers: route its server logs through ours.
            "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        },
    }

    # LLM Instrumentation
    LANGFUSE_ENABLED = values.BooleanValue(
        default=False, environ_name="LANGFUSE_ENABLED", environ_prefix=None
    )
    LANGFUSE_PUBLIC_KEY = values.Value(
        None, environ_name="LANGFUSE_PUBLIC_KEY", environ_prefix=None
    )
    LANGFUSE_SECRET_KEY = SecretFileValue(
        None, environ_name="LANGFUSE_SECRET_KEY", environ_prefix=None
    )
    LANGFUSE_HOST = values.Value(None, environ_name="LANGFUSE_HOST", environ_prefix=None)
    LANGFUSE_DEBUG = values.BooleanValue(
        default=False, environ_name="LANGFUSE_DEBUG", environ_prefix=None
    )
    LANGFUSE_MEDIA_UPLOAD_ENABLED = values.BooleanValue(
        default=False, environ_name="LANGFUSE_MEDIA_UPLOAD_ENABLED", environ_prefix=None
    )
