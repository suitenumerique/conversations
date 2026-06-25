# Celery

Celery runs background tasks off the request path: the Django app enqueues a
message on a **broker** (Redis), and a separate **worker** process executes the
task. Use it for slow or unreliable work (file parsing, RAG indexing, anything
that shouldn't block an HTTP response).

## Architecture

```
Django app  --.delay()-->  Redis (broker, db 0)  -->  Celery worker  -->  runs the task
```

- **Broker** — Redis db 0 (`CELERY_BROKER_URL`). Carries task messages. Required.
  Kept on db 0 so it doesn't collide with the cache (db 1 in prod, db 2 in dev).
- **Worker** — long-running process that consumes the queue and runs tasks.
  Scales independently from the web server (more replicas = more throughput).
- **Beat** — scheduler that enqueues tasks on a cron/interval. Wired up but
  idle until a periodic task exists.
- **Result backend** — **not configured** (fire-and-forget). Tasks track their
  own outcome on DB models / cache, not via Celery results. See
  [Tasks and results](#tasks-and-results).

## Files

| Path | Purpose |
|------|---------|
| `conversations/celery_app.py` | Celery app; bootstraps django-configurations and autodiscovers tasks |
| `conversations/__init__.py` | Imports the app so it loads on Django startup |
| `conversations/settings.py` | `CELERY_*` settings (in `Base`; eager mode in `Test`) |
| `<app>/tasks.py` | Task definitions, auto-discovered from every app in `INSTALLED_APPS` |
| `core/tasks.py` | `debug_add` — trivial task used to verify the setup |
| `core/management/commands/celery_check.py` | Enqueues `debug_add` to check the worker + broker |

## Settings

In `Base` (`conversations/settings.py`):

- `CELERY_BROKER_URL` — default `redis://redis:6379/0`, override via env.
- `CELERY_BROKER_TRANSPORT_OPTIONS` — Redis transport tuning. Empty = defaults.
  Raise `visibility_timeout` if any task can run longer than 1h (default 3600s),
  otherwise it gets redelivered and runs twice.
- `CELERY_TASK_ROUTES` — maps task names to queues, e.g.
  `{"chat.tasks.*": {"queue": "heavy"}}`. Empty = everything on the default queue.

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

There is **no result backend**, so `AsyncResult.get()` / `.status` /
`update_state()` are unavailable. Track task outcomes where the rest of the app
can read them:

- **Coarse status** (pending / processing / done / failed) → a field on the
  related model (Postgres), polled via the API.
- **Fine progress** (e.g. page 3/10 for a progress bar) → a Redis cache key
  keyed by the object id, polled via a small endpoint.

You only need to add `CELERY_RESULT_BACKEND` (e.g. `redis://redis:6379/3`) if you
use `chord` / `group().get()` (parallel fan-out + join) or want to poll Celery
directly with `AsyncResult`. It's a one-line, reversible change when that day comes.

## Deployment (Helm)

Defined under `backend` in `src/helm/conversations/values.yaml`:

- `celeryWorkers` — a list of worker deployments (name, replicas, args, probes).
  Add entries with `-Q <queue>` args to run dedicated pools per queue.
- `celeryBeat` — single scheduler deployment (`enabled: true`).

Templates: `templates/backend_celery_worker.yaml`, `templates/backend_celery_beat.yaml`.
Liveness/readiness probes use `celery -A conversations.celery_app inspect ping`.
