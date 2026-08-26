"""Django configuration mixin for Celery broker, result backend and task limits."""

from configurations import values


class CelerySettings:
    """Celery broker, result backend and task limits."""

    # Celery
    # Broker uses Redis db 0 to avoid colliding with the cache (db 1 in production,
    # db 2 in development).
    CELERY_BROKER_URL = values.Value(
        "redis://redis:6379/0", environ_name="CELERY_BROKER_URL", environ_prefix=None
    )
    # Result backend: stores task return values so a request can await a task's
    # result. Needed by the conversation document-parse task, which the chat turn
    # blocks on to get the parsed content back; fire-and-forget tasks (project
    # indexing) do not use it. Shares Redis db 0 with the broker - Celery keeps
    # result keys in their own `celery-task-meta-*` namespace.
    CELERY_RESULT_BACKEND = values.Value(
        "redis://redis:6379/0", environ_name="CELERY_RESULT_BACKEND", environ_prefix=None
    )
    # How long unconsumed task results stay in Redis. The document-parse caller
    # forgets its result right after reading it, so this only covers results the
    # caller never read (e.g. a parse finishing after the caller timed out).
    # Those payloads can be whole parsed documents, so keep the window short
    # (1h) rather than Celery's 24h default.
    CELERY_RESULT_EXPIRES = values.IntegerValue(
        3600,
        environ_name="CELERY_RESULT_EXPIRES",
        environ_prefix=None,
    )
    # Broker-specific tuning passed through to the Redis transport (e.g. visibility_timeout).
    # Empty means defaults; raise visibility_timeout if any task can run longer than 1h.
    CELERY_BROKER_TRANSPORT_OPTIONS = values.DictValue(
        {},
        environ_name="CELERY_BROKER_TRANSPORT_OPTIONS",
        environ_prefix=None,
    )
    # Maps task names to queues (e.g. {"chat.tasks.*": {"queue": "heavy"}}) so heavy and
    # fast tasks can run on separate workers. Empty means everything uses the default queue.
    CELERY_TASK_ROUTES = values.DictValue(
        {},
        environ_name="CELERY_TASK_ROUTES",
        environ_prefix=None,
    )
    # Per-task wall-clock budget. The soft limit raises SoftTimeLimitExceeded, which the
    # parse path catches and records as a visible FAILED state; the hard limit SIGKILLs the
    # worker child (prefork pool) so a runaway or malicious parse (zip bomb, entity blowup)
    # can't pin a worker indefinitely or grow memory unbounded. Eager mode ignores both.
    CELERY_TASK_SOFT_TIME_LIMIT = values.IntegerValue(
        180,
        environ_name="CELERY_TASK_SOFT_TIME_LIMIT",
        environ_prefix=None,
    )
    CELERY_TASK_TIME_LIMIT = values.IntegerValue(
        300,
        environ_name="CELERY_TASK_TIME_LIMIT",
        environ_prefix=None,
    )
    # Max seconds a chat turn waits for the conversation document-parse task result
    # before giving up with a RAG error. Set above CELERY_TASK_TIME_LIMIT (the task's
    # own hard cap) plus expected queue wait so a slow-but-progressing parse is not
    # cut off here; the task time limit, not this, is the safety cap on a runaway
    # parse. Ignored in eager mode, where the task runs inline.
    DOCUMENT_PARSE_RESULT_TIMEOUT_SECONDS = values.IntegerValue(
        360,
        environ_name="DOCUMENT_PARSE_RESULT_TIMEOUT_SECONDS",
        environ_prefix=None,
    )
