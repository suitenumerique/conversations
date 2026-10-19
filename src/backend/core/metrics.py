"""Prometheus metrics of the application, as served on /metrics.

Enabled by PROMETHEUS_METRICS_ENABLED and protected by
`core.middleware.PrometheusAuthMiddleware`, see docs/metrics.md.

Only imported when the metrics are enabled: the rest of the code goes through
`core.instrumentation`, which does not depend on prometheus_client.

Labels never carry a user, a conversation, a prompt, a url or a document name:
only the model hrid, the provider, the agent class, the service, the operation
and the status.
"""

import logging
import os
import re
import socket

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_safe

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.multiprocess import MultiProcessCollector

from conversations.celery_app import app as celery_app

logger = logging.getLogger(__name__)

HOSTNAME_LABEL = "hostname"

# A call to another service answers in milliseconds when all is well and in tens
# of seconds when that service is drowning: both ends have to be readable.
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
# A model request lasts from a fraction of a second (a title) to minutes (a long
# answer streamed by a saturated model): the agents allow up to 600 seconds.
LLM_BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600)
TIME_TO_FIRST_TOKEN_BUCKETS = (0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 30, 60)
# A chat stream spans every model request and tool call of a turn, up to
# MAX_TURN_DURATION (30 minutes by default) once its reader is gone.
STREAM_BUCKETS = (1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800)

LLM_REQUEST_DURATION = Histogram(
    "conversations_llm_request_duration_seconds",
    "Duration of the requests made to the models, streamed answer included",
    ["model", "provider", "agent", "status"],
    buckets=LLM_BUCKETS,
)
LLM_REQUESTS_INFLIGHT = Gauge(
    "conversations_llm_requests_inflight",
    "Requests made to the models that have not been answered yet",
    ["model", "provider"],
    # one value per worker process: add up those that are still alive
    multiprocess_mode="livesum",
)
LLM_TOKENS = Counter(
    "conversations_llm_tokens",
    "Tokens sent to (input) and received from (output) the models",
    ["model", "provider", "agent", "kind"],
)
LLM_TIME_TO_FIRST_TOKEN = Histogram(
    "conversations_llm_time_to_first_token_seconds",
    "Time between a streamed chat model request and its first part (text, tool call or reasoning)",
    ["model", "provider"],
    buckets=TIME_TO_FIRST_TOKEN_BUCKETS,
)

CHAT_STREAMS_ACTIVE = Gauge(
    "conversations_chat_streams_active",
    "Chat turns running, whether someone is still reading them or not",
    ["model"],
    multiprocess_mode="livesum",
)
CHAT_STREAM_DURATION = Histogram(
    "conversations_chat_stream_duration_seconds",
    "Duration of the chat turns, including what runs after the reader left",
    ["model", "outcome"],
    buckets=STREAM_BUCKETS,
)

OUTGOING_REQUEST_DURATION = Histogram(
    "conversations_outgoing_request_duration_seconds",
    "Duration of the HTTP calls made to the other services (Albert RAG, web search, Docs)",
    ["service", "operation", "status"],
    buckets=LATENCY_BUCKETS,
)
OUTGOING_REQUESTS_INFLIGHT = Gauge(
    "conversations_outgoing_requests_inflight",
    "HTTP calls to the other services that have not been answered yet",
    ["service", "operation"],
    multiprocess_mode="livesum",
)

LIVE_GAUGE_FILE = re.compile(r"^gauge_live[a-z]*_(?P<pid>\d+)\.db$")


def forget_dead_processes():
    """
    Drop the gauges of the worker processes that are gone.

    A gauge that is summed over the living processes is kept in one file per
    process, and prometheus_client only removes it when told the process died.
    gunicorn has a hook for that, uvicorn has none: whoever answers a scrape
    checks instead. The directory is local to this host, so are the pids.
    Counters and histograms are left alone: what a dead worker counted stays part
    of the totals.
    """
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not directory:
        return
    try:
        names = os.listdir(directory)
    except OSError:
        return
    pids = {int(m["pid"]) for m in map(LIVE_GAUGE_FILE.match, names) if m}
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            multiprocess.mark_process_dead(pid)
        except OSError:
            # it exists and is not ours to signal: alive is all that matters
            continue


class CeleryQueueCollector:
    """
    The number of tasks waiting on the default Celery queue, asked to the broker
    when the metrics are scraped.

    The workers have no endpoint of their own, and the queue is what tells that
    they are not keeping up: document parsing, project indexing and history
    summaries all land on it. One queue for the whole deployment: every replica
    reports the same number, which is to be read with max(), never summed.
    """

    def collect(self):
        """Yield the gauge, or nothing when the broker cannot be asked."""
        length = self.queue_length()
        if length is None:
            return
        gauge = GaugeMetricFamily(
            "conversations_celery_queue_length",
            "Tasks waiting on the default Celery queue, for the whole deployment "
            "(use max, not sum)",
            labels=["queue"],
        )
        gauge.add_metric([self.queue_name()], length)
        yield gauge

    @staticmethod
    def queue_name():
        """The queue the tasks are sent to: none of them names another one."""
        return celery_app.conf.task_default_queue

    def queue_length(self):
        """Ask the broker, quickly: a scrape must not hang on it."""
        try:
            with celery_app.connection_for_read() as connection:
                if connection.transport.driver_type != "redis":
                    return None
                connection.ensure_connection(max_retries=1, timeout=2)
                channel = connection.default_channel
                queue = self.queue_name()
                # kombu keeps one redis list per priority step
                keys = [
                    f"{queue}{channel.sep}{priority}" if priority else queue
                    for priority in channel.priority_steps
                ]
                return sum(channel.client.llen(key) for key in keys)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("could not read the celery queue length", exc_info=True)
            return None


class WorkerProcessesCollector:
    """
    The metrics of every worker process of this host.

    uvicorn runs several workers and the scrape is answered by one of them: the
    multiprocess collector reads what they all wrote to PROMETHEUS_MULTIPROC_DIR
    and adds it up, instead of reporting the numbers of that worker alone.
    """

    def collect(self):
        """Yield the aggregated metrics."""
        # a registry of its own: the collector registers itself in the one it is given
        yield from MultiProcessCollector(CollectorRegistry()).collect()


class HostnameLabelled:
    """
    The metrics of another collector, labelled with the name of this host.

    The label is for a scraper that goes through a load balancer (an ingress in
    front of several replicas): each scrape is then answered by a different
    replica, and without it their counters would land in the same series.
    """

    def __init__(self, collector):
        self.collector = collector
        self.hostname = socket.gethostname()

    def collect(self):
        """Yield the metrics with the hostname added to every sample."""
        for metric in self.collector.collect():
            labelled = Metric(metric.name, metric.documentation, metric.type)
            for sample in metric.samples:
                labelled.add_sample(
                    sample.name,
                    {**sample.labels, HOSTNAME_LABEL: self.hostname},
                    sample.value,
                    sample.timestamp,
                    sample.exemplar,
                )
            yield labelled


@require_safe
def metrics_view(request):  # pylint: disable=unused-argument
    """Serve the metrics in the Prometheus text format."""
    forget_dead_processes()
    registry = CollectorRegistry()
    registry.register(HostnameLabelled(WorkerProcessesCollector()))
    if settings.PROMETHEUS_CELERY_QUEUE_METRICS_ENABLED:
        registry.register(HostnameLabelled(CeleryQueueCollector()))
    return HttpResponse(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)
