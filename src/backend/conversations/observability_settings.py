"""Django configuration mixin for Sentry, Posthog, Langfuse and logging."""

from configurations import values
from lasuite.configuration.values import SecretFileValue


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

    # Logging
    # We want to make it easy to log to console but by default we log production
    # to Sentry and don't want to log to console.
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {
                "format": "{asctime} {name} {levelname} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",
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
