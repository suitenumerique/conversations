"""Tests for the tabular Celery task, the tabular tools and their wiring in AIAgentService."""
# pylint: disable=protected-access

import logging
import time
from datetime import timedelta
from unittest.mock import ANY, MagicMock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

import pytest
from asgiref.sync import sync_to_async
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded, WorkerLostError
from celery.exceptions import TimeoutError as CeleryTimeoutError

from chat.clients.pydantic_ai import AIAgentService
from chat.constants import TABULAR_MAX_OUTPUT_CHARS, TABULAR_RESULT_TIMEOUT_SECONDS
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory
from chat.models import AttachmentStatus
from chat.tasks import purge_tabular_results_task, run_tabular_query_task
from chat.tools.exceptions import ModelCannotRetry, UserContentModelRetry
from chat.tools.tabular import _run_tabular_task

# transaction=True: async tests create rows through sync_to_async, on another
# connection than the test transaction, so a rollback would not clean them up.
pytestmark = pytest.mark.django_db(transaction=True)

SALES_CSV = b"region;montant\nNord;10,5\nSud;4\nNord;1,5\n"
# 400 columns with 150-character headers: every output path exceeds the cap.
WIDE_HEADERS = [f"{index:03d}" + "h" * 147 for index in range(400)]
WIDE_CSV = (",".join(WIDE_HEADERS) + "\n" + ",".join("v" * 50 for _ in WIDE_HEADERS)).encode()


@pytest.fixture(autouse=True, name="base_settings")
def base_settings_fixture(settings):
    """Minimum settings to instantiate AIAgentService."""
    settings.AI_BASE_URL = "https://api.llm.com/v1/"
    settings.AI_API_KEY = "test-key"
    settings.AI_MODEL = "model-123"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful assistant"
    settings.AI_AGENT_TOOLS = []


def _deadline():
    """A deadline the task meets: one minute from now."""
    return time.time() + 60


def _read_result(result):
    """Read the content a task stored, as the tool does."""
    with default_storage.open(result["key"], "rb") as file:
        return file.read().decode("utf-8")


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
        _deadline(),
    )

    assert result == {"ok": True, "key": ANY}
    assert result["key"].startswith("tabular-results/")
    assert _read_result(result) == (
        "| region | montant_sum |\n|---|---|\n| Nord | 12 |\n| Sud | 4 |"
    )


def test_task_describes_tables_without_query():
    """Without a query, the task returns the table description."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    result = run_tabular_query_task(str(conversation.pk), None, _deadline())

    assert result["ok"] is True
    assert "## Table ventes" in _read_result(result)


def test_task_only_loads_ready_spreadsheets_of_the_conversation():
    """Pending uploads, other conversations' files and non-spreadsheets are not loaded."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation, file_name="pending.csv", upload_state=AttachmentStatus.PENDING)
    _spreadsheet(ChatConversationFactory(), file_name="other.csv")
    _spreadsheet(conversation, file_name="notes.txt", content_type="text/plain")

    result = run_tabular_query_task(str(conversation.pk), None, _deadline())

    assert result["ok"] is True
    assert _read_result(result) == "No spreadsheet could be loaded from the attachments."


def test_task_returns_query_errors_for_the_model():
    """A failing query is returned as a non-ok result, not raised."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    result = run_tabular_query_task(str(conversation.pk), {"table": "missing"}, _deadline())

    assert result["ok"] is False
    assert _read_result(result) == 'Unknown table "missing". Available tables: ventes.'


def test_task_writes_nothing_past_the_deadline():
    """Past the deadline the tool has stopped waiting: nothing is stored for it to delete."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    with patch("chat.tasks.default_storage.save") as save:
        result = run_tabular_query_task(str(conversation.pk), None, time.time() - 1)

    assert result == {"ok": False, "key": None, "error": "deadline"}
    save.assert_not_called()


def test_task_writes_nothing_when_the_deadline_passes_during_the_work():
    """A deadline reached while loading or querying also skips the write."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)
    deadline = time.time() + 60

    with (
        patch("chat.tasks.time") as task_time,
        patch("chat.tasks.default_storage.save") as save,
    ):
        task_time.time.side_effect = [deadline - 30, deadline]
        result = run_tabular_query_task(str(conversation.pk), None, deadline)

    assert result == {"ok": False, "key": None, "error": "deadline"}
    save.assert_not_called()


def test_task_applies_the_join_cell_cap_setting(settings):
    """The join cap comes from the TABULAR_JOIN_MAX_CELLS setting."""
    settings.TABULAR_JOIN_MAX_CELLS = 10
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)
    _spreadsheet(conversation, file_name="objectifs.csv")

    result = run_tabular_query_task(
        str(conversation.pk),
        {
            "table": "ventes",
            "join": {"table": "objectifs", "left_on": "region", "right_on": "region"},
        },
        _deadline(),
    )

    assert result["ok"] is False
    assert "would produce 5 rows" in _read_result(result)


def test_task_reports_its_soft_time_limit():
    """A load or query cut by the soft time limit is reported, not raised."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    with patch("chat.tasks.build_dataset", side_effect=SoftTimeLimitExceeded()):
        result = run_tabular_query_task(str(conversation.pk), None, _deadline())

    assert result == {"ok": False, "key": None, "error": "time_limit"}


@pytest.mark.parametrize(
    "target",
    ["chat.tasks.run_table_query", "chat.tasks.default_storage.save"],
)
def test_task_reports_unexpected_errors_without_their_message(target, caplog):
    """Any other failure is reported, and only its type is logged: its message may quote cells."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation)

    with (
        patch(target, side_effect=KeyError("salaire_secret")),
        caplog.at_level(logging.WARNING),
    ):
        result = run_tabular_query_task(str(conversation.pk), {"table": "ventes"}, _deadline())

    assert result == {"ok": False, "key": None, "error": "failed"}
    [line] = [r.msg for r in caplog.records if r.msg["event"] == "tabular_query_failed"]
    assert line["error_type"] == "KeyError"
    assert "salaire_secret" not in caplog.text


@pytest.mark.parametrize(
    "query",
    [
        None,  # describe_tables: one line per column, wide sample rows
        {"table": "ventes"},  # every column of the rows
        {"table": "ventes", "columns": ["missing"]},  # error listing every column
    ],
)
def test_task_output_is_capped(query):
    """No output path stores more than the cap: it all ends up in the model context."""
    conversation = ChatConversationFactory()
    _spreadsheet(conversation, content=WIDE_CSV)

    content = _read_result(run_tabular_query_task(str(conversation.pk), query, _deadline()))

    assert len(content) <= TABULAR_MAX_OUTPUT_CHARS
    assert f"[Output cut at {TABULAR_MAX_OUTPUT_CHARS} characters" in content


def test_purge_deletes_only_old_tabular_results(caplog):
    """Results left unread past an hour are deleted; recent ones and other keys stay."""
    # A prefix of its own: tests running in parallel share the bucket.
    prefix = f"tabular-results-purge-test-{time.time_ns()}/"
    result_key = default_storage.save(f"{prefix}orphan.md", ContentFile(b"| n |"))
    other_key = default_storage.save(f"{prefix[:-1]}-other/keep.csv", ContentFile(b"a"))

    with patch("chat.tasks.TABULAR_RESULTS_PREFIX", prefix), caplog.at_level(logging.INFO):
        purge_tabular_results_task()
        assert default_storage.exists(result_key)

        with patch("chat.tasks.timezone") as task_timezone:
            task_timezone.now.return_value = timezone.now() + timedelta(hours=1, minutes=1)
            purge_tabular_results_task()

    assert not default_storage.exists(result_key)
    assert default_storage.exists(other_key)
    purged = [r.msg for r in caplog.records if r.msg["event"] == "tabular_results_purged"]
    assert [line["deleted"] for line in purged] == [0, 1]
    default_storage.delete(other_key)


def _ctx(conversation):
    ctx = MagicMock()
    ctx.deps.conversation = conversation
    return ctx


def _mock_task(get_result=None, get_side_effect=None):
    task = MagicMock()
    task.delay.return_value.get.return_value = get_result
    task.delay.return_value.get.side_effect = get_side_effect
    return task


def _stored(content: str) -> str:
    """Store a task output the way the task does, and return its key."""
    return default_storage.save("tabular-results/test.md", ContentFile(content.encode("utf-8")))


@pytest.mark.asyncio
async def test_tool_returns_stored_content_and_deletes_it():
    """The tool reads the stored output, deletes it, and forgets the result."""
    conversation = await sync_to_async(ChatConversationFactory)()
    key = await sync_to_async(_stored)("| n |")
    task = _mock_task({"ok": True, "key": key})

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        patch("chat.tools.tabular.time") as tool_time,
    ):
        tool_time.time.return_value = 1000.0
        assert await _run_tabular_task(_ctx(conversation), {"table": "t"}) == "| n |"

    task.delay.assert_called_once_with(
        str(conversation.pk), {"table": "t"}, 1000.0 + TABULAR_RESULT_TIMEOUT_SECONDS
    )
    task.delay.return_value.forget.assert_called_once()
    assert not default_storage.exists(key)


@pytest.mark.asyncio
async def test_tool_asks_model_to_retry_on_query_error():
    """A failed query becomes a ModelRetry carrying the error; the output is deleted too."""
    conversation = await sync_to_async(ChatConversationFactory)()
    key = await sync_to_async(_stored)("Unknown column(s) boom")
    task = _mock_task({"ok": False, "key": key})

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        pytest.raises(UserContentModelRetry, match="Unknown column"),
    ):
        await _run_tabular_task(_ctx(conversation), {"table": "t", "columns": ["boom"]})

    assert not default_storage.exists(key)


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
@pytest.mark.parametrize(
    ("error", "message"),
    [
        ("deadline", "did not finish in time"),
        ("time_limit", "took too long to compute"),
        ("failed", "could not be completed"),
    ],
)
async def test_tool_reports_task_failures_without_retry(error, message):
    """A task that produced no output tells the model why, and not to retry."""
    conversation = await sync_to_async(ChatConversationFactory)()
    task = _mock_task({"ok": False, "key": None, "error": error})

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        pytest.raises(ModelCannotRetry, match=message),
    ):
        await _run_tabular_task(_ctx(conversation), {"table": "t"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [TimeLimitExceeded(60), WorkerLostError("killed"), ConnectionError("broker down")],
)
async def test_tool_reports_a_task_that_never_returned(exc):
    """A worker killed at the hard limit or by memory, or a broker error, ends the tool cleanly."""
    conversation = await sync_to_async(ChatConversationFactory)()
    task = _mock_task(get_side_effect=exc)

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        pytest.raises(ModelCannotRetry, match="could not be completed"),
    ):
        await _run_tabular_task(_ctx(conversation), {"table": "t"})

    task.delay.return_value.forget.assert_called_once()


@pytest.mark.asyncio
async def test_tool_reports_an_unreadable_output():
    """An output that cannot be read back from storage ends the tool cleanly."""
    conversation = await sync_to_async(ChatConversationFactory)()
    task = _mock_task({"ok": True, "key": "tabular-results/missing.md"})

    with (
        patch("chat.tools.tabular.run_tabular_query_task", task),
        patch("chat.tools.tabular.default_storage.open", side_effect=OSError("s3 down")),
        pytest.raises(ModelCannotRetry, match="could not be completed"),
    ):
        await _run_tabular_task(_ctx(conversation), {"table": "t"})


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
