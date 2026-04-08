"""Tests for document context rolling window instructions."""

import pytest
from asgiref.sync import async_to_sync

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db()


@pytest.fixture()
def _llm_config_with_context(settings):
    """Configure a model with max_token_context for context window tests."""
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.5
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="amazing-llm",
            human_readable_name="Amazing LLM",
            is_active=True,
            icon=None,
            system_prompt="You are an amazing assistant.",
            tools=[],
            # Keep context large enough so tests can exercise rolling-window behavior
            # despite the fixed security buffer applied by the service.
            max_token_context=4000,
            provider=LLMProvider(
                hrid="unused",
                base_url="https://example.com",
                api_key="key",
            ),
        ),
    }


def test_document_context_marks_oversized_docs_as_rag_only(_llm_config_with_context, monkeypatch):
    """Oversized documents must stay accessible only through rag/summarize tools."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="big.md",
        content_type="text/markdown",
    )

    async def fake_read_attachment_content(_attachment):
        return "big.md", "a" * 999

    monkeypatch.setattr(
        "chat.clients.pydantic_ai.read_attachment_content",
        fake_read_attachment_content,
    )
    monkeypatch.setattr(
        "chat.clients.pydantic_ai.count_approx_tokens",
        lambda _text: 1201,
    )

    instruction = async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access
    assert '"title": "big"' in instruction
    assert '"access": "tool_call_only"' in instruction
    assert '"content": "available via tools"' in instruction
    assert "List of documents attached to this conversation" in instruction


def test_document_context_uses_fifo_rolling_window(_llm_config_with_context, monkeypatch):
    """When budget overflows, oldest inlined documents must be evicted first."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-1.md",
        content_type="text/markdown",
    )
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-2.md",
        content_type="text/markdown",
    )
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-3.md",
        content_type="text/markdown",
    )

    content_by_name = {
        "doc-1.md": "a" * 6,  # 2 tokens (ceil(6/3))
        "doc-2.md": "b" * 6,  # 2 tokens (ceil(6/3))
        "doc-3.md": "c" * 9,  # 3 tokens (ceil(9/3))
    }

    async def fake_read_attachment_content(attachment):
        return attachment.file_name, content_by_name[attachment.file_name]

    monkeypatch.setattr(
        "chat.clients.pydantic_ai.read_attachment_content",
        fake_read_attachment_content,
    )

    monkeypatch.setattr(
        "chat.clients.pydantic_ai.count_approx_tokens",
        lambda _text: 400,
    )

    instruction = async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access

    # max_token_context=4000, ratio=0.5 => budget=1000 after buffer.
    # With 3 docs at 400 tokens each, rolling outcome should inline doc-2 + doc-3.
    assert '"title": "doc-1"' in instruction
    assert '"title": "doc-2"' in instruction
    assert '"title": "doc-3"' in instruction
    assert '"access": "tool_call_only"' in instruction
    assert instruction.count('"access": "full-context"') == 2
    assert '"content": "available via tools"' in instruction


def test_document_context_uses_configurable_ratio(_llm_config_with_context, monkeypatch, settings):
    """Budget ratio comes from Django settings and changes inlining behavior."""
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.3  # max_token_context=10 => budget=3

    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-1.md",
        content_type="text/markdown",
    )
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-2.md",
        content_type="text/markdown",
    )

    content_by_name = {
        "doc-1.md": "a" * 6,  # 2 tokens (ceil(6/3))
        "doc-2.md": "b" * 6,  # 2 tokens (ceil(6/3))
    }

    async def fake_read_attachment_content(attachment):
        return attachment.file_name, content_by_name[attachment.file_name]

    monkeypatch.setattr(
        "chat.clients.pydantic_ai.read_attachment_content",
        fake_read_attachment_content,
    )
    monkeypatch.setattr(
        "chat.clients.pydantic_ai.count_approx_tokens",
        lambda _text: 150,
    )

    instruction = async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access
    assert '"title": "doc-1"' in instruction
    assert '"title": "doc-2"' in instruction
    assert '"access": "tool_call_only"' in instruction
    assert '"access": "full-context"' in instruction
