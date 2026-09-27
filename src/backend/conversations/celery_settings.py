"""Django configuration mixin for Celery broker, result backend and task limits."""

from celery.schedules import crontab
from configurations import values

# Providers the fetch_model_health command supports. Duplicated from the
# command's own PROVIDERS dict (chat.management.commands.fetch_model_health)
# because settings must not import that module, which imports Django models.
MODEL_HEALTH_POLL_PROVIDERS = ("albert",)


def crontab_from_string(value):
    """Build a celery crontab from a five-field cron string ("min hour dom month dow")."""
    fields = value.split()
    if len(fields) != 5:
        raise ValueError(
            "DEINDEX_INACTIVE_COLLECTIONS_CRON must have five space-separated fields "
            f"(minute hour day_of_month month day_of_week), got {value!r}."
        )
    minute, hour, day_of_month, month_of_year, day_of_week = fields
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


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
    # Both periodic tasks default to off: only Albert deployments have a health
    # endpoint to poll and RAG collections to clean.
    MODEL_HEALTH_POLL_PROVIDER = values.Value(
        "", environ_name="MODEL_HEALTH_POLL_PROVIDER", environ_prefix=None
    )
    # How often beat enqueues the poll. The command's cache lock, sized by
    # ModelHealthSettings.poll_interval_minutes, decides when a poll really runs.
    MODEL_HEALTH_POLL_INTERVAL_SECONDS = values.PositiveIntegerValue(
        60, environ_name="MODEL_HEALTH_POLL_INTERVAL_SECONDS", environ_prefix=None
    )
    # Five-field cron string ("0 2 * * *"). Empty disables the task.
    DEINDEX_INACTIVE_COLLECTIONS_CRON = values.Value(
        "", environ_name="DEINDEX_INACTIVE_COLLECTIONS_CRON", environ_prefix=None
    )

    @property
    def CELERY_BEAT_SCHEDULE(self):  # pylint: disable=invalid-name
        """Beat schedule built from the MODEL_HEALTH_POLL_* and DEINDEX_* settings."""
        schedule = {}
        if self.MODEL_HEALTH_POLL_PROVIDER:
            if self.MODEL_HEALTH_POLL_PROVIDER not in MODEL_HEALTH_POLL_PROVIDERS:
                raise ValueError(
                    f"MODEL_HEALTH_POLL_PROVIDER must be one of {MODEL_HEALTH_POLL_PROVIDERS}, "
                    f"got {self.MODEL_HEALTH_POLL_PROVIDER!r}."
                )
            interval = self.MODEL_HEALTH_POLL_INTERVAL_SECONDS
            if interval < 1:
                raise ValueError(
                    f"MODEL_HEALTH_POLL_INTERVAL_SECONDS must be at least 1, got {interval!r}."
                )
            schedule["fetch-model-health"] = {
                "task": "chat.tasks.fetch_model_health_task",
                "schedule": interval,
                "args": (self.MODEL_HEALTH_POLL_PROVIDER,),
                # A poll that waited a full interval in the queue is stale; drop it
                # so a worker outage does not produce a burst of polls on recovery.
                "options": {"expires": interval},
            }
        if self.DEINDEX_INACTIVE_COLLECTIONS_CRON:
            schedule["deindex-inactive-collections"] = {
                "task": "chat.tasks.deindex_inactive_collections_task",
                "schedule": crontab_from_string(self.DEINDEX_INACTIVE_COLLECTIONS_CRON),
            }
        return schedule
