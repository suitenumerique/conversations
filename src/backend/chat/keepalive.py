"""Helpers to prevent proxy timeouts during long-running stream operations.

This module provides utilities to wrap synchronous and asynchronous iterators
with keepalive messages. When a stream pauses for longer than the specified
interval, keepalive messages are injected to prevent proxy/gateway
timeouts while waiting for the stream data.
"""

import asyncio
import logging
import queue
import threading
import time
from typing import AsyncIterator, Iterator

from django.conf import settings
from django.db import connections

from asgiref.sync import sync_to_async

from .vercel_ai_sdk.core.events_v5 import DataPart as V5DataPart
from .vercel_ai_sdk.encoder import CURRENT_EVENT_ENCODER_VERSION, EventEncoder
from .vercel_ai_sdk.encoder.v4_to_v5 import data_part_type

logger = logging.getLogger(__name__)


def get_keepalive_message() -> str:
    """Generate a keepalive message.

    Transient, so the client hands it to `onData` and never adds it to the
    message: it exists only to keep the connection warm.
    """
    event = V5DataPart(type=data_part_type("keepalive"), data={"status": "WAITING"})
    encoder = EventEncoder(CURRENT_EVENT_ENCODER_VERSION)
    return encoder.encode(event)


# Turns that outlived their reader. A turn writes itself to the database as it
# goes, so losing the reader is not losing the answer. What a task does need is
# someone holding a reference to it: nothing awaits these any more, and a task
# nobody holds can be garbage collected in the middle of an answer.
_running_alone: set = set()


def _keep(task: asyncio.Task) -> None:
    """Hold on to a task nothing awaits, until it is done."""
    _running_alone.add(task)
    task.add_done_callback(_running_alone.discard)


async def _run_alone(producer_task: asyncio.Task, on_keepalive, deadline: float) -> None:
    """Beat for a turn whose reader is gone, until the turn ends.

    The loop in `stream_with_keepalive_async` is what beats while someone is
    reading, and it leaves when the reader does. Without this, a turn that then
    goes quiet for longer than the liveness window - a long tool call - reads as
    abandoned, and the next question on that conversation folds it while it is
    still running.

    It beats straight away: the reader's loop beats only after a whole interval
    of silence, so waiting another one here could leave a quiet turn close to
    two intervals without a row, which is about the liveness window.

    A turn left alone is also one nobody can cut short by refreshing any more,
    so it is held to MAX_TURN_DURATION: past `deadline` it is cancelled, which
    files what it produced as interrupted.

    Once the turn is over, the database connections it opened are closed. The
    request took its thread pool with it when it ended, so the turn's database
    work moved to a thread of its own, the one this task's `sync_to_async`
    lands on too, and nothing at the end of a request will close it.
    """
    try:
        while True:
            remaining = deadline - get_current_time()
            if remaining <= 0:
                logger.warning(
                    "Turn left alone still running after %ss, cancelling it",
                    settings.MAX_TURN_DURATION,
                )
                producer_task.cancel()
                # Let it file itself as interrupted before its connection goes.
                await asyncio.gather(producer_task, return_exceptions=True)
                return
            await _call_keepalive_async(on_keepalive)
            done, _ = await asyncio.wait(
                {producer_task}, timeout=min(settings.KEEPALIVE_INTERVAL, remaining)
            )
            if done:
                return
    finally:
        await asyncio.shield(sync_to_async(connections.close_all)())


async def _consume_stream_async(
    stream: AsyncIterator[str],
    q: asyncio.Queue,
    finished: asyncio.Event,
    reader_gone: asyncio.Event,
) -> None:
    """Background task that consumes the original stream into a queue.

    Once the reader is gone nothing drains that queue, so the rest of the
    answer is produced but no longer queued. It is on its way to the database
    either way, which is where the next reader looks for it.
    """

    try:
        async for stream_item in stream:
            if reader_gone.is_set():
                continue
            await q.put(stream_item)
    except Exception as exc:  # pylint: disable=broad-except
        if reader_gone.is_set():
            # Nobody is left to re-raise it, so this is the only trace it leaves.
            logger.exception("Turn left alone failed")
        else:
            # Pass exceptions through the queue so the consumer can re-raise them.
            # This ensures errors aren't silently swallowed.
            await q.put(exc)
    finally:
        finished.set()
        await q.put(None)  # Sentinel to signal completion


async def _call_keepalive_async(on_keepalive) -> None:
    """Hand the keepalive to its callback, if there is one.

    Failures are logged and swallowed: a beat that cannot be written is not
    worth losing the answer over.
    """
    if on_keepalive is None:
        return
    try:
        await on_keepalive()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Keepalive callback failed")


async def stream_with_keepalive_async(
    stream: AsyncIterator[str],
    on_keepalive=None,
) -> AsyncIterator[str]:
    """Wrap an async iterator to emit keepalive during long pauses.

    Args:
        stream: The async iterator to wrap
        on_keepalive: Awaited each time a pause is long enough to need a
            keepalive. This loop is the only thing that ticks while the stream
            produces nothing - the source can sit for minutes on a document
            parse or a tool call - so it is also the only place from which
            something blocked can prove it is still running. Failures are
            logged and swallowed: a keepalive must not take the stream down.
        A reader that goes away does not take the source with it: the
            producer below is a task of its own, and it is left running. That
            is what lets a refreshed page pick up an answer that was already
            being written rather than find it cut short. It is still held to
            MAX_TURN_DURATION from when this wrapper started.
    Yields:
        Items from the original stream, plus keepalive messages during pauses
    Raises:
        Any exception raised by the original stream
    """
    q: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()
    reader_gone = asyncio.Event()
    keepalive_message = get_keepalive_message()
    deadline = get_current_time() + settings.MAX_TURN_DURATION

    producer_task = asyncio.create_task(_consume_stream_async(stream, q, finished, reader_gone))

    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=settings.KEEPALIVE_INTERVAL)
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
            except asyncio.TimeoutError:
                # No data received within interval
                if finished.is_set():
                    # Producer is done, queue is empty (else we would not have timed out)
                    break

                logger.debug("Send keepalive")
                await _call_keepalive_async(on_keepalive)
                yield keepalive_message
    finally:
        if not producer_task.done():
            # The reader left before the source was done, which on ASGI is what
            # a page refresh looks like: the handler cancels the response and
            # this loop with it. Cancelling the producer here would take the
            # turn down too, so it is left to finish, store itself and drop its
            # rows the way it would have with someone watching.
            reader_gone.set()
            _keep(producer_task)
            _keep(asyncio.create_task(_run_alone(producer_task, on_keepalive, deadline)))


def get_current_time() -> float:
    """Get current monotonic time, avoiding freezegun interferences.

    Returns time.monotonic() which:
    - Is NOT affected by freezegun's @freeze_time decorator (unlike time.time())
    - Prevents issues where frozen time in main thread differs from real time in
      spawned threads, causing incorrect keepalive interval computation
    - Is the best clock for measuring time intervals

    Wrapped in a function to ease mocking in tests.

    Returns:
        float: Monotonic time in seconds since an arbitrary reference point
    """
    return time.monotonic()


def _consume_stream_sync(
    stream: Iterator[str], q: queue.Queue, stream_done: threading.Event
) -> None:
    """Read from source stream and forward chunks to queue."""
    try:
        for chunk in stream:
            if stream_done.is_set():
                return  # early exit
            q.put(chunk, timeout=1)  # Arbitrary timeout prevents blocking forever
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error in stream consumption")
        q.put(e)
    finally:
        stream_done.set()


def _send_keepalives(
    q: queue.Queue,
    stream_done: threading.Event,
    keepalive_message: str,
    last_yield_time: list,
) -> None:
    """Inject keepalive messages when idle too long.

    Uses get_current_time() (time.monotonic) instead of time.time()
    to avoid issues with freezegun in tests.
    """
    while not stream_done.is_set():
        # Sleep before checking to give main loop time to process and update timestamp
        time.sleep(0.5)  # let main loop process first, empiric value
        if get_current_time() - last_yield_time[0] >= settings.KEEPALIVE_INTERVAL:
            try:
                q.put(keepalive_message, timeout=0.1)
            except queue.Full:
                pass


def _call_keepalive_sync(on_keepalive) -> None:
    """Hand the keepalive to its callback, if there is one.

    Failures are logged and swallowed: a beat that cannot be written is not
    worth losing the answer over.
    """
    if on_keepalive is None:
        return
    try:
        on_keepalive()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Keepalive callback failed")


def stream_with_keepalive_sync(stream: Iterator[str], on_keepalive=None) -> Iterator[str]:
    """Wraps a synchronous stream with keepalive messages.

    `on_keepalive` is called each time a pause is long enough to need one, for
    the same reason as in the async variant: this loop is the only thing still
    running while the source produces nothing. It is called from the request's
    own thread, not the keepalive thread, so it uses the connection that is
    already open. Failures are logged and swallowed.

    The source and the keepalive clock each run in their own thread and reach
    this loop through `q`; `_consume_stream_sync` and `_send_keepalives` are
    those threads.
    """

    q: queue.Queue = queue.Queue()
    stream_done = threading.Event()
    keepalive_message = get_keepalive_message()
    # Mutable container so threads can read/write shared timestamp
    last_yield_time = [get_current_time()]

    for target, args in (
        (_consume_stream_sync, (stream, q, stream_done)),
        (_send_keepalives, (q, stream_done, keepalive_message, last_yield_time)),
    ):
        threading.Thread(target=target, args=args, daemon=True).start()

    try:
        # Continue while stream is active or queue has still items
        while not stream_done.is_set() or not q.empty():
            try:
                item = q.get(timeout=1)  # short timeout, avoid blocking and stay responsive
            except queue.Empty:
                continue

            # Re-raise from _consume_stream_sync
            if isinstance(item, Exception):
                raise item

            if item == keepalive_message:
                # The keepalive thread can queue a message while the source stream is
                # finishing, which would put it after the terminator frame. Nothing
                # needs keeping alive once the stream is done, so drop it.
                if stream_done.is_set():
                    continue
                _call_keepalive_sync(on_keepalive)

            yield item
            last_yield_time[0] = get_current_time()
    finally:
        # Signal threads to stop
        stream_done.set()
