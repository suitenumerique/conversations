"""
Real-component tests for build_document_context_instruction.

These tests exercise the full builder logic with:
- Real Django ORM (factory-created attachments)
- Real default_storage (writes/reads actual content)
- A deterministic token counter (whitespace word count) monkeypatched onto the
  builder module so budget math is precise.
"""

import datetime
import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
from asgiref.sync import sync_to_async

from chat.constants import ACCESS_FULL_CONTEXT, ACCESS_TOOL_CALL_ONLY
from chat.document_context_builder import build_document_context_instruction
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.models import ChatConversationAttachment

# transaction=True is required so writes done via sync_to_async (which run on
# threadpool connections distinct from the test's wrapping transaction) commit
# and are flushed via TRUNCATE between tests instead of leaking across them.
pytestmark = pytest.mark.django_db(transaction=True)


def _word_count(text: str) -> int:
    """Deterministic token count - one 'token' per whitespace-separated word."""
    return len(text.split())


@pytest.fixture(autouse=True)
def deterministic_token_counter(monkeypatch):
    """Swap the builder's token counter for a deterministic word count."""
    monkeypatch.setattr(
        "chat.document_context_builder.count_approx_tokens",
        _word_count,
    )


def _make_attachment(  # pylint: disable=too-many-arguments  # noqa: PLR0913
    conversation, *, file_name, content, conversion_from=None, write=True, created_at=None
):
    """Create an attachment and (optionally) write its content to default_storage.

    `created_at` lets tests pin a deterministic timestamp; auto_now_add otherwise
    sets it at INSERT time and consecutive creates can collide on microseconds,
    making the ("created_at", "id") ordering unstable.
    """
    attachment = ChatConversationAttachmentFactory(
        conversation=conversation,
        file_name=file_name,
        content_type="text/markdown",
        conversion_from=conversion_from,
    )
    if created_at is not None:
        ChatConversationAttachment.objects.filter(pk=attachment.pk).update(created_at=created_at)
        attachment.refresh_from_db(fields=["created_at"])
    if write:
        default_storage.save(attachment.key, ContentFile(content.encode("utf-8")))
    return attachment


def _ts(offset_seconds: int):
    """Build a deterministic timestamp anchored at a fixed base + offset seconds."""
    year = datetime.datetime.now().year
    base = datetime.datetime(year, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    return base + datetime.timedelta(seconds=offset_seconds)


_acreate_conversation = sync_to_async(ChatConversationFactory)
_amake_attachment = sync_to_async(_make_attachment)


def _parse_listing(instruction: str) -> dict:
    """Extract and parse the JSON listing from the instruction string."""
    prefix = "List of documents attached to this conversation:\n"
    assert prefix in instruction, f"missing prefix in: {instruction!r}"
    return json.loads(instruction.split(prefix, 1)[1])


async def _build(conversation, *, max_token_context=100, budget_ratio=0.5, security_buffer=0):
    """Run build_document_context_instruction with real components."""
    text_attachments = await sync_to_async(list)(
        conversation.attachments.filter(content_type__startswith="text/").order_by(
            "created_at", "id"
        )
    )
    return await build_document_context_instruction(
        conversation_id=str(conversation.id),
        text_attachments=text_attachments,
        model_hrid="test-model",
        max_token_context=max_token_context,
        budget_ratio=budget_ratio,
        security_buffer_tokens=security_buffer,
    )


@pytest.mark.asyncio
async def test_empty_attachments_returns_empty_string():
    """Conversation with no text attachments returns an empty instruction."""
    conversation = await _acreate_conversation()
    instruction = await _build(conversation)
    assert instruction == ""


@pytest.mark.asyncio
async def test_single_small_doc_is_inlined():
    """A small doc fits in budget and is inlined as full-context with content."""
    conversation = await _acreate_conversation()
    attachment = await _amake_attachment(
        conversation,
        file_name="notes.md",
        content="ten words " * 5,  # 10 words
    )

    instruction = await _build(conversation)  # budget = 50 tokens
    listing = _parse_listing(instruction)

    assert listing["documents_order"] == "newest_to_oldest"
    assert len(listing["documents"]) == 1
    doc = listing["documents"][0]
    assert doc["document_id"] == str(attachment.id)
    assert doc["title"] == "notes.md"  # not converted, suffix kept
    assert doc["access"] == ACCESS_FULL_CONTEXT
    assert doc["content"] == "ten words " * 5
    # Single doc: index == 1 wins over the index == len check, so first_uploaded_document.
    assert doc["info"] == "first_uploaded_document"


@pytest.mark.asyncio
async def test_oversized_doc_kept_tool_call_only():
    """A doc whose token count exceeds the budget stays tool_call_only."""
    conversation = await _acreate_conversation()
    await _amake_attachment(
        conversation,
        file_name="big.md",
        content="word " * 60,  # 60 > budget 50
    )

    instruction = await _build(conversation)
    listing = _parse_listing(instruction)

    doc = listing["documents"][0]
    assert doc["title"] == "big.md"
    assert doc["access"] == ACCESS_TOOL_CALL_ONLY
    assert doc["content"] == "available via tools"


@pytest.mark.asyncio
async def test_multiple_small_docs_all_inlined():
    """Three small docs fit; payload ordered newest-to-oldest with info labels."""
    conversation = await _acreate_conversation()
    a1 = await _amake_attachment(
        conversation, file_name="doc-1.md", content="alpha " * 10, created_at=_ts(1)
    )  # oldest
    a2 = await _amake_attachment(
        conversation, file_name="doc-2.md", content="beta " * 10, created_at=_ts(2)
    )
    a3 = await _amake_attachment(
        conversation, file_name="doc-3.md", content="gamma " * 10, created_at=_ts(3)
    )  # newest

    instruction = await _build(conversation)  # budget 50, total 30
    listing = _parse_listing(instruction)

    docs = listing["documents"]
    # Newest first in the rendered listing.
    assert [d["document_id"] for d in docs] == [str(a3.id), str(a2.id), str(a1.id)]
    assert all(d["access"] == ACCESS_FULL_CONTEXT for d in docs)
    content_by_id = {d["document_id"]: d["content"] for d in docs}
    assert content_by_id[str(a1.id)] == "alpha " * 10
    assert content_by_id[str(a2.id)] == "beta " * 10
    assert content_by_id[str(a3.id)] == "gamma " * 10
    # info labels are based on upload order (oldest = first, newest = last)
    info_by_id = {d["document_id"]: d["info"] for d in docs}
    assert info_by_id[str(a1.id)] == "first_uploaded_document"
    assert info_by_id[str(a3.id)] == "last_uploaded_document"
    assert info_by_id[str(a2.id)] is None


@pytest.mark.asyncio
async def test_fifo_eviction_evicts_oldest_when_budget_overflows():
    """When a new doc would overflow the budget, the oldest inlined doc is evicted."""
    conversation = await _acreate_conversation()
    a1 = await _amake_attachment(
        conversation, file_name="doc-1.md", content="alpha " * 25, created_at=_ts(1)
    )  # oldest
    a2 = await _amake_attachment(
        conversation, file_name="doc-2.md", content="beta " * 25, created_at=_ts(2)
    )
    a3 = await _amake_attachment(
        conversation, file_name="doc-3.md", content="gamma " * 25, created_at=_ts(3)
    )  # newest

    instruction = await _build(conversation)  # budget 50; 3 * 25 = 75
    listing = _parse_listing(instruction)

    by_id = {d["document_id"]: d for d in listing["documents"]}
    # Oldest evicted, two newest inlined.
    assert by_id[str(a1.id)]["access"] == ACCESS_TOOL_CALL_ONLY
    assert by_id[str(a1.id)]["content"] == "available via tools"
    assert by_id[str(a2.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a2.id)]["content"] == "beta " * 25
    assert by_id[str(a3.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a3.id)]["content"] == "gamma " * 25


@pytest.mark.asyncio
async def test_oversized_and_small_docs_processed_independently():
    """An oversized doc stays tool_call_only; smalls compete for budget normally."""
    conversation = await _acreate_conversation()
    a1 = await _amake_attachment(conversation, file_name="small-1.md", content="alpha " * 20)
    a2 = await _amake_attachment(
        conversation,
        file_name="huge.md",
        content="huge " * 60,  # exceeds budget alone
    )
    a3 = await _amake_attachment(conversation, file_name="small-2.md", content="gamma " * 20)

    instruction = await _build(conversation)  # budget 50
    listing = _parse_listing(instruction)

    by_id = {d["document_id"]: d for d in listing["documents"]}
    # Smalls inline (20 + 20 = 40 <= 50). Huge stays tool_call_only and does not
    # consume budget - it would never have fit anyway.
    assert by_id[str(a1.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a1.id)]["content"] == "alpha " * 20
    assert by_id[str(a2.id)]["access"] == ACCESS_TOOL_CALL_ONLY
    assert by_id[str(a2.id)]["content"] == "available via tools"
    assert by_id[str(a3.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a3.id)]["content"] == "gamma " * 20


@pytest.mark.asyncio
async def test_failed_storage_read_isolated_from_other_docs():
    """If one attachment fails to read, others must still inline correctly."""
    conversation = await _acreate_conversation()
    a1 = await _amake_attachment(conversation, file_name="ok-1.md", content="alpha " * 15)
    # No content written for this one; default_storage.open will raise.
    a_broken = await _amake_attachment(
        conversation, file_name="missing.md", content="(unused)", write=False
    )
    a3 = await _amake_attachment(conversation, file_name="ok-2.md", content="gamma " * 15)

    instruction = await _build(conversation)  # budget 50
    listing = _parse_listing(instruction)

    by_id = {d["document_id"]: d for d in listing["documents"]}
    # Failed read kept tool_call_only with sentinel content; never inlined.
    assert by_id[str(a_broken.id)]["access"] == ACCESS_TOOL_CALL_ONLY
    assert by_id[str(a_broken.id)]["content"] == "available via tools"
    # Other docs still inline (15 + 15 = 30 <= 50). The failed doc must NOT have
    # consumed any budget - regression test for the inlineable-flag fix.
    assert by_id[str(a1.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a1.id)]["content"] == "alpha " * 15
    assert by_id[str(a3.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a3.id)]["content"] == "gamma " * 15


@pytest.mark.asyncio
async def test_fifo_eviction_can_evict_multiple_oldest_for_one_new_doc():
    """A single new doc may evict 2+ older inlined docs to make room."""
    conversation = await _acreate_conversation()
    a1 = await _amake_attachment(
        conversation, file_name="doc-1.md", content="alpha " * 15, created_at=_ts(1)
    )  # 15 tokens, oldest
    a2 = await _amake_attachment(
        conversation, file_name="doc-2.md", content="beta " * 15, created_at=_ts(2)
    )
    a3 = await _amake_attachment(
        conversation, file_name="doc-3.md", content="gamma " * 15, created_at=_ts(3)
    )
    a4 = await _amake_attachment(
        conversation, file_name="doc-4.md", content="delta " * 40, created_at=_ts(4)
    )  # 40 tokens, newest - evicts a1, a2, a3 to fit (40 + 15 = 55 > 50)

    instruction = await _build(conversation)  # budget = 50
    listing = _parse_listing(instruction)

    by_id = {d["document_id"]: d for d in listing["documents"]}
    # a1, a2, a3 all evicted to make room for a4.
    for evicted in (a1, a2, a3):
        assert by_id[str(evicted.id)]["access"] == ACCESS_TOOL_CALL_ONLY
        assert by_id[str(evicted.id)]["content"] == "available via tools"
    assert by_id[str(a4.id)]["access"] == ACCESS_FULL_CONTEXT
    assert by_id[str(a4.id)]["content"] == "delta " * 40


@pytest.mark.asyncio
async def test_doc_exactly_filling_budget_is_inlined():
    """Boundary: a doc whose token count equals the remaining budget still fits (<=)."""
    conversation = await _acreate_conversation()
    attachment = await _amake_attachment(
        conversation,
        file_name="exact.md",
        content="word " * 50,  # exactly equal to budget=50
    )

    instruction = await _build(conversation)
    listing = _parse_listing(instruction)

    doc = listing["documents"][0]
    assert doc["document_id"] == str(attachment.id)
    assert doc["access"] == ACCESS_FULL_CONTEXT
    assert doc["content"] == "word " * 50
