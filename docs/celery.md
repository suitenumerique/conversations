# Celery

Celery runs background tasks off the request path: the Django app enqueues a
message on a **broker** (Redis), and a separate **worker** process executes the
task. Use it for slow or unreliable work (file parsing, RAG indexing, anything
that shouldn't block an HTTP response).

## Architecture

```text
Django app  --.delay()-->  Redis (broker, db 0)  -->  Celery worker  -->  runs the task
```

- **Broker** — Redis db 0 (`CELERY_BROKER_URL`). Carries task messages. Required.
  Kept on db 0 so it doesn't collide with the cache (db 1 in prod, db 2 in dev).
- **Worker** — long-running process that consumes the queue and runs tasks.
  Scales independently from the web server (more replicas = more throughput).
- **Beat** — scheduler that enqueues tasks on a cron/interval. The schedule
  comes from `CELERY_BEAT_SCHEDULE`, built from env settings. See
  [Periodic tasks](#periodic-tasks).
- **Result backend** — Redis db 0 (`CELERY_RESULT_BACKEND`). Results expire
  after `CELERY_RESULT_EXPIRES` seconds. Only the conversation document-parse
  task reads it. The summarization and debug tasks still write a result; the
  index and periodic tasks set `ignore_result=True`. See
  [Tasks and results](#tasks-and-results).

## Files

| Path | Purpose |
|------|---------|
| `conversations/celery_app.py` | Celery app; bootstraps django-configurations and autodiscovers tasks |
| `conversations/__init__.py` | Imports the app so it loads on Django startup |
| `conversations/celery_settings.py` | `CELERY_*` settings and the `CELERY_BEAT_SCHEDULE` property |
| `conversations/settings.py` | Mixes `CelerySettings` into `Base` (eager mode in `Test`) |
| `<app>/tasks.py` | Task definitions, auto-discovered from every app in `INSTALLED_APPS` |
| `core/tasks.py` | `debug_add` — trivial task used to verify the setup |
| `core/management/commands/celery_check.py` | Enqueues `debug_add` to check the worker + broker |

## Settings

In `conversations/celery_settings.py` (`CelerySettings`, mixed into `Base`):

- `CELERY_BROKER_URL` — default `redis://redis:6379/0`, override via env.
- `CELERY_RESULT_BACKEND` — default `redis://redis:6379/0`. Stores task return
  values so a caller can await a result.
- `CELERY_RESULT_EXPIRES` — default `3600` seconds. How long an unread task
  result stays in Redis.
- `CELERY_BROKER_TRANSPORT_OPTIONS` — Redis transport tuning. Empty = defaults.
  Raise `visibility_timeout` if any task can run longer than 1h (default 3600s),
  otherwise it gets redelivered and runs twice.
- `CELERY_TASK_ROUTES` — maps task names to queues, e.g.
  `{"chat.tasks.*": {"queue": "heavy"}}`. Empty = everything on the default queue.
- `MODEL_HEALTH_POLL_PROVIDER` — default `""` (off). The provider name beat
  polls for model health, e.g. `"albert"`.
- `MODEL_HEALTH_POLL_INTERVAL_SECONDS` — default `60`. How often beat enqueues
  the poll task.
- `DEINDEX_INACTIVE_COLLECTIONS_CRON` — default `""` (off). Five-field cron
  string for the de-index task.
- `ARENA_PURGE_CONTENT_CRON` — default `""` (off). Five-field cron string for
  the Arena retention purge.

In `Test`: `CELERY_TASK_ALWAYS_EAGER = True` — tasks run synchronously in-process,
no broker or worker needed during tests.

## Running locally

```bash
make run-celery     # start only the worker (also: make run-backend starts it too)
make logs           # app logs;  docker compose logs -f celery-dev  for worker logs
```

Verify the wiring end to end (worker must be running):

```bash
docker compose run --rm app-dev python manage.py celery_check
# -> "Task sent to the broker: id=..."  then look for "debug_add(2, 3) = 5" in the worker logs
```

## Writing a task

Put tasks in `<app>/tasks.py`; they're auto-discovered.

```python
from conversations.celery_app import app

@app.task(bind=True, max_retries=3)
def process_attachment(self, attachment_id):
    ...
```

Enqueue with `process_attachment.delay(attachment_id)`. Retries, `autoretry_for`,
and `on_failure` callbacks all work without a result backend.

## Tasks and results

A result backend exists (`CELERY_RESULT_BACKEND`), but a task returns a value
only when a caller awaits it with `AsyncResult.get()`. The conversation
document-parse task is the only one that does this: the chat turn blocks on
its result to get the parsed content back. The summarization and debug tasks
are fire-and-forget but still write a result that expires unread. The index
and periodic tasks set `ignore_result=True`, so they never write a
`celery-task-meta-*` result. Those tasks track their outcome where the rest of
the app can read it:

- **Coarse status** (pending / processing / done / failed) → a field on the
  related model (Postgres), polled via the API.
- **Fine progress** (e.g. page 3/10 for a progress bar) → a Redis cache key
  keyed by the object id, polled via a small endpoint.

Use `AsyncResult.get()` / `.status` for a new task only when a caller must
await the return value directly; otherwise keep `ignore_result=True` and track
the outcome on a model or cache key, as above.

## Periodic tasks

Celery beat enqueues three tasks, built into `CELERY_BEAT_SCHEDULE` by
`conversations/celery_settings.py`:

- `fetch-model-health` runs `chat.tasks.fetch_model_health_task`, which calls
  the `fetch_model_health` management command for one provider, on an
  interval schedule.
- `deindex-inactive-collections` runs
  `chat.tasks.deindex_inactive_collections_task`, which calls the
  `deindex_inactive_collections` management command, on a cron schedule.
- `purge-arena-content` runs `chat.tasks.purge_arena_content_task`, which
  calls the `purge_arena_content` management command, on a cron schedule set
  by `ARENA_PURGE_CONTENT_CRON` (default `""`, off). Set it daily wherever the
  Arena is enabled; see [Arena](arena.md#retention).

All entries are off by default: only Albert deployments have a model-health
endpoint to poll and RAG collections to clean, and only deployments with the
Arena enabled have Arena content to purge. Four env settings control them:

- `MODEL_HEALTH_POLL_PROVIDER` — default `""` (off). Set to `"albert"` to turn
  on the poll entry. An unknown provider name raises `ValueError` when
  settings load, so every process (web, worker, beat) fails to start.
- `MODEL_HEALTH_POLL_INTERVAL_SECONDS` — default `60`. How often beat enqueues
  the poll. Must be at least `1`; a lower value raises `ValueError` the same
  way, like a bad cron string.
- `DEINDEX_INACTIVE_COLLECTIONS_CRON` — default `""` (off). A five-field cron
  string turns on the de-index entry.
- `ARENA_PURGE_CONTENT_CRON` — default `""` (off). A five-field cron string
  turns on the Arena purge entry.

The cron strings and the interval are all evaluated in UTC: `TIME_ZONE =
"UTC"` in `conversations/settings.py`, and `CELERY_TIMEZONE` is not set, so
Celery beat also uses UTC. This matches the old Kubernetes CronJob, which
ran on the cluster's UTC clock.

The poll interval only sets how often beat tries. The `fetch_model_health`
command takes its own cache lock, sized by
`ModelHealthSettings.poll_interval_minutes` (an admin singleton), so a shorter
beat interval only produces cheap "Skipping" runs; the lock decides when a
poll really runs. The poll entry also sets `options={"expires": interval}`:
a poll that waited a full interval in the queue is stale and Celery drops it,
so a worker outage does not produce a burst of polls on recovery. The
de-index entry has no expiry, so a missed run still happens when the worker
recovers.

`DEINDEX_INACTIVE_COLLECTIONS_CRON` and `ARENA_PURGE_CONTENT_CRON` fields
follow cron field order: `minute hour day_of_month month day_of_week`. A
string with a field count other than five raises `ValueError` when settings load, so every process (web, worker,
beat) fails to start.

When both `day_of_month` and `day_of_week` are restricted, Celery runs the
task only when both fields match. A Kubernetes CronJob (Vixie cron) runs it
when either field matches. `0 2 1 * mon` ran on the 1st and on every Monday
in Kubernetes. In Celery beat it runs only on a Monday that is the 1st.
Restrict one day field when you port such a string.

To run beat locally, set the env vars and start beat directly; the
`celery-dev` compose service runs only the worker:

```bash
docker compose run --rm app-dev celery -A conversations.celery_app beat -l INFO --schedule=/tmp/celerybeat-schedule
```

Pass `--schedule`. Without it, beat writes its `celerybeat-schedule` file into
the bind-mounted `src/backend` directory, so a host-side `git status` shows an
untracked file after every local run.

### Queues

All periodic tasks run on the default queue, the same queue as the
conversation document-parse task that a chat turn awaits. A long de-index run
can delay a parse behind it. To isolate them, route the periodic tasks to
their own queue with `CELERY_TASK_ROUTES` and add a second
`backend.celeryWorkers` entry (Helm) that consumes that queue.
`deindex_inactive_collections_task` sets its own time limits,
`DEINDEX_TASK_SOFT_TIME_LIMIT` (1500 s) and `DEINDEX_TASK_TIME_LIMIT`
(1800 s), defined in `chat/constants.py`, because the global
`CELERY_TASK_SOFT_TIME_LIMIT` / `CELERY_TASK_TIME_LIMIT` (180 s / 300 s) are
too short for a full de-index run.

## Deployment (Helm)

Defined under `backend` in `src/helm/conversations/values.yaml`:

- `celeryWorkers` — a list of worker deployments (name, replicas, args, probes).
  Add entries with `-Q <queue>` args to run dedicated pools per queue.
- `celeryBeat` — single scheduler deployment (`enabled: true`).

Templates: `templates/backend_celery_worker.yaml`, `templates/backend_celery_beat.yaml`.
Liveness/readiness probes use `celery -A conversations.celery_app inspect ping`.

The env vars in `backend.envVars` replace the `modelHealthCronJob` and
`deindexCronJob` values removed in chart 0.0.10.
