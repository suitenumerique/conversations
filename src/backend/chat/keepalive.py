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

from .vercel_ai_sdk.core.events_v4 import DataPart as V4DataPart
from .vercel_ai_sdk.core.events_v5 import DataPart as V5DataPart
from .vercel_ai_sdk.encoder import (
    CURRENT_EVENT_ENCODER_VERSION,
    EventEncoder,
    EventEncoderVersion,
)

logger = logging.getLogger(__name__)


def get_keepalive_message() -> str:
    """Generate a keepalive message based on encoder/SDK version."""
    if CURRENT_EVENT_ENCODER_VERSION == EventEncoderVersion.V4:
        event = V4DataPart(data=[{"status": "WAITING"}])
    else:
        event = V5DataPart(data={"status": "WAITING"})
    encoder = EventEncoder(CURRENT_EVENT_ENCODER_VERSION)
    return encoder.encode(event)


async def stream_with_keepalive_async(
    stream: AsyncIterator[str],
) -> AsyncIterator[str]:
    """Wrap an async iterator to emit keepalive during long pauses.

    Args:
        stream: The async iterator to wrap
    Yields:
        Items from the original stream, plus keepalive messages during pauses
    Raises:
        Any exception raised by the original stream
    """
    q: asyncio.Queue = asyncio.Queue()
    finished = asyncio.Event()
    keepalive_message = get_keepalive_message()

    async def producer():
        """Background task that consumes the original stream into a queue."""

        try:
            async for stream_item in stream:
                await q.put(stream_item)
        except Exception as exc:  # pylint: disable=broad-except #noqa: BLE001
            # Pass exceptions through the queue so the consumer can re-raise them.
            # This ensures errors aren't silently swallowed.
            await q.put(exc)
        finally:
            finished.set()
            await q.put(None)  # Sentinel to signal completion

    producer_task = asyncio.create_task(producer())

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
                yield keepalive_message
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


def stream_with_keepalive_sync(stream: Iterator[str]) -> Iterator[str]:
    """Wraps a synchronous stream with keepalive messages."""

    q: queue.Queue = queue.Queue()
    stream_done = threading.Event()
    keepalive_message = get_keepalive_message()
    # Mutable container so threads can read/write shared timestamp
    last_yield_time = [get_current_time()]

    def consume_stream():
        """Read from source stream and forward chunks to queue."""
        try:
            for chunk in stream:
                if stream_done.is_set():
                    return  # early exit
                q.put(chunk, timeout=1)  # Arbitrary timeout prevents blocking forever
        # pylint: disable=broad-exception-caught
        except Exception as e:
            logger.exception("Error in stream consumption")
            q.put(e)
        finally:
            stream_done.set()

    def send_keepalives():
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

    for target in (consume_stream, send_keepalives):
        threading.Thread(target=target, daemon=True).start()

    try:
        # Continue while stream is active or queue has still items
        while not stream_done.is_set() or not q.empty():
            try:
                item = q.get(timeout=1)  # short timeout, avoid blocking and stay responsive
            except queue.Empty:
                continue

            # Re-raise from consume_stream
            if isinstance(item, Exception):
                raise item

            yield item
            last_yield_time[0] = get_current_time()
    finally:
        # Signal threads to stop
        stream_done.set()
