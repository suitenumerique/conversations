"""Tests for document context rolling window instructions."""

import json
from unittest import mock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
from asgiref.sync import async_to_sync

from chat.clients.pydantic_ai import AIAgentService
from chat.constants import ACCESS_FULL_CONTEXT, ACCESS_TOOL_CALL_ONLY
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory, UserFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db()

LISTING_PREFIX = "List of documents attached to this conversation:\n"
TOOL_CALL_ONLY_CONTENT = "available via tools"


def _parse_listing(instruction: str) -> dict:
    """Extract and parse the JSON listing from the instruction string."""
    assert LISTING_PREFIX in instruction, f"missing prefix in: {instruction!r}"
    return json.loads(instruction.split(LISTING_PREFIX, 1)[1])


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
        conversion_from="markdown",
    )

    async def fake_read_attachment_content(_attachment):  # NOSONAR
        return "big.md", "a" * 999

    monkeypatch.setattr(
        "chat.document_context_builder.read_attachment_content",
        fake_read_attachment_content,
    )
    monkeypatch.setattr(
        "chat.document_context_builder.count_approx_tokens",
        lambda _text: 1201,
    )

    instruction = async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access
    listing = _parse_listing(instruction)
    assert len(listing["documents"]) == 1
    doc = listing["documents"][0]
    assert doc["title"] == "big"
    assert doc["access"] == ACCESS_TOOL_CALL_ONLY
    assert doc["content"] == TOOL_CALL_ONLY_CONTENT


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
        conversion_from="markdown",
    )
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-2.md",
        content_type="text/markdown",
        conversion_from="markdown",
    )
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-3.md",
        content_type="text/markdown",
        conversion_from="markdown",
    )

    content_by_name = {
        "doc-1.md": "a" * 6,  # 2 tokens (ceil(6/3))
        "doc-2.md": "b" * 6,  # 2 tokens (ceil(6/3))
        "doc-3.md": "c" * 9,  # 3 tokens (ceil(9/3))
    }

    async def fake_read_attachment_content(attachment):  # NOSONAR
        return attachment.file_name, content_by_name[attachment.file_name]

    monkeypatch.setattr(
        "chat.document_context_builder.read_attachment_content",
        fake_read_attachment_content,
    )

    monkeypatch.setattr(
        "chat.document_context_builder.count_approx_tokens",
        lambda _text: 400,
    )

    instruction = async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access
    listing = _parse_listing(instruction)

    # max_token_context=4000, ratio=0.5 => budget=1000 after buffer.
    # With 3 docs at 400 tokens each, rolling outcome should inline doc-2 + doc-3.
    assert listing["documents_order"] == "newest_to_oldest"
    by_title = {d["title"]: d for d in listing["documents"]}
    assert set(by_title) == {"doc-1", "doc-2", "doc-3"}
    assert by_title["doc-1"]["access"] == ACCESS_TOOL_CALL_ONLY
    assert by_title["doc-1"]["content"] == TOOL_CALL_ONLY_CONTENT
    assert by_title["doc-2"]["access"] == ACCESS_FULL_CONTEXT
    assert by_title["doc-3"]["access"] == ACCESS_FULL_CONTEXT


def test_document_context_uses_configurable_ratio(_llm_config_with_context, monkeypatch, settings):
    """Budget ratio comes from Django settings and changes inlining behavior."""
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.3  # max_token_context=4000 => budget=200

    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    service = AIAgentService(conversation, user=user)

    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-1.md",
        content_type="text/markdown",
        conversion_from="markdown",
    )
    ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name="doc-2.md",
        content_type="text/markdown",
        conversion_from="markdown",
    )

    content_by_name = {
        "doc-1.md": "a" * 6,  # 2 tokens (ceil(6/3))
        "doc-2.md": "b" * 6,  # 2 tokens (ceil(6/3))
    }

    async def fake_read_attachment_content(attachment):  # NOSONAR
        return attachment.file_name, content_by_name[attachment.file_name]

    monkeypatch.setattr(
        "chat.document_context_builder.read_attachment_content",
        fake_read_attachment_content,
    )
    monkeypatch.setattr(
        "chat.document_context_builder.count_approx_tokens",
        lambda _text: 150,
    )

    instruction = async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access
    listing = _parse_listing(instruction)

    by_title = {d["title"]: d for d in listing["documents"]}
    assert set(by_title) == {"doc-1", "doc-2"}
    # ratio=0.3, max_context=4000, buffer=1000 => budget=200; only newest fits.
    assert by_title["doc-1"]["access"] == ACCESS_TOOL_CALL_ONLY
    assert by_title["doc-2"]["access"] == ACCESS_FULL_CONTEXT


# Cache-behavior tests for AIAgentService._build_document_context_instruction.
#
# These tests use REAL components: real default_storage, real Django cache
# (LocMem in tests), real ORM. The cache-hit signal is "did we re-read from
# storage?" - spied via mock.patch.object on default_storage.open.


@pytest.fixture()
def _llm_config_two_models(settings):
    """Two LLM configs so cache-key-by-model can be exercised."""
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.5
    settings.DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS = 0
    provider = LLMProvider(hrid="p", base_url="https://example.com", api_key="key")
    settings.LLM_CONFIGURATIONS = {
        "model-a": LLModel(
            hrid="model-a",
            model_name="m-a",
            human_readable_name="Model A",
            is_active=True,
            icon=None,
            system_prompt="A",
            tools=[],
            max_token_context=4000,
            provider=provider,
        ),
        "model-b": LLModel(
            hrid="model-b",
            model_name="m-b",
            human_readable_name="Model B",
            is_active=True,
            icon=None,
            system_prompt="B",
            tools=[],
            max_token_context=8000,
            provider=provider,
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "model-a"


@pytest.fixture(autouse=True)
def _clear_cache():
    """Cache state must not leak between tests."""
    cache.clear()
    yield
    cache.clear()


def _make_text_attachment(*, conversation, user, file_name, content):
    """Create an attachment and persist content under default_storage."""
    attachment = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=user,
        file_name=file_name,
        content_type="text/markdown",
        conversion_from=None,
    )
    default_storage.save(attachment.key, ContentFile(content.encode("utf-8")))
    return attachment


def _build(service):
    return async_to_sync(service._build_document_context_instruction)()  # pylint: disable=protected-access


def _spy_storage_open():
    """Wrap default_storage.open so we can count calls without changing behavior."""
    return mock.patch.object(default_storage, "open", wraps=default_storage.open)


def test_first_call_reads_storage_once_per_attachment(_llm_config_two_models):
    """B#1: cold cache -> default_storage.open called once per text attachment."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    _make_text_attachment(conversation=conversation, user=user, file_name="a.md", content="alpha")
    _make_text_attachment(conversation=conversation, user=user, file_name="b.md", content="beta")
    service = AIAgentService(conversation, user=user)

    with _spy_storage_open() as spy:
        _build(service)

    assert spy.call_count == 2


def test_second_call_hits_cache_no_storage_reads(_llm_config_two_models):
    """B#2: identical second call returns cached instruction with zero storage opens."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    _make_text_attachment(conversation=conversation, user=user, file_name="a.md", content="alpha")
    service = AIAgentService(conversation, user=user)

    first = _build(service)  # warms cache
    with _spy_storage_open() as spy:
        second = _build(service)

    assert spy.call_count == 0
    assert first == second


def test_new_attachment_invalidates_cache(_llm_config_two_models):
    """B#3: adding an attachment changes the fingerprint -> cache miss + new doc shown."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    _make_text_attachment(
        conversation=conversation, user=user, file_name="first.md", content="alpha"
    )
    service = AIAgentService(conversation, user=user)
    _build(service)  # warm

    _make_text_attachment(
        conversation=conversation, user=user, file_name="second.md", content="beta"
    )
    with _spy_storage_open() as spy:
        instruction = _build(service)

    # Cache miss: BOTH attachments re-read since the fingerprint covers all of them.
    assert spy.call_count == 2
    assert "first.md" in instruction
    assert "second.md" in instruction


def test_updated_at_change_invalidates_cache(_llm_config_two_models):
    """B#4: bumping an attachment's updated_at must invalidate the cache."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    attachment = _make_text_attachment(
        conversation=conversation, user=user, file_name="a.md", content="alpha"
    )
    service = AIAgentService(conversation, user=user)
    _build(service)  # warm

    # save() refreshes updated_at via auto_now=True on BaseModel.
    attachment.save()
    with _spy_storage_open() as spy:
        _build(service)

    assert spy.call_count == 1


def test_different_model_uses_different_cache_entry(_llm_config_two_models):
    """B#5: switching model_hrid produces a separate cache entry."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    _make_text_attachment(conversation=conversation, user=user, file_name="a.md", content="alpha")
    service_a = AIAgentService(conversation, user=user, model_hrid="model-a")
    service_b = AIAgentService(conversation, user=user, model_hrid="model-b")

    _build(service_a)  # warm cache for model-a
    with _spy_storage_open() as spy:
        _build(service_b)

    assert spy.call_count == 1  # model-b is its own entry


def test_budget_ratio_change_invalidates_cache(_llm_config_two_models, settings):
    """B#6: changing DOCUMENT_CONTEXT_BUDGET_RATIO must invalidate the cache."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    _make_text_attachment(conversation=conversation, user=user, file_name="a.md", content="alpha")
    service = AIAgentService(conversation, user=user)

    _build(service)
    settings.DOCUMENT_CONTEXT_BUDGET_RATIO = 0.25
    with _spy_storage_open() as spy:
        _build(service)

    assert spy.call_count == 1


def test_different_user_uses_different_cache_entry(_llm_config_two_models):
    """B#7: same conversation accessed as a different user is a separate cache entry."""
    owner = UserFactory()
    other_user = UserFactory()
    conversation = ChatConversationFactory(owner=owner)
    _make_text_attachment(conversation=conversation, user=owner, file_name="a.md", content="alpha")

    service_owner = AIAgentService(conversation, user=owner)
    service_other = AIAgentService(conversation, user=other_user)

    _build(service_owner)
    with _spy_storage_open() as spy:
        _build(service_other)

    assert spy.call_count == 1
