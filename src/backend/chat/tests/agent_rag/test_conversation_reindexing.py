"""Tests for rebuild_conversation_collection, the Celery side of a re-index."""

import logging
import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
from celery.exceptions import SoftTimeLimitExceeded

from core.file_upload.enums import AttachmentStatus

from chat.agent_rag.conversation_reindexing import rebuild_conversation_collection
from chat.clients.error_classification import RAG_ERROR
from chat.enums import CollectionIndexState
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory

REINDEXING_LOGGER = "chat.agent_rag.conversation_reindexing"

pytestmark = pytest.mark.django_db


def _records(caplog, event):
    """Reindexing records for `event` (structlog records carry a dict msg)."""
    return [r for r in caplog.records if r.name == REINDEXING_LOGGER and r.msg["event"] == event]


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError whose response carries the given status code."""
    request = httpx.Request("POST", "https://albert.example.com/v1/collections")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


def _indexing_conversation(**kwargs):
    """A conversation whose re-index claim is held, as the web turn leaves it."""
    kwargs.setdefault("collection_id", None)
    return ChatConversationFactory(index_state=CollectionIndexState.INDEXING, **kwargs)


def _text_attachment(conversation, **kwargs):
    return ChatConversationAttachmentFactory(
        conversation=conversation,
        upload_state=AttachmentStatus.READY,
        content_type="text/markdown",
        **kwargs,
    )


def _mock_store(collection_id="new-456"):
    store = MagicMock()
    store.collection_id = collection_id
    store.store_document.return_value = "doc-id"
    return store


def _rebuild(conversation, attachments, store):
    with (
        patch(
            "chat.agent_rag.conversation_reindexing.document_store_backend",
            MagicMock(return_value=store),
        ),
        patch(
            "chat.agent_rag.conversation_reindexing._read_attachment_bytes",
            return_value=b"data",
        ),
    ):
        return rebuild_conversation_collection(
            str(conversation.pk), [str(a.pk) for a in attachments]
        )


def test_rebuild_stores_documents_and_saves_collection_id():
    """Every attachment is stored as text and the collection id is saved."""
    conversation = _indexing_conversation()
    attachments = [_text_attachment(conversation), _text_attachment(conversation)]
    store = _mock_store()
    store.store_document.side_effect = ["doc-1", "doc-2"]

    result = _rebuild(conversation, attachments, store)

    assert result == {"state": "done"}
    store.create_collection.assert_called_once_with(name=f"conversation-{conversation.pk}")
    assert store.store_document.call_count == 2
    store.parse_document.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.index_state == CollectionIndexState.INDEXED
    assert conversation.collection_id == "new-456"
    for attachment in attachments:
        attachment.refresh_from_db()
        assert attachment.is_indexed is True
    assert {a.rag_document_id for a in attachments} == {"doc-1", "doc-2"}


def test_rebuild_reuses_existing_collection():
    """An existing collection is reused, so a retry only adds the missing documents."""
    conversation = _indexing_conversation(collection_id="col-existing")
    attachment = _text_attachment(conversation)
    store = _mock_store(collection_id="col-existing")

    result = _rebuild(conversation, [attachment], store)

    assert result == {"state": "done"}
    store.create_collection.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.collection_id == "col-existing"


@pytest.mark.parametrize(
    "exc, kind",
    [
        (RuntimeError("Albert down"), "rag_error"),
        (_http_error(500), "rag_unavailable"),
        (httpx.ConnectError("no route"), "rag_connection_error"),
    ],
)
def test_rebuild_collection_create_failure(caplog, exc, kind):
    """A collection creation failure sets ERROR and resets the attachments."""
    conversation = _indexing_conversation()
    attachment = _text_attachment(conversation, rag_document_id="stale-rag-id")
    store = _mock_store(collection_id=None)
    store.create_collection.side_effect = exc

    caplog.set_level(logging.ERROR, logger=REINDEXING_LOGGER)
    result = _rebuild(conversation, [attachment], store)

    assert result["state"] == "error"
    assert result["kind"] == kind
    store.store_document.assert_not_called()
    failures = _records(caplog, "reindex_collection_create_failed")
    assert len(failures) == 1
    assert failures[0].exc_info is not None
    conversation.refresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR
    assert conversation.collection_id is None
    attachment.refresh_from_db()
    assert attachment.is_indexed is False
    assert attachment.rag_document_id is None


def test_rebuild_partial_failure(caplog):
    """One failed document does not stop the others; the row ends in ERROR."""
    conversation = _indexing_conversation()
    ok = _text_attachment(conversation, file_name="ok.md")
    broken = _text_attachment(conversation, file_name="broken.md")
    store = _mock_store(collection_id="col-new")
    store.store_document.side_effect = ["doc-ok", RuntimeError("boom")]

    caplog.set_level(logging.ERROR, logger=REINDEXING_LOGGER)
    result = _rebuild(conversation, [ok, broken], store)

    assert result == {"state": "partial", "failed_documents": ["broken.md"]}
    assert len(_records(caplog, "reindex_attachment_failed")) == 1
    conversation.refresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR
    assert conversation.collection_id == "col-new"
    ok.refresh_from_db()
    assert ok.is_indexed is True


def test_rebuild_all_failures_uses_last_failure_kind(caplog):
    """When every document fails, the result carries the last failure's kind."""
    conversation = _indexing_conversation()
    attachments = [
        _text_attachment(conversation, file_name="first.md"),
        _text_attachment(conversation, file_name="second.md"),
    ]
    store = _mock_store(collection_id="col-mix")
    store.store_document.side_effect = [RuntimeError("boom"), httpx.ConnectError("no route")]

    caplog.set_level(logging.ERROR, logger=REINDEXING_LOGGER)
    result = _rebuild(conversation, attachments, store)

    assert result["state"] == "error"
    assert result["kind"] == "rag_connection_error"
    assert len(_records(caplog, "reindex_attachment_failed")) == 2
    conversation.refresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR
    assert conversation.collection_id == "col-mix"


def test_rebuild_skips_ids_no_longer_ready():
    """Attachments deleted or no longer READY since the selection are skipped."""
    conversation = _indexing_conversation()
    kept = _text_attachment(conversation)
    deleted = _text_attachment(conversation)
    pending = _text_attachment(conversation)
    ids = [str(kept.pk), str(deleted.pk), str(pending.pk)]
    deleted.delete()
    pending.upload_state = AttachmentStatus.PENDING
    pending.save()
    store = _mock_store()

    with (
        patch(
            "chat.agent_rag.conversation_reindexing.document_store_backend",
            MagicMock(return_value=store),
        ),
        patch(
            "chat.agent_rag.conversation_reindexing._read_attachment_bytes",
            return_value=b"data",
        ),
    ):
        result = rebuild_conversation_collection(str(conversation.pk), ids)

    assert result == {"state": "done"}
    assert store.store_document.call_count == 1
    kept.refresh_from_db()
    assert kept.is_indexed is True


def test_rebuild_noop_when_row_not_indexing():
    """A row that lost its claim (e.g. de-indexed again) is left untouched."""
    conversation = ChatConversationFactory(index_state=CollectionIndexState.DEINDEXED)
    attachment = _text_attachment(conversation)
    store = _mock_store()

    result = _rebuild(conversation, [attachment], store)

    assert result["state"] == "error"
    assert result["kind"] == "concurrent_reindex"
    store.create_collection.assert_not_called()
    store.store_document.assert_not_called()
    conversation.refresh_from_db()
    assert conversation.index_state == CollectionIndexState.DEINDEXED


def test_rebuild_soft_time_limit_keeps_progress():
    """Hitting the soft time limit keeps what was stored and sets ERROR."""
    conversation = _indexing_conversation()
    first = _text_attachment(conversation, file_name="first.md")
    second = _text_attachment(conversation, file_name="second.md")
    store = _mock_store(collection_id="col-new")
    store.store_document.side_effect = ["doc-1", SoftTimeLimitExceeded()]

    result = _rebuild(conversation, [first, second], store)

    assert result["state"] == "error"
    assert result["kind"] == RAG_ERROR
    conversation.refresh_from_db()
    assert conversation.index_state == CollectionIndexState.ERROR
    assert conversation.collection_id == "col-new"
    first.refresh_from_db()
    assert first.is_indexed is True
    second.refresh_from_db()
    assert second.is_indexed is False


def test_rebuild_conversation_gone(caplog):
    """A conversation deleted before the task runs is reported, not raised."""
    caplog.set_level(logging.INFO, logger=REINDEXING_LOGGER)

    result = rebuild_conversation_collection(str(uuid.uuid4()), [])

    assert result["state"] == "error"
    assert result["kind"] == RAG_ERROR
    assert len(_records(caplog, "reindex_conversation_gone")) == 1


def test_rebuild_saves_new_collection_id_before_storing():
    """A worker killed mid-loop leaves the new collection recorded on the row.

    Otherwise the stored attachments (is_indexed=True) would point at a
    collection the row no longer knows, and the next re-index would skip them.
    """
    conversation = _indexing_conversation()
    attachment = _text_attachment(conversation)
    store = _mock_store(collection_id="col-early")
    seen = []

    def record_row(**kwargs):
        conversation.refresh_from_db()
        seen.append((conversation.collection_id, conversation.index_state))
        return "doc-id"

    store.store_document.side_effect = record_row

    _rebuild(conversation, [attachment], store)

    assert seen == [("col-early", CollectionIndexState.INDEXING)]


def test_rebuild_skips_attachments_indexed_since_selection():
    """An attachment another task already stored is not stored twice."""
    conversation = _indexing_conversation(collection_id="col-1")
    done = _text_attachment(conversation, is_indexed=True)
    todo = _text_attachment(conversation)
    store = _mock_store(collection_id="col-1")

    result = _rebuild(conversation, [done, todo], store)

    assert result == {"state": "done"}
    assert store.store_document.call_count == 1
