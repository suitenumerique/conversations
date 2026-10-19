"""Hooks the application calls to be measured, cheap when nothing is measured.

The Prometheus metrics are opt-in (PROMETHEUS_METRICS_ENABLED). This module is
what the rest of the code imports: it has no dependency on prometheus_client, and
only loads `core.metrics`, where the metrics are defined, once they are enabled.
With the metrics off, every hook here is a test of a setting and nothing else.

Labels never carry a user, a conversation, a prompt, a url or a document name.
"""

import asyncio
import time
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings

import httpx
from pydantic_ai.capabilities import Hooks
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError


def _metrics():
    """The metrics module, loaded on first use so that prometheus_client stays optional."""
    # Imported here on purpose: `core.metrics` imports prometheus_client and defines the
    # metrics, which must not happen when they are disabled.
    from core import metrics  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    return metrics


def _provider_label(configuration):
    """The provider of a model configuration, as a label."""
    if configuration.provider is not None:
        return configuration.provider.hrid
    # built-in pydantic-ai models are named "provider:model"
    provider, _, _model = configuration.model_name.partition(":")
    return provider or "unknown"


def _llm_error_status(error):
    """The status label of a failed model request."""
    if isinstance(error, ModelHTTPError):
        return str(error.status_code)
    if isinstance(error, ModelAPIError):
        return "connection_error"
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    return "error"


class StreamedRequest:
    """What the reader of a streamed model request saw go wrong, for the request hook."""

    def __init__(self):
        self.error_status = None


# The streamed model request being read in this task. pydantic-ai raises the errors of
# a stream where it is read, then cancels the task the request hook runs in, so the
# hook only ever sees CancelledError: the reader leaves what went wrong here instead.
# Set before the stream is opened, so the task of the hook, created then, sees it too.
_streamed_request = ContextVar("streamed_request", default=None)


def llm_metrics_hooks(configuration, agent_name):
    """
    A pydantic-ai capability measuring every model request of an agent, or None when
    the metrics are disabled.

    It wraps the whole request: for a streamed one, until its last part was received,
    so the duration is what the user waited for the model. A streamed request that
    fails midway is counted under what its reader saw go wrong (see
    `streamed_model_request`), and its tokens are not counted.
    """
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return None

    metrics = _metrics()
    model = configuration.hrid
    provider = _provider_label(configuration)
    hooks = Hooks()

    @hooks.on.model_request
    async def _measure_model_request(ctx, *, request_context, handler):  # pylint: disable=unused-argument
        inflight = metrics.LLM_REQUESTS_INFLIGHT.labels(model=model, provider=provider)
        inflight.inc()
        start = time.perf_counter()
        status = "error"
        try:
            response = await handler(request_context)
            status = "ok"
            usage = response.usage
            for kind, tokens in (("input", usage.input_tokens), ("output", usage.output_tokens)):
                metrics.LLM_TOKENS.labels(
                    model=model, provider=provider, agent=agent_name, kind=kind
                ).inc(tokens or 0)
            return response
        except BaseException as error:
            status = _llm_error_status(error)
            streamed = _streamed_request.get()
            if status == "cancelled" and request_context.streaming and streamed is not None:
                status = streamed.error_status or status
            raise
        finally:
            inflight.dec()
            metrics.LLM_REQUEST_DURATION.labels(
                model=model, provider=provider, agent=agent_name, status=status
            ).observe(time.perf_counter() - start)

    return hooks


def observe_time_to_first_token(configuration, seconds):
    """Record how long a streamed chat model request took to send its first part."""
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return
    _metrics().LLM_TIME_TO_FIRST_TOKEN.labels(
        model=configuration.hrid, provider=_provider_label(configuration)
    ).observe(seconds)


def streamed_model_request(configuration):
    """
    Measure a streamed chat model request from where it is read. Called before the
    request is sent, it returns what to read its events through.

        observe = streamed_model_request(configuration)
        async with node.stream(run_ctx) as request_stream:
            async for event in observe(request_stream):
                ...

    `observe` passes the events through, recording how long the first part took, and
    tells the request hook what went wrong when the stream fails midway, which the
    hook cannot see. A reader that stops on its own, as the stop button does, leaves
    the request counted as cancelled.

    What it sets for the hook is never reset: the caller is an async generator, which
    a shutdown may close from another context, where a reset would fail. The next
    streamed request sets its own, and the hook only reads it for a streamed request.

    With the metrics off, the events are handed back untouched.
    """
    if not settings.PROMETHEUS_METRICS_ENABLED:
        return lambda events: events

    request = StreamedRequest()
    _streamed_request.set(request)
    started = time.perf_counter()
    return lambda events: _observed_events(configuration, events, started, request)


async def _observed_events(configuration, events, started, request):
    """Pass the events through, timing the first one and noting why the stream failed."""
    first_part_seen = False
    try:
        async for event in events:
            if not first_part_seen:
                first_part_seen = True
                observe_time_to_first_token(configuration, time.perf_counter() - started)
            yield event
    except Exception as error:
        request.error_status = _llm_error_status(error)
        raise


class ObservedStream:
    """What the chat stream tells about how it ended, when it handled an error itself."""

    def __init__(self):
        self.outcome = None


@contextmanager
def chat_stream(model):
    """
    Measure a chat answer stream.

        with chat_stream(model_hrid) as observed:
            ...
            observed.outcome = "model_rate_limited"  # an error turned into an error frame

    The outcome is `ok`, the error code the stream reported, `cancelled` when the user
    stopped it, `interrupted` when the turn was cut short from outside (past
    MAX_TURN_DURATION, or the process shutting down), `error` otherwise. A reader
    leaving is none of these: the turn keeps running without it.
    """
    observed = ObservedStream()
    if not settings.PROMETHEUS_METRICS_ENABLED:
        yield observed
        return

    metrics = _metrics()
    active = metrics.CHAT_STREAMS_ACTIVE.labels(model=model)
    active.inc()
    start = time.perf_counter()
    outcome = "error"
    try:
        yield observed
        outcome = observed.outcome or "ok"
    except GeneratorExit, asyncio.CancelledError:
        outcome = "interrupted"
        raise
    finally:
        active.dec()
        metrics.CHAT_STREAM_DURATION.labels(model=model, outcome=outcome).observe(
            time.perf_counter() - start
        )


class ObservedRequest:
    """What the caller tells about the outgoing request it is making."""

    def __init__(self):
        self.status = None


@contextmanager
def outgoing_request(service, operation):
    """
    Time an HTTP call to another service, from sync or async code.

        with outgoing_request("albert", "search") as observed:
            response = await client.post(...)
            observed.status = response.status_code
            response.raise_for_status()

    The status label is the HTTP status the caller reported, `timeout` when the call
    was given up on, `cancelled` when the task was, `error` when it never got an answer.
    Neither the url nor a document id is ever a label: `operation` names the endpoint.
    """
    observed = ObservedRequest()
    if not settings.PROMETHEUS_METRICS_ENABLED:
        yield observed
        return

    metrics = _metrics()
    inflight = metrics.OUTGOING_REQUESTS_INFLIGHT.labels(service=service, operation=operation)
    inflight.inc()
    start = time.perf_counter()
    status = "error"
    try:
        yield observed
        status = str(observed.status) if observed.status is not None else "unknown"
    except httpx.TimeoutException:
        status = "timeout"
        raise
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except BaseException:
        # raise_for_status after the caller reported the status: keep the status
        if observed.status is not None:
            status = str(observed.status)
        raise
    finally:
        inflight.dec()
        metrics.OUTGOING_REQUEST_DURATION.labels(
            service=service, operation=operation, status=status
        ).observe(time.perf_counter() - start)
