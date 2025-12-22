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

logger = logging.getLogger(__name__)

# Default keepalive message sent to client during stream pauses
KEEPALIVE_MESSAGE = '2:[{"status":"WAITING"}]\n'
# Default keepalive interval: 55s (safely below typical 60s proxy timeouts)
# Prevents connection drops during long stream pauses while providing 5s safety margin.
# Works for our current production proxies. Override via keepalive_interval parameter.
KEEPALIVE_INTERVAL = 55.0  # seconds


async def stream_with_keepalive_async(
    stream: AsyncIterator,
) -> AsyncIterator:
    """Wrap an async iterator to emit keepalive during long pauses.

    Args:
        stream: The async iterator to wrap
    Yields:
        Items from the original stream, plus keepalive messages during pauses
    """
    q: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()

    async def producer():
        """Background task that consumes the original stream into a queue."""
        try:
            async for stream_item in stream:
                await q.put(stream_item)
        finally:
            finished.set()
            await q.put(None)

    producer_task = asyncio.create_task(producer())

    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_INTERVAL)
                if item is None:
                    break

                yield item
            except asyncio.TimeoutError:
                # No data received within interval
                if finished.is_set():
                    break

                logger.debug("Send keepalive")
                yield KEEPALIVE_MESSAGE
    finally:
        # Cleanup
        producer_task.cancel()
        try:
            await producer_task
        except asyncio.CancelledError:
            pass


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


def stream_with_keepalive_sync(
    stream: Iterator[str],
) -> Iterator[str]:
    """Wraps a synchronous stream with keepalive messages."""

    q = queue.Queue()
    stream_done = threading.Event()
    last_output_time = [get_current_time()]
    exception_holder: list[Exception] = []

    def consume_stream():
        """Consume stream and put chunks in queue."""
        try:
            for chunk in stream:
                if stream_done.is_set():
                    return
                q.put(("data", chunk), timeout=1)
        # pylint: disable=broad-exception-caught
        except Exception as e:
            logger.exception("Error in stream consumption")
            exception_holder[0] = e
            q.put(("error", str(e)))
        finally:
            stream_done.set()

    def send_keepalives():
        """Send keepalive messages during idle periods."""
        while not stream_done.is_set():
            time.sleep(0.5)
            t = get_current_time()

            if t - last_output_time[0] >= KEEPALIVE_INTERVAL:
                try:
                    q.put(("keepalive", KEEPALIVE_MESSAGE), timeout=0.1)
                except queue.Full:
                    pass

    # Start threads
    for target in (consume_stream, send_keepalives):
        threading.Thread(target=target, daemon=True).start()

    try:
        while not stream_done.is_set() or not q.empty():
            try:
                msg_type, msg_data = q.get(timeout=1)
            except queue.Empty:
                # Send keepalive on timeout if stream still active
                if not stream_done.is_set():
                    logger.debug("Send keepalive")
                    yield KEEPALIVE_MESSAGE
                    last_output_time[0] = get_current_time()
                continue

            # Handle error messages
            if msg_type == "error":
                logger.error("Stream error: %s", msg_data)
                if exception_holder and exception_holder[0]:
                    raise exception_holder[0]
                break
            # Yield data or keepalive and update timestamp

            yield msg_data
            last_output_time[0] = get_current_time()

    finally:
        stream_done.set()
