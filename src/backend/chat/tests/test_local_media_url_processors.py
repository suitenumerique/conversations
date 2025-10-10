"""Tests for local_media_url_processors."""

from unittest.mock import patch

import pytest
from pydantic_ai import (
    DocumentUrl,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from chat.agents.local_media_url_processors import (
    update_history_local_urls,
    update_local_urls,
)
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls(mock_generate_retrieve_policy):
    """Test that update_local_urls replaces local URLs with presigned URLs."""
    conversation = ChatConversationFactory()
    mock_generate_retrieve_policy.side_effect = lambda _key: f"presigned_url-{_key}"

    key = f"{conversation.pk}/test.jpg"
    contents = [
        ImageUrl(url=f"/media-key/{key}"),
        DocumentUrl(url=f"/media-key/{conversation.pk}/test.pdf"),
        ImageUrl(url="https://example.com/image.jpg"),
    ]
    updated_urls = {}

    result = list(update_local_urls(conversation, contents, updated_urls))

    assert len(result) == 3
    assert result[0].url == f"presigned_url-{key}"
    assert result[1].url == f"presigned_url-{conversation.pk}/test.pdf"
    assert result[2].url == "https://example.com/image.jpg"

    assert mock_generate_retrieve_policy.call_count == 2
    mock_generate_retrieve_policy.assert_any_call(key)
    mock_generate_retrieve_policy.assert_any_call(f"{conversation.pk}/test.pdf")

    assert len(updated_urls) == 2
    assert updated_urls[f"presigned_url-{key}"] == f"/media-key/{key}"
    assert (
        updated_urls[f"presigned_url-{conversation.pk}/test.pdf"]
        == f"/media-key/{conversation.pk}/test.pdf"
    )


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_security_check(mock_generate_retrieve_policy):
    """Test that update_local_urls performs a security check."""
    conversation = ChatConversationFactory()
    contents = [ImageUrl(url="/media-key/other_conversation/test.jpg")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    assert result[0].url == "/media-key/other_conversation/test.jpg"
    mock_generate_retrieve_policy.assert_not_called()


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_no_media(mock_generate_retrieve_policy):
    """Test that update_local_urls handles no media URLs."""
    conversation = ChatConversationFactory()
    contents = []
    result = list(update_local_urls(conversation, contents))
    assert len(result) == 0
    mock_generate_retrieve_policy.assert_not_called()


@patch("chat.agents.local_media_url_processors.update_local_urls")
def test_update_history_local_urls(mock_update_local_urls):
    """Test that update_history_local_urls processes messages."""
    conversation = ChatConversationFactory()
    mock_update_local_urls.return_value = iter([])
    key = f"{conversation.pk}/test.jpg"
    user_prompt_content = [
        ImageUrl(url=f"/media-key/{key}"),
        DocumentUrl(url=f"/media-key/{conversation.pk}/test.pdf"),
    ]
    messages = [
        ModelRequest(parts=[UserPromptPart(content=user_prompt_content)]),
        ModelResponse(parts=[TextPart(content="I see your images.")]),
    ]

    result = update_history_local_urls(conversation, messages)

    assert len(result) == 2
    mock_update_local_urls.assert_called_once_with(conversation, user_prompt_content)


def test_update_history_local_urls_no_requests():
    """Test that update_history_local_urls handles no ModelRequest messages."""
    conversation = ChatConversationFactory()
    messages = [
        ModelRequest(parts=["Hello"]),
        ModelResponse(parts=[TextPart(content="Hi there!")]),
    ]

    with patch("chat.agents.local_media_url_processors.update_local_urls") as mock:
        result = update_history_local_urls(conversation, messages)
        assert result == messages
        mock.assert_not_called()


def test_update_history_local_urls_no_user_prompt_parts():
    """Test that update_history_local_urls handles no UserPromptPart."""
    conversation = ChatConversationFactory()
    messages = [ModelRequest(parts=[])]

    with patch("chat.agents.local_media_url_processors.update_local_urls") as mock:
        result = update_history_local_urls(conversation, messages)
        assert result == messages
        mock.assert_not_called()
