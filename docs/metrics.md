# Prometheus metrics of the backend

The backend ships an **opt-in** instrumentation, [django-prometheus](https://github.com/django-commons/django-prometheus). It is **disabled by default**: when `PROMETHEUS_METRICS_ENABLED` is unset, `django_prometheus` is not in `INSTALLED_APPS`, its middlewares are not installed, the database engine is left alone and `/metrics` is not routed.

## Enabling it

```bash
PROMETHEUS_METRICS_ENABLED=True
PROMETHEUS_API_KEY=<a long random secret>   # or PROMETHEUS_API_KEY_FILE
```

The application **refuses to start** with the metrics enabled and no key: the endpoint would otherwise answer to anybody.

Then scrape `GET /metrics` with the key as a bearer token:

```yaml
scrape_configs:
  - job_name: conversations-backend
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/conversations-api-key
    static_configs:
      - targets: ["conversations-backend:8000"]
```

If `SECURE_SSL_REDIRECT` is on (the `Production` configuration) and the scraper reaches the pods directly over plain http, set `PROMETHEUS_METRICS_SSL_REDIRECT_EXEMPT=True` so `/metrics` is not redirected to https.

The redirect does not protect the token: a scrape over http has already sent it in clear when the redirect answers. When the scraper crosses an untrusted network, configure it with an https target (`scheme: https` in the scrape config) so the token only travels over TLS.

## What is measured

- HTTP requests: counts and latency histograms, labelled by **view name**, method and status (`django_http_requests_latency_seconds_by_view_method`, `django_http_responses_total_by_status_view_method_total`, ...).
- SQL (unless `PROMETHEUS_DB_METRICS_ENABLED=False`): queries, errors and query duration (`django_db_execute_total`, `django_db_query_duration_seconds`, ...). Applies when `DB_ENGINE` is `django.db.backends.postgresql` or `django.db.backends.postgresql_psycopg2` (the default).

Specific to conversations:

| Metric | Labels | What it tells |
|---|---|---|
| `conversations_llm_request_duration_seconds` | `model`, `provider`, `agent`, `status` | Duration of each model request, the whole streamed answer included. `status` is `ok`, the HTTP status of the provider (`429`, `503`, ...), `connection_error`, `cancelled` (stop button, or the turn cut short) or `error`, also when a streamed answer fails midway |
| `conversations_llm_requests_inflight` | `model`, `provider` | Model requests not answered yet: the first sign that a model is saturated |
| `conversations_llm_tokens_total` | `model`, `provider`, `agent`, `kind` | Tokens sent (`input`) and received (`output`) by the requests that went through: a streamed answer failing midway counts none |
| `conversations_llm_time_to_first_token_seconds` | `model`, `provider` | Streamed chat requests only: time until the first part (text, tool call or reasoning) |
| `conversations_chat_streams_active` | `model` | Chat turns running, including those whose reader left |
| `conversations_chat_stream_duration_seconds` | `model`, `outcome` | Whole chat turns, including what runs after the reader left. `outcome` is `ok`, the error code shown to the user (`model_rate_limited`, `model_unavailable`, `model_connection_error`, ...), `cancelled` (stop button), `interrupted` (cut short past `MAX_TURN_DURATION` or by a shutdown; a reader leaving does not stop the turn) or `error` |
| `conversations_outgoing_request_duration_seconds` | `service`, `operation`, `status` | Calls to `albert` (RAG collections, documents, search), `brave`, `staan`, `web_page` (pages fetched for a web search) and `docs` |
| `conversations_outgoing_requests_inflight` | `service`, `operation` | Those calls not answered yet |
| `conversations_celery_queue_length` | `queue` | Tasks waiting on the Celery queue, read from the broker at each scrape (unless `PROMETHEUS_CELERY_QUEUE_METRICS_ENABLED=False`). Every replica reports the same number: aggregate with `max`, never `sum` |

`model` is the hrid of the model in the LLM configuration, `agent` the class of the agent (`ConversationAgent`, `TitleGenerationAgent`, `SummarizationAgent`, ...). The gauges are summed over the living uvicorn workers.

No label ever carries a path, a user, a conversation, a prompt, a url or a document name. A request that matches no route is counted under `<unnamed view>`.

Every sample carries a `hostname` label (the pod name in Kubernetes), so the series of several replicas never mix when scraped through one address.

The chat endpoint streams its answer: django-prometheus stops its latency timer when the streaming response is returned, not when the stream ends. Read `conversations_chat_stream_duration_seconds` for how long turns take, not the django latency of the chat view.

## How the endpoint is protected

| Layer | What it guarantees |
|---|---|
| Off by default | Nothing is installed, and `/metrics` is a 404, unless the deployment asks for it |
| Served on `/metrics`, not under `/api/` | The metrics are not reachable through the application ingress until a route is added on purpose |
| Bearer token | `core.middleware.PrometheusAuthMiddleware` refuses anything but `Authorization: Bearer <PROMETHEUS_API_KEY>`, compared in constant time. It fails closed: no key, no answer |
| First middleware | A refused call stops there: no session is created, no database or cache access is made |
| Maintenance mode | `/metrics` keeps answering while maintenance mode returns 503 elsewhere |
| Labels | No path, user or conversation identifier leaves the application |

The key is a long-lived shared secret. Give it through `PROMETHEUS_API_KEY_FILE` or a Kubernetes secret, keep TLS on wherever it travels, and rotate it by changing the value on both sides.

## uvicorn workers

uvicorn runs several worker processes and a scrape is answered by one of them. The workers therefore all write their numbers to one directory (prometheus_client's multiprocess mode), and whichever answers adds them up. Nothing has to be configured: the directory defaults to `<tmp>/conversations-prometheus-<uid>`, is created with mode `0700`, and the application refuses a directory owned by another user or a symbolic link. Set `PROMETHEUS_MULTIPROC_DIR` to put it elsewhere: it must be writable, and local to the host or the pod (it is **not** shared between replicas).

Known limit: uvicorn recycles its workers (`--limit-max-requests`) and has no hook to tell when one is gone. Every new worker writes new files, and the files of the workers that are gone must stay (their counters are part of the totals). The directory grows, and the scrape gets slower, until the container is replaced. Watch `scrape_duration_seconds` on long runs.

The container entrypoint empties the directory each time the container starts, before uvicorn starts its workers: a container restarted by docker keeps its `/tmp`, and its new workers would reuse the process ids, hence the files, of the old ones. Outside of a container, empty the directory before starting the application.

## Kubernetes (Helm chart)

For a Prometheus Operator inside the cluster (kube-prometheus-stack, for instance), the chart scrapes every backend pod directly:

```yaml
backend:
  metrics:
    enabled: true
  envVars:
    PROMETHEUS_API_KEY:
      secretKeyRef:
        name: backend
        key: PROMETHEUS_API_KEY

serviceMonitor:   # or podMonitor, whichever kind your Prometheus selects
  enabled: true
  labels:
    release: kube-prometheus-stack   # the label your Prometheus selects monitors by
```

- `backend.metrics.enabled` sets `PROMETHEUS_METRICS_ENABLED` and `PROMETHEUS_METRICS_SSL_REDIRECT_EXEMPT` on the backend pods only, never on the Celery worker and beat. A value set by hand in `backend.envVars` wins.
- The monitor presents a bearer token read from a Secret: the one named in `backend.metrics.apiKeySecret` when it is set, or else the one `PROMETHEUS_API_KEY` references (its `secretKeyRef` in `backend.envVars`). The chart refuses to render a monitor when the key does not come from a Secret, rather than letting every scrape fail with a 401.
- The Prometheus Operator reads that Secret itself: it has to be in the namespace of the monitor, and readable by the operator.
- If network policies restrict ingress to the namespace, allow the Prometheus pods to reach the backend pods on their `http` port (8000). Otherwise the target stays down, with no error on the application side.
- Check the target on the Prometheus targets page: one target per backend pod, labelled `job="backend"`.

## Celery

The Celery worker serves no request, so its metrics are never read. Leave `PROMETHEUS_METRICS_ENABLED` off for it.

Known limit: the work done in Celery is therefore not measured. Document parsing and OCR, project indexing (Albert collections and documents created from Celery) and conversation history summaries do not show up in the metrics above. Only the queue length tells whether the workers keep up.
