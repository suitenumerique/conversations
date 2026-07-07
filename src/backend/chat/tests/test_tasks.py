"""Tests for the conversation summarization Celery task."""

from unittest.mock import patch

from django.utils import timezone

import pytest

from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.tasks import summarize_conversation_history

pytestmark = pytest.mark.django_db()


@pytest.fixture(autouse=True)
def _llm_config(settings):
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            max_token_context=4000,
            provider=LLMProvider(hrid="p", base_url="https://example.com", api_key="k"),
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS = 1000
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.5


def _long_history(turns: int = 30) -> list:
    """Raw pydantic message dicts long enough to exceed any small budget."""
    messages = []
    for i in range(turns):
        messages.append(
            {
                "kind": "request",
                "parts": [{"part_kind": "user-prompt", "content": f"user {i} " + "x " * 200}],
            }
        )
        messages.append(
            {
                "kind": "response",
                "parts": [{"part_kind": "text", "content": f"assistant {i} " + "y " * 200}],
            }
        )
    return messages


def test_task_generates_summary_and_advances_checkpoint():
    """Happy path: summary is generated and persisted, claim released."""
    conversation = ChatConversationFactory(messages=[], pydantic_messages=_long_history())

    with patch(
        "chat.tasks.generate_history_summary", return_value=("task summary", 60)
    ) as summarize:
        summarize_conversation_history(str(conversation.pk))

    summarize.assert_called_once()
    conversation.refresh_from_db()
    assert conversation.history_summary == "task summary"
    assert conversation.history_summary_checkpoint == 60
    assert conversation.history_summary_claimed_at is None  # released


def test_task_exits_when_claim_is_held():
    """Task is a no-op when another worker holds an active claim."""
    conversation = ChatConversationFactory(
        pydantic_messages=_long_history(),
        history_summary_claimed_at=timezone.now(),
    )
    with patch("chat.tasks.generate_history_summary") as summarize:
        summarize_conversation_history(str(conversation.pk))
    summarize.assert_not_called()


def test_task_noop_when_under_budget():
    """Task is a no-op when history fits within the token budget."""
    conversation = ChatConversationFactory(pydantic_messages=_long_history(turns=1))
    with patch("chat.tasks.generate_history_summary") as summarize:
        summarize_conversation_history(str(conversation.pk))
    summarize.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.history_summary_claimed_at is None  # released


def test_task_releases_claim_and_raises_on_failure():
    """Failure propagates (so celery autoretry fires) but the claim is released."""
    conversation = ChatConversationFactory(pydantic_messages=_long_history())

    with (
        patch(
            "chat.tasks.generate_history_summary",
            side_effect=RuntimeError("provider down"),
        ),
        pytest.raises(RuntimeError),
    ):
        summarize_conversation_history(str(conversation.pk))

    conversation.refresh_from_db()
    assert conversation.history_summary_claimed_at is None


def test_task_ignores_deleted_conversation():
    """Task exits silently for a non-existent conversation PK."""
    summarize_conversation_history("00000000-0000-0000-0000-000000000000")
