"""Tests for the Prometheus measurement of the chat streams of AIAgentService."""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from prometheus_client import REGISTRY
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from chat.clients.exceptions import StreamCancelException
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db()

STREAM_DURATION = "conversations_chat_stream_duration_seconds_count"


class AsyncRaiseIterator:
    """Async iterator that raises the given exception on the first iteration."""

    def __init__(self, exc):
        self.exc = exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self.exc


def sample(name, **labels):
    """The value of a sample of the default registry, 0 when it does not exist."""
    return REGISTRY.get_sample_value(name, labels) or 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,outcome",
    [
        (ModelHTTPError(status_code=429, model_name="test-model"), "model_rate_limited"),
        (ModelHTTPError(status_code=500, model_name="test-model"), "model_unavailable"),
        (ModelAPIError("test-model", "connection refused"), "model_connection_error"),
    ],
)
async def test_stream_metrics_error_reported_to_the_user(settings, error, outcome):
    """A stream that ends on an error frame is counted under the error code it sent."""
    settings.PROMETHEUS_METRICS_ENABLED = True
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    before = sample(STREAM_DURATION, model=service.model_hrid, outcome=outcome)

    with patch.object(service, "_run_agent", side_effect=lambda *a, **k: AsyncRaiseIterator(error)):
        async for _frame in service.stream_data_async([]):
            pass

    assert sample(STREAM_DURATION, model=service.model_hrid, outcome=outcome) == before + 1


@pytest.mark.asyncio
async def test_stream_metrics_stopped_by_the_user(settings):
    """
    A stream the user stopped ends like a normal one, keeping what was produced, and
    is counted as cancelled.
    """
    settings.PROMETHEUS_METRICS_ENABLED = True
    conversation = await sync_to_async(ChatConversationFactory)()
    service = AIAgentService(conversation, user=conversation.owner)
    before = sample(STREAM_DURATION, model=service.model_hrid, outcome="cancelled")

    with patch.object(
        service,
        "_run_agent",
        side_effect=lambda *a, **k: AsyncRaiseIterator(StreamCancelException()),
    ):
        frames = [frame async for frame in service.stream_data_async([])]

    assert frames[-1] == "data: [DONE]\n\n"
    assert sample(STREAM_DURATION, model=service.model_hrid, outcome="cancelled") == before + 1
