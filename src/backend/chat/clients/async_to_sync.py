"""
Helpers to manage async objects in a synchronous context.

This is not optimal, but we would prefer to stay in a synchronous context
for now.
"""

import asyncio
import queue
import threading


def convert_async_generator_to_sync(async_gen):
    """Convert an async generator to a sync generator."""
    q = queue.Queue()
    sentinel = object()
    exc_sentinel = object()

    async def run_async_gen():
        try:
            async for async_item in async_gen:
                q.put(async_item)
        except Exception as exc:  # pylint: disable=broad-except #noqa: BLE001
            q.put((exc_sentinel, exc))
        finally:
            q.put(sentinel)

    def start_async_loop():
        asyncio.run(run_async_gen())

    thread = threading.Thread(target=start_async_loop, daemon=True)
    thread.start()

    try:
        while True:
            item = q.get()
            if item is sentinel:
                break
            if isinstance(item, tuple) and item[0] is exc_sentinel:
                # re-raise the exception in the sync context
                raise item[1]
            yield item
    finally:
        thread.join()
