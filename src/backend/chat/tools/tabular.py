"""Query tools over the conversation's spreadsheet attachments (CSV, XLSX)."""

import asyncio
import json
import time

from django.core.files.storage import default_storage

import structlog
from celery.exceptions import TimeoutError as CeleryTimeoutError
from pydantic_ai import RunContext, ToolReturn

from core.log_fields import safe_error_fields

from chat.constants import TABULAR_RESULT_TIMEOUT_SECONDS
from chat.tabular import Aggregation, ChartSpec, Filter, GroupKey, Join, SortKey, TableQuery
from chat.tasks import run_tabular_query_task
from chat.tools.exceptions import ModelCannotRetry, UserContentModelRetry
from chat.tools.utils import last_model_retry_soft_fail

logger = structlog.get_logger(__name__)

TIMEOUT_MESSAGE = (
    "The spreadsheet analysis did not finish in time. "
    "You must explain this to the user and ask them to retry later."
)
TIME_LIMIT_MESSAGE = (
    "The spreadsheet analysis took too long to compute. You must explain this to the "
    "user and suggest a simpler question or a smaller file."
)
FAILED_MESSAGE = (
    "The spreadsheet analysis could not be completed. "
    "You must explain this to the user and ask them to retry later."
)
# Why the task produced no output (its `error`), as told to the model.
TASK_ERROR_MESSAGES = {
    "deadline": TIMEOUT_MESSAGE,
    "time_limit": TIME_LIMIT_MESSAGE,
    "failed": FAILED_MESSAGE,
}


def _read_and_delete(key: str) -> dict:
    """Read a task output (`content` and `chart`) from storage, then delete it: it is read once."""
    try:
        with default_storage.open(key, "rb") as file:
            return json.loads(file.read())
    finally:
        default_storage.delete(key)


async def _run_tabular_task(ctx: RunContext, query: dict | None) -> dict:
    """Run the tabular task on a Celery worker, block on it, and read its output.

    Returns the output of a successful task: `content` for the model, `chart`
    (or None) for the UI.

    Same pattern as document parsing: the publish, the wait and the storage
    calls are synchronous round trips, so they run in threads to keep the event
    loop free. Only the storage key of the output goes through Redis.
    """
    # The task skips its write past this point, when nobody waits for it anymore.
    deadline = time.time() + TABULAR_RESULT_TIMEOUT_SECONDS
    async_result = await asyncio.to_thread(
        run_tabular_query_task.delay, str(ctx.deps.conversation.pk), query, deadline
    )
    try:
        result = await asyncio.to_thread(async_result.get, timeout=TABULAR_RESULT_TIMEOUT_SECONDS)
    except CeleryTimeoutError as exc:
        # Still queued: revoke so it doesn't run after the turn moved on. A
        # running task is not stopped by revoke; the hard time limit caps it.
        await asyncio.to_thread(async_result.revoke)
        raise ModelCannotRetry(TIMEOUT_MESSAGE) from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # The task reports its own errors: this is a worker killed (hard time
        # limit, memory) before it could, or the result backend failing.
        logger.error("tabular_task_lost", **safe_error_fields(exc))
        raise ModelCannotRetry(FAILED_MESSAGE) from exc
    finally:
        await asyncio.to_thread(async_result.forget)

    if result["key"] is None:
        raise ModelCannotRetry(TASK_ERROR_MESSAGES[result["error"]])
    try:
        output = await asyncio.to_thread(_read_and_delete, result["key"])
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("tabular_output_read_failed", **safe_error_fields(exc))
        raise ModelCannotRetry(FAILED_MESSAGE) from exc
    if not result["ok"]:
        # Tabular errors name the tables and columns of the user's files.
        raise UserContentModelRetry(output["content"])
    return output


@last_model_retry_soft_fail
async def describe_tables(ctx: RunContext) -> str:
    """Describe the tables loaded from the conversation's spreadsheets."""
    return (await _run_tabular_task(ctx, None))["content"]


@last_model_retry_soft_fail
async def query_table(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # noqa: PLR0913, PLR0917
    ctx: RunContext,
    table: str,
    filters: list[Filter] | None = None,
    group_by: list[GroupKey] | None = None,
    aggregations: list[Aggregation] | None = None,
    columns: list[str] | None = None,
    sort: list[SortKey] | None = None,
    limit: int = 100,
    join: Join | None = None,
    chart: ChartSpec | None = None,
) -> str | ToolReturn:
    """Filter, group, aggregate and sort one spreadsheet table.

    Args:
        table (str): Table name from describe_tables.
        filters (list[Filter] | None): Row conditions, combined with AND.
        group_by (list[GroupKey] | None): Grouping columns (date columns may use a period).
        aggregations (list[Aggregation] | None): Aggregates per group, or over all rows.
        columns (list[str] | None): Columns to return when not aggregating.
        sort (list[SortKey] | None): Sort keys of the result.
        limit (int): Maximum number of rows returned (1 to 100).
        join (Join | None): Second table to inner-join before filtering.
        chart (ChartSpec | None): Also show the result to the user as a chart.
    """
    query = TableQuery(
        table=table,
        join=join,
        filters=filters or [],
        group_by=group_by or [],
        aggregations=aggregations or [],
        columns=columns or [],
        sort=sort or [],
        limit=min(max(limit, 1), 100),
        chart=chart,
    )
    output = await _run_tabular_task(ctx, query.model_dump(mode="json"))
    if not output["chart"]:
        return output["content"]
    # The metadata never reaches the model: it carries the chart data to the UI.
    return ToolReturn(return_value=output["content"], metadata={"chart": output["chart"]})
