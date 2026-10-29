"""Test that a chat turn served by the endpoint is measured end to end."""

import pytest
from freezegun import freeze_time
from prometheus_client import REGISTRY

from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)


def total(name, **labels):
    """The sum of the samples of the default registry that carry these labels."""
    return sum(
        found.value
        for family in REGISTRY.collect()
        for found in family.samples
        if found.name == name and labels.items() <= found.labels.items()
    )


@freeze_time("2025-07-25T10:36:35.297675Z")
def test_post_conversation_is_measured(
    settings, api_client, mock_openai_stream, hello_conversation_data
):
    """
    The stream, the model request it made and the time to its first part are measured,
    and nothing is left in flight.
    """
    settings.PROMETHEUS_METRICS_ENABLED = True
    chat_conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_login(chat_conversation.owner)

    def measured():
        return [
            total("conversations_chat_stream_duration_seconds_count", outcome="ok"),
            total(
                "conversations_llm_request_duration_seconds_count",
                agent="ConversationAgent",
                status="ok",
            ),
            total("conversations_llm_time_to_first_token_seconds_count"),
        ]

    before = measured()

    response = api_client.post(
        f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
        hello_conversation_data,
        format="json",
    )
    b"".join(response.streaming_content)

    assert mock_openai_stream.called
    # one stream, one model request, one first token
    assert [after - start for after, start in zip(measured(), before, strict=True)] == [1, 1, 1]
    assert total("conversations_chat_streams_active") == 0
    assert total("conversations_llm_requests_inflight") == 0
