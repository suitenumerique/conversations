"""Tests for chat Celery tasks.

Celery runs eagerly in the test settings (`CELERY_TASK_ALWAYS_EAGER`), so
`.delay()` executes the task synchronously in-process.
"""

from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

import pytest
import responses
from pydantic_ai.exceptions import ModelHTTPError
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat import factories
from chat.agents.history_processors import SummarizationRequiredError
from chat.enums import AttachmentIndexState
from chat.factories import ChatConversationFactory
from chat.llm_configuration import LLModel, LLMProvider
from chat.tasks import (
    RETRYABLE_SUMMARIZATION_ERRORS,
    index_project_attachment_task,
    summarize_conversation_history,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure Albert backend + parser for the task tests."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )
    settings.RAG_DOCUMENT_PARSER = "chat.agent_rag.document_converter.parser.AlbertParser"
    settings.ALBERT_API_URL = "https://albert.api.etalab.gouv.fr"
    settings.ALBERT_API_KEY = "albert-api-key"
    return settings


@responses.activate
def test_index_project_attachment_task_indexes_attachment():
    """The task resolves the id and indexes the file into the project collection."""
    saved_name = default_storage.save("task-rag-test.txt", ContentFile(b"Hello task content"))
    attachment = factories.ChatProjectAttachmentFactory(
        key=saved_name,
        file_name="hello.txt",
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
    )
    try:
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/collections",
            json={"id": "42"},
            status=status.HTTP_200_OK,
        )
        responses.post(
            "https://albert.api.etalab.gouv.fr/v1/documents",
            json={"id": 1},
            status=status.HTTP_201_CREATED,
        )

        index_project_attachment_task.delay(attachment.pk)

        attachment.refresh_from_db()
        assert attachment.rag_document_id == "1"
        assert attachment.index_state == AttachmentIndexState.INDEXED
    finally:
        default_storage.delete(saved_name)


def test_index_project_attachment_task_ignores_missing_attachment():
    """A deleted attachment id is logged and skipped, never raised."""
    index_project_attachment_task.delay(999999)


@pytest.fixture(name="_llm_config", autouse=True)
def llm_config_fixture(settings):
    """Configure a single active model for the summarization task tests."""
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
    """A non-retryable failure propagates and the claim is still released."""
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


def test_retryable_errors_exclude_deterministic_failures():
    """Only transient provider errors are retried; deterministic ones fail fast."""
    assert issubclass(ModelHTTPError, RETRYABLE_SUMMARIZATION_ERRORS)
    assert not issubclass(SummarizationRequiredError, RETRYABLE_SUMMARIZATION_ERRORS)
    assert not issubclass(RuntimeError, RETRYABLE_SUMMARIZATION_ERRORS)


def test_task_ignores_deleted_conversation():
    """Task exits silently for a non-existent conversation PK."""
    summarize_conversation_history("00000000-0000-0000-0000-000000000000")
