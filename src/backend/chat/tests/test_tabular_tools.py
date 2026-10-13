"""Tests for the tabular Celery task, the tabular tools and their wiring in AIAgentService."""
# pylint: disable=protected-access

from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
from asgiref.sync import sync_to_async
from celery.exceptions import TimeoutError as CeleryTimeoutError
from pydantic_ai.exceptions import ModelRetry

from chat.clients.pydantic_ai import AIAgentService
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.models import AttachmentStatus
from chat.tasks import run_tabular_query_task
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.tabular import _run_tabular_task

# transaction=True: async tests create rows through sync_to_async, on another
# connection than the test transaction, so a rollback would not clean them up.
pytestmark = pytest.mark.django_db(transaction=True)

SALES_CSV = b"region;montant\nNord;10,5\nSud;4\nNord;1,5\n"


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Minimum settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def _spreadsheet(conversation, content=SALES_CSV, **kwargs):
    """Store a CSV in object storage and attach it to the conversation."""
    attachment = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        file_name=kwargs.pop("file_name", "ventes.csv"),
        content_type=kwargs.pop("content_type", "text/csv"),
        upload_state=kwargs.pop("upload_state", AttachmentStatus.READY),
        **kwargs,
    )
    default_storage.save(attachment.key, ContentFile(content))
    return attachment


def test_task_runs_query_on_conversation_spreadsheets():
    """The task loads the conversation's spreadsheets and computes the query."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    result = run_tabular_query_task(
        str(conversation.pk),
        {
            "table": "ventes",
            "group_by": [{"column": "region"}],
            "aggregations": [{"func": "sum", "column": "montant"}],
        },
    )

    assert result == {
        "ok": True,
        "content": "| region | montant_sum |\n|---|---|\n| Nord | 12 |\n| Sud | 4 |",
    }


def test_task_describes_tables_without_query():
    """Without a query, the task returns the table description."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    result = run_tabular_query_task(str(conversation.pk))

    assert result["ok"] is True
    assert "## Table ventes" in result["content"]


def test_task_only_loads_ready_spreadsheets_of_the_conversation():
    """Pending uploads, other conversations' files and non-spreadsheets are not loaded."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation, file_name="pending.csv", upload_state=AttachmentStatus.PENDING)
    _spreadsheet(ChatConversationFactory(), file_name="other.csv")
    _spreadsheet(conversation, file_name="notes.txt", content_type="text/plain")

    result = run_tabular_query_task(str(conversation.pk))

    assert result == {"ok": True, "content": "No spreadsheet could be loaded from the attachments."}


def test_task_returns_query_errors_for_the_model():
    """A failing query is returned as a non-ok result, not raised."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    result = run_tabular_query_task(str(conversation.pk), {"table": "missing"})

    assert result == {
        "ok": False,
        "content": 'Unknown table "missing". Available tables: ventes.',
    }


def _ctx(conversation):
    ctx = MagicMock()
    ctx.deps.conversation = conversation
    return ctx


def _mock_task(get_result=None, get_side_effect=None):
    task = MagicMock()
    task.delay.return_value.get.return_value = get_result
    task.delay.return_value.get.side_effect = get_side_effect
    return task


@pytest.mark.asyncio
async def test_tool_returns_task_content():
    """The tool returns the task content and forgets the result."""
    conversation = await sync_to_async(ChatConversationFactory)()
    task = _mock_task({"ok": True, "content": "| n |"})

    with patch("chat.tools.tabular.run_tabular_query_task", task):
        assert await _run_tabular_task(_ctx(conversation), {"table": "t"}) == "| n |"

    task.delay.assert_called_once_with(str(conversation.pk), {"table": "t"})
    task.delay.return_value.forget.assert_called_once()


@pytest.mark.asyncio
async def test_tool_asks_model_to_retry_on_query_error():
    """A failed query becomes a ModelRetry carrying the error for the model."""
    conversation = await sync_to_async(ChatConversationFactory)()
    task = _mock_task({"ok": False, "content": "Unknown column(s) boom"})

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        pytest.raises(ModelRetry, match="Unknown column"),
    ):
        await _run_tabular_task(_ctx(conversation), {"table": "t", "columns": ["boom"]})


@pytest.mark.asyncio
async def test_tool_revokes_task_on_timeout():
    """A result-wait timeout revokes the task and tells the model it cannot retry."""
    conversation = await sync_to_async(ChatConversationFactory)()
    task = _mock_task(get_side_effect=CeleryTimeoutError("too slow"))

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        pytest.raises(ModelCannotRetry),
    ):
        await _run_tabular_task(_ctx(conversation), {"table": "t"})

    task.delay.return_value.revoke.assert_called_once()
    task.delay.return_value.forget.assert_called_once()


@pytest.mark.asyncio
async def test_tools_registered_when_conversation_has_spreadsheets():
    """READY spreadsheets register describe_tables and query_table."""
    conversation = await sync_to_async(ChatConversationFactory)()
    await sync_to_async(_spreadsheet)(conversation)
    service = AIAgentService(conversation, user=conversation.owner)

    await service._setup_tabular_tools()

    tools = service.conversation_agent._function_toolset.tools
    assert "describe_tables" in tools
    assert "query_table" in tools


@pytest.mark.asyncio
async def test_tools_absent_without_ready_spreadsheets():
    """No READY spreadsheet: the tabular tools are not registered."""
    conversation = await sync_to_async(ChatConversationFactory)()
    await sync_to_async(_spreadsheet)(conversation, upload_state=AttachmentStatus.PENDING)
    service = AIAgentService(conversation, user=conversation.owner)

    await service._setup_tabular_tools()

    assert "query_table" not in service.conversation_agent._function_toolset.tools


@pytest.mark.asyncio
async def test_spreadsheets_are_not_in_the_documents_listing():
    """CSV attachments are queried with query_table, never inlined in the document context."""
    conversation = await sync_to_async(ChatConversationFactory)()
    await sync_to_async(_spreadsheet)(conversation)
    service = AIAgentService(conversation, user=conversation.owner)

    listing = await service._build_documents_listing()

    assert listing is None or not listing.documents
