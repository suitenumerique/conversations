"""Query tools over the conversation's spreadsheet attachments (CSV, XLSX)."""

import asyncio

from celery.exceptions import TimeoutError as CeleryTimeoutError
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from chat.constants import TABULAR_RESULT_TIMEOUT_SECONDS
from chat.tabular import Aggregation, Filter, GroupKey, Join, SortKey, TableQuery
from chat.tasks import run_tabular_query_task
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail


async def _run_tabular_task(ctx: RunContext, query: dict | None) -> str:
    """Run the tabular task on a Celery worker and block on its result.

    Same pattern as document parsing: the publish and the wait are synchronous
    Redis round trips, so they run in threads to keep the event loop free.
    """
    async_result = await asyncio.to_thread(
        run_tabular_query_task.delay, str(ctx.deps.conversation.pk), query
    )
    try:
        result = await asyncio.to_thread(async_result.get, timeout=TABULAR_RESULT_TIMEOUT_SECONDS)
    except CeleryTimeoutError as exc:
        # Still queued: revoke so it doesn't run after the turn moved on. A
        # running task is not stopped by revoke; the hard time limit caps it.
        await asyncio.to_thread(async_result.revoke)
        raise ModelCannotRetry(
            "The spreadsheet analysis did not finish in time. "
            "You must explain this to the user and ask them to retry later."
        ) from exc
    finally:
        await asyncio.to_thread(async_result.forget)

    if not result["ok"]:
        raise ModelRetry(result["content"])
    return result["content"]


@last_model_retry_soft_fail
async def describe_tables(ctx: RunContext) -> str:
    """Describe the tables loaded from the conversation's spreadsheets."""
    return await _run_tabular_task(ctx, None)


@last_model_retry_soft_fail
async def query_table(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # noqa: PLR0913
    ctx: RunContext,
    table: str,
    filters: list[Filter] | None = None,
    group_by: list[GroupKey] | None = None,
    aggregations: list[Aggregation] | None = None,
    columns: list[str] | None = None,
    sort: list[SortKey] | None = None,
    limit: int = 100,
    join: Join | None = None,
) -> str:
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
    )
    return await _run_tabular_task(ctx, query.model_dump(mode="json"))
