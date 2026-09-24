"""The liveness marker that tells a live turn from an interrupted one.

A client that navigated away comes back to a checkpoint it cannot interpret on
its own: the same row means "this is all you will get" or "the rest is coming",
depending only on whether the turn is still running.
"""

# pylint: disable=protected-access
import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationFactory
from chat.streaming_status import is_stream_alive

pytestmark = pytest.mark.django_db(transaction=True)

QUESTION = UIMessage(
    id="q-1",
    role="user",
    content="Say hello",
    parts=[TextUIPart(type="text", text="Say hello")],
)


async def _hello_model(_messages: list[ModelMessage], _info: AgentInfo):
    """Stream an answer in two parts, so a reader can stop after the first."""
    yield "Hello"
    yield " there"


def _service_with_model(conversation, stream_function):
    """Build the service against a scripted model, as the view fixture does."""
    service = AIAgentService(conversation, user=conversation.owner)
    service.conversation_agent._model = FunctionModel(stream_function=stream_function)
    return service


@pytest.mark.asyncio
async def test_the_marker_is_live_while_the_turn_runs_and_gone_once_it_ends(clear_cache):  # pylint: disable=unused-argument
    """Set for the length of the turn, dropped as soon as it has nothing left."""
    conversation = await sync_to_async(ChatConversationFactory)()
    seen = []

    async def model_reading_the_marker(_messages, _info):
        """Read the marker back from the cache mid-run."""
        seen.append(await sync_to_async(is_stream_alive)(conversation.pk))
        yield "Hello"

    service = _service_with_model(conversation, model_reading_the_marker)
    async for _ in service.stream_data_async([QUESTION]):
        pass

    assert seen == [True]
    assert await sync_to_async(is_stream_alive)(conversation.pk) is False


@pytest.mark.asyncio
async def test_an_interrupted_turn_leaves_the_marker_to_expire(clear_cache):  # pylint: disable=unused-argument
    """Nothing clears it when the reader walks away; the TTL does, later.

    This is what keeps the checkpoint readable as "still coming" rather than
    "interrupted" for a turn whose reader left but whose run carries on.
    """
    conversation = await sync_to_async(ChatConversationFactory)()
    service = _service_with_model(conversation, _hello_model)

    stream = service.stream_data_async([QUESTION])
    async for chunk in stream:
        if '"delta":"Hello"' in chunk:
            break

    assert await sync_to_async(is_stream_alive)(conversation.pk) is True
