"""
Test the measurements the application takes of itself: model requests, chat streams,
calls to other services and the Celery queue.
"""

import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

from django.contrib.sessions.backends.cache import SessionStore

import httpx
import pytest
import respx
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from core import instrumentation, metrics

from chat.agent_rag.document_rag_backends.albert_rag_backend import AlbertRagBackend
from chat.agents.conversation import TitleGenerationAgent
from chat.clients.exceptions import StreamCancelException
from chat.docs_client import DocsClient, DocsFetchError
from chat.tools.web_search_brave import _query_brave_api_with_endpoint_async
from chat.tools.web_search_staan import STAAN_SEARCH_URL, staan_search

OUTGOING_DURATION = "conversations_outgoing_request_duration_seconds_count"
OUTGOING_INFLIGHT = "conversations_outgoing_requests_inflight"
LLM_DURATION = "conversations_llm_request_duration_seconds_count"
LLM_INFLIGHT = "conversations_llm_requests_inflight"
LLM_TOKENS = "conversations_llm_tokens_total"
STREAM_DURATION = "conversations_chat_stream_duration_seconds_count"
STREAMS_ACTIVE = "conversations_chat_streams_active"

# Matches the ALBERT_API_URL default in the Test settings class.
ALBERT_SEARCH_URL = "https://albert.api.etalab.gouv.fr/v1/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def sample(name, **labels):
    """The value of a sample of the default registry, 0 when it does not exist."""
    return REGISTRY.get_sample_value(name, labels) or 0


def total(name, **labels):
    """The sum of the samples of the default registry that carry these labels."""
    return sum(
        found.value
        for family in REGISTRY.collect()
        for found in family.samples
        if found.name == name and labels.items() <= found.labels.items()
    )


def model_configuration(hrid, provider_hrid="test-provider"):
    """The parts of an LLModel the measurements read."""
    return SimpleNamespace(
        hrid=hrid, provider=SimpleNamespace(hrid=provider_hrid), model_name="a-model"
    )


@pytest.fixture(name="metrics_enabled")
def metrics_enabled_fixture(settings):
    """Turn the measurements on, as PROMETHEUS_METRICS_ENABLED does."""
    settings.PROMETHEUS_METRICS_ENABLED = True
    return settings


# -- outgoing_request --------------------------------------------------------------


def test_instrumentation_outgoing_request_disabled(settings):
    """With the metrics off a call is not measured, and goes through untouched."""
    settings.PROMETHEUS_METRICS_ENABLED = False

    with instrumentation.outgoing_request("test-off", "op") as observed:
        observed.status = 200

    assert sample(OUTGOING_DURATION, service="test-off", operation="op", status="200") == 0


@pytest.mark.usefixtures("metrics_enabled")
def test_instrumentation_outgoing_request_counts_the_status():
    """A call is counted under the status its caller reported, and is in flight meanwhile."""
    labels = {"service": "test-status", "operation": "op"}

    with instrumentation.outgoing_request("test-status", "op") as observed:
        assert sample(OUTGOING_INFLIGHT, **labels) == 1
        observed.status = 201

    assert sample(OUTGOING_INFLIGHT, **labels) == 0
    assert sample(OUTGOING_DURATION, **labels, status="201") == 1


@pytest.mark.usefixtures("metrics_enabled")
@pytest.mark.parametrize(
    "reported_status,error,status",
    [
        (None, httpx.ReadTimeout("too slow"), "timeout"),
        (None, httpx.ConnectTimeout("too slow"), "timeout"),
        (None, httpx.ConnectError("refused"), "error"),
        (None, ValueError("anything else"), "error"),
        # raise_for_status after the status was reported
        (503, ValueError("raise_for_status"), "503"),
    ],
)
def test_instrumentation_outgoing_request_failures(reported_status, error, status):
    """A call given up on is told apart from one that failed, and both are re-raised."""
    labels = {"service": f"test-{status}", "operation": "op"}
    before = sample(OUTGOING_DURATION, **labels, status=status)

    with pytest.raises(type(error)):
        with instrumentation.outgoing_request(f"test-{status}", "op") as observed:
            observed.status = reported_status
            raise error

    assert sample(OUTGOING_DURATION, **labels, status=status) == before + 1
    assert sample(OUTGOING_INFLIGHT, **labels) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_outgoing_request_cancelled():
    """A call whose task is cancelled is counted as such and leaves the in-flight gauge."""
    labels = {"service": "test-cancel", "operation": "op"}

    async def call():
        with instrumentation.outgoing_request("test-cancel", "op"):
            await asyncio.sleep(10)

    task = asyncio.create_task(call())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sample(OUTGOING_DURATION, **labels, status="cancelled") == 1
    assert sample(OUTGOING_INFLIGHT, **labels) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
@respx.mock
@pytest.mark.parametrize("status_code", [200, 500])
async def test_instrumentation_albert_search_is_measured(status_code):
    """The Albert search is measured under its operation, whatever it answers."""
    respx.post(ALBERT_SEARCH_URL).mock(
        return_value=httpx.Response(
            status_code, json={"data": [], "usage": {"prompt_tokens": 1, "completion_tokens": 0}}
        )
    )
    labels = {"service": "albert", "operation": "search", "status": str(status_code)}
    before = sample(OUTGOING_DURATION, **labels)

    try:
        await AlbertRagBackend(collection_id="123").asearch("a query")
    except httpx.HTTPStatusError:
        assert status_code == 500

    assert sample(OUTGOING_DURATION, **labels) == before + 1


@pytest.mark.asyncio
@respx.mock
async def test_instrumentation_brave_is_measured_by_endpoint(metrics_enabled):
    """A Brave search is measured under the endpoint it called, never its url or query."""
    metrics_enabled.BRAVE_API_KEY = "a-key"
    respx.get(BRAVE_URL).mock(return_value=httpx.Response(200, json={"web": {"results": []}}))
    labels = {"service": "brave", "operation": "web_search", "status": "200"}
    before = sample(OUTGOING_DURATION, **labels)

    await _query_brave_api_with_endpoint_async(BRAVE_URL, "web_search", {"q": "a query"})

    assert sample(OUTGOING_DURATION, **labels) == before + 1


@pytest.mark.asyncio
@respx.mock
async def test_instrumentation_staan_is_measured(metrics_enabled):
    """A Staan search is measured."""
    metrics_enabled.STAAN_API_KEY = "a-key"
    respx.get(STAAN_SEARCH_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    labels = {"service": "staan", "operation": "search", "status": "200"}
    before = sample(OUTGOING_DURATION, **labels)

    await staan_search("a query", "fr-fr")

    assert sample(OUTGOING_DURATION, **labels) == before + 1


@respx.mock
def test_instrumentation_docs_is_measured(metrics_enabled):
    """A document created in Docs is measured."""
    metrics_enabled.DOCS_BASE_URL = "https://docs.example.com/"
    respx.post("https://docs.example.com/external_api/v1.0/documents/").mock(
        return_value=httpx.Response(201, json={"id": "a-document"})
    )
    session = SessionStore()
    session["oidc_access_token"] = "a-token"
    labels = {"service": "docs", "operation": "create_document", "status": "201"}
    before = sample(OUTGOING_DURATION, **labels)

    DocsClient().create_document("A title", "Some content", session)

    assert sample(OUTGOING_DURATION, **labels) == before + 1


@pytest.mark.asyncio
@respx.mock
async def test_instrumentation_docs_fetch_is_measured(metrics_enabled):
    """A document read from Docs is measured, under the status Docs answered with."""
    metrics_enabled.DOCS_BASE_URL = "https://docs.example.com/"
    document_id = "0b8f1e9a-3c5d-4e2f-9a1b-7c6d5e4f3a21"
    respx.get(
        f"https://docs.example.com/external_api/v1.0/documents/{document_id}/formatted-content/"
    ).mock(return_value=httpx.Response(403))
    labels = {"service": "docs", "operation": "fetch_document", "status": "403"}
    before = sample(OUTGOING_DURATION, **labels)

    with pytest.raises(DocsFetchError):
        await DocsClient().fetch_document_markdown(document_id, {"oidc_access_token": "a-token"})

    assert sample(OUTGOING_DURATION, **labels) == before + 1


# -- model requests ----------------------------------------------------------------


async def _streamed_answer(_messages, _info):
    """A model streaming its answer."""
    for word in ["Hello", " there"]:
        yield word


def _answer(_messages, _info):
    """A model answering at once."""
    return ModelResponse(
        parts=[TextPart("Hello")], usage=RequestUsage(input_tokens=12, output_tokens=3)
    )


def test_instrumentation_llm_hooks_disabled(settings):
    """With the metrics off the agents get no capability at all."""
    settings.PROMETHEUS_METRICS_ENABLED = False

    assert instrumentation.llm_metrics_hooks(model_configuration("m"), "AnAgent") is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_llm_streamed_request():
    """A streamed request is measured until its last part, with the tokens it used."""
    hooks = instrumentation.llm_metrics_hooks(model_configuration("llm-stream"), "AnAgent")
    agent = Agent(FunctionModel(stream_function=_streamed_answer), capabilities=[hooks])
    labels = {"model": "llm-stream", "provider": "test-provider", "agent": "AnAgent"}

    async with agent.iter("Hi") as run:
        async for node in run:
            if Agent.is_model_request_node(node):
                async with node.stream(run.ctx) as stream:
                    async for _event in stream:
                        assert sample(LLM_INFLIGHT, model="llm-stream", provider="test-provider")

    assert sample(LLM_DURATION, **labels, status="ok") == 1
    assert sample(LLM_INFLIGHT, model="llm-stream", provider="test-provider") == 0
    assert sample(LLM_TOKENS, **labels, kind="input") == run.usage.input_tokens
    assert sample(LLM_TOKENS, **labels, kind="output") == run.usage.output_tokens


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_llm_request():
    """A request answered at once is measured with the tokens it used."""
    hooks = instrumentation.llm_metrics_hooks(model_configuration("llm-run"), "AnAgent")
    agent = Agent(FunctionModel(_answer), capabilities=[hooks])
    labels = {"model": "llm-run", "provider": "test-provider", "agent": "AnAgent"}

    await agent.run("Hi")

    assert sample(LLM_DURATION, **labels, status="ok") == 1
    assert sample(LLM_TOKENS, **labels, kind="input") == 12
    assert sample(LLM_TOKENS, **labels, kind="output") == 3


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
@pytest.mark.parametrize(
    "error,status",
    [
        (ModelHTTPError(429, "a-model"), "429"),
        (ModelHTTPError(503, "a-model"), "503"),
        (ModelAPIError("a-model", "connection refused"), "connection_error"),
        (ValueError("anything else"), "error"),
    ],
)
async def test_instrumentation_llm_request_failures(error, status):
    """A failed request is counted under what went wrong, and is re-raised."""
    hrid = f"llm-fail-{status}"
    hooks = instrumentation.llm_metrics_hooks(model_configuration(hrid), "AnAgent")

    def _fail(_messages, _info):
        raise error

    agent = Agent(FunctionModel(_fail), capabilities=[hooks])

    with pytest.raises(type(error)):
        await agent.run("Hi")

    labels = {"model": hrid, "provider": "test-provider", "agent": "AnAgent"}
    assert sample(LLM_DURATION, **labels, status=status) == 1
    assert sample(LLM_INFLIGHT, model=hrid, provider="test-provider") == 0


async def _consume_streamed_run(agent, configuration, on_event=None):
    """Run an agent the way the chat streams its answer."""
    async with agent.iter("Hi") as run:
        async for node in run:
            if Agent.is_model_request_node(node):
                observe = instrumentation.streamed_model_request(configuration)
                async with node.stream(run.ctx) as stream:
                    async for event in observe(stream):
                        if on_event:
                            on_event(event)


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
@pytest.mark.parametrize(
    "error,status",
    [
        (ModelHTTPError(503, "a-model"), "503"),
        (ModelAPIError("a-model", "connection dropped"), "connection_error"),
    ],
)
async def test_instrumentation_llm_streamed_request_failures(error, status):
    """A streamed request failing midway is counted under what went wrong, not as cancelled."""
    hrid = f"llm-stream-fail-{status}"
    configuration = model_configuration(hrid)
    hooks = instrumentation.llm_metrics_hooks(configuration, "AnAgent")

    async def _fail_midway(_messages, _info):
        yield "Hello"
        raise error

    agent = Agent(FunctionModel(stream_function=_fail_midway), capabilities=[hooks])

    with pytest.raises(type(error)):
        await _consume_streamed_run(agent, configuration)

    labels = {"model": hrid, "provider": "test-provider", "agent": "AnAgent"}
    assert sample(LLM_DURATION, **labels, status=status) == 1
    assert sample(LLM_DURATION, **labels, status="cancelled") == 0
    assert sample(LLM_INFLIGHT, model=hrid, provider="test-provider") == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_llm_streamed_request_stopped():
    """A streamed request its reader stopped, as the stop button does, is counted as cancelled."""
    configuration = model_configuration("llm-stream-stopped")
    hooks = instrumentation.llm_metrics_hooks(configuration, "AnAgent")
    agent = Agent(FunctionModel(stream_function=_streamed_answer), capabilities=[hooks])

    def _stop(_event):
        raise StreamCancelException()

    with pytest.raises(StreamCancelException):
        await _consume_streamed_run(agent, configuration, on_event=_stop)

    labels = {"model": "llm-stream-stopped", "provider": "test-provider", "agent": "AnAgent"}
    assert sample(LLM_DURATION, **labels, status="cancelled") == 1


@pytest.mark.usefixtures("metrics_enabled")
def test_instrumentation_llm_provider_of_a_builtin_model():
    """A model without a provider is labelled with the provider prefix of its name."""
    configuration = SimpleNamespace(hrid="m", provider=None, model_name="mistral:small")

    instrumentation.observe_time_to_first_token(configuration, 0.2)

    assert (
        sample(
            "conversations_llm_time_to_first_token_seconds_count",
            model="m",
            provider="mistral",
        )
        == 1
    )


async def _parts(*parts):
    """A model stream sending these parts."""
    for part in parts:
        yield part


def test_instrumentation_time_to_first_token_disabled(settings):
    """With the metrics off the stream is handed back as it is."""
    settings.PROMETHEUS_METRICS_ENABLED = False
    events = _parts("first")

    observe = instrumentation.streamed_model_request(model_configuration("m"))

    assert observe(events) is events


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_time_to_first_token():
    """Every part goes through, and only the first one is timed."""
    observe = instrumentation.streamed_model_request(model_configuration("ttft"))

    received = [event async for event in observe(_parts("first", "second", "third"))]

    assert received == ["first", "second", "third"]
    labels = {"model": "ttft", "provider": "test-provider"}
    assert sample("conversations_llm_time_to_first_token_seconds_count", **labels) == 1
    assert 0 <= sample("conversations_llm_time_to_first_token_seconds_sum", **labels) < 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_every_agent_is_measured(settings):
    """The agents built on BaseAgent are measured under their class name and model hrid."""
    agent = TitleGenerationAgent()
    labels = {
        "model": settings.LLM_DEFAULT_MODEL_HRID,
        "agent": "TitleGenerationAgent",
        "status": "ok",
    }
    before = total(LLM_DURATION, **labels)

    with agent.override(model=FunctionModel(_answer)):
        await agent.run("Hi")

    assert total(LLM_DURATION, **labels) == before + 1


# -- chat streams ------------------------------------------------------------------


@pytest.mark.usefixtures("metrics_enabled")
@pytest.mark.parametrize(
    "reported_outcome,outcome",
    [(None, "ok"), ("model_rate_limited", "model_rate_limited")],
)
def test_instrumentation_chat_stream(reported_outcome, outcome):
    """A stream is active while it runs, then counted under how it ended."""
    model = f"stream-{outcome}"

    with instrumentation.chat_stream(model) as observed:
        assert sample(STREAMS_ACTIVE, model=model) == 1
        observed.outcome = reported_outcome

    assert sample(STREAMS_ACTIVE, model=model) == 0
    assert sample(STREAM_DURATION, model=model, outcome=outcome) == 1


@pytest.mark.usefixtures("metrics_enabled")
def test_instrumentation_chat_stream_failure():
    """A stream that raised is counted as an error."""
    model = "stream-raise-error"

    with pytest.raises(ValueError):
        with instrumentation.chat_stream(model):
            raise ValueError("anything else")

    assert sample(STREAMS_ACTIVE, model=model) == 0
    assert sample(STREAM_DURATION, model=model, outcome="error") == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("metrics_enabled")
async def test_instrumentation_chat_stream_interrupted():
    """A stream closed or cancelled from outside, as a shutdown does, is counted as interrupted."""

    async def stream():
        with instrumentation.chat_stream("stream-closed"):
            yield "first frame"
            yield "second frame"

    frames = stream()
    await anext(frames)
    await frames.aclose()

    async def cancelled_stream():
        with instrumentation.chat_stream("stream-cancelled"):
            await asyncio.sleep(10)

    task = asyncio.create_task(cancelled_stream())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    for model in ["stream-closed", "stream-cancelled"]:
        assert sample(STREAMS_ACTIVE, model=model) == 0
        assert sample(STREAM_DURATION, model=model, outcome="interrupted") == 1


# -- workers and Celery ------------------------------------------------------------


def test_instrumentation_forget_dead_processes(monkeypatch, tmp_path):
    """The gauges of the workers that are gone are dropped, what they counted is kept."""
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    with subprocess.Popen([sys.executable, "-c", "pass"]) as process:
        process.wait()
    dead, alive = process.pid, os.getpid()
    for name in [
        f"gauge_livesum_{dead}.db",
        f"gauge_liveall_{dead}.db",
        f"gauge_livesum_{alive}.db",
        f"counter_{dead}.db",
        f"histogram_{dead}.db",
        "unrelated.txt",
    ]:
        (tmp_path / name).touch()

    metrics.forget_dead_processes()

    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        [
            f"gauge_livesum_{alive}.db",
            f"counter_{dead}.db",
            f"histogram_{dead}.db",
            "unrelated.txt",
        ]
    )


def test_instrumentation_forget_dead_processes_without_directory(monkeypatch, tmp_path):
    """Nothing to do, and nothing to fail on, without a shared directory."""
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    metrics.forget_dead_processes()
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path / "missing"))
    metrics.forget_dead_processes()


def fake_broker(lengths, driver_type="redis"):
    """A kombu connection to a broker holding these redis lists."""
    channel = mock.Mock(sep="\x06\x16", priority_steps=[0, 3, 6, 9])
    channel.client.llen.side_effect = lambda key: lengths.get(key, 0)
    connection = mock.MagicMock()
    connection.__enter__.return_value = connection
    connection.transport.driver_type = driver_type
    connection.default_channel = channel
    return connection


def collected(collector):
    """What a collector exposes, in the text format."""
    registry = CollectorRegistry()
    registry.register(collector)
    return generate_latest(registry).decode()


def test_instrumentation_celery_queue_length():
    """The tasks waiting on every priority of the default queue are added up."""
    broker = fake_broker({"celery": 4, "celery\x06\x163": 2, "other": 50})

    with mock.patch.object(metrics.celery_app, "connection_for_read", return_value=broker):
        output = collected(metrics.CeleryQueueCollector())

    assert 'conversations_celery_queue_length{queue="celery"} 6.0' in output
    broker.ensure_connection.assert_called_once_with(max_retries=1, timeout=2)


@pytest.mark.parametrize(
    "broker",
    [
        fake_broker({}, driver_type="memory"),
        mock.MagicMock(__enter__=mock.Mock(side_effect=OSError("broker is down"))),
    ],
    ids=["not-redis", "unreachable"],
)
def test_instrumentation_celery_queue_length_unknown(broker):
    """A broker that cannot be asked yields no sample rather than failing the scrape."""
    with mock.patch.object(metrics.celery_app, "connection_for_read", return_value=broker):
        assert "conversations_celery_queue_length" not in collected(metrics.CeleryQueueCollector())
