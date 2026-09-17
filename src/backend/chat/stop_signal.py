"""The Stop button for one conversation's stream, from both sides.

A stop request crosses a process boundary: the browser POSTs to
``post_stop_streaming``, which may land in a different worker than the one
running the stream, so the signal is a cache key rather than an in-memory flag.

Two things read that key, and they cover different ground:

- ``raise_if_stopped`` is the in-band check. The streaming code calls it
  between events and it raises ``StreamCancelException`` right where the caller
  stands, which is the cheapest possible unwind. It is also the only check that
  runs *before* the agent does, during history summarization and document
  parsing, where there is no run to cancel yet.
- ``cancelling`` is the out-of-band watcher. Once a run is in flight it polls on
  its own schedule and cancels the run's task wherever it is blocked, because a
  run parked in a tool call or a provider retry reaches no in-band check for as
  long as that takes - minutes, in practice.

Neither subsumes the other, which is why both read the same key.
"""

import asyncio
import dataclasses
import logging
import time
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator

from django.core.cache import cache

from chat.clients.exceptions import StreamCancelException

logger = logging.getLogger(__name__)

# An armed signal is cleared by whoever observes it; this only keeps one that
# nobody ever observes from lingering in the cache forever.
SIGNAL_TIMEOUT = 30 * 60

# How often the watcher polls while a run is in flight. This is the floor on
# how long a Stop click can go unnoticed.
POLL_INTERVAL = 0.5

# How often `raise_if_stopped` is allowed to reach the cache. That check sits in
# the per-event hot path, so it is throttled; the watcher is not.
CHECK_INTERVAL = 2


@dataclasses.dataclass
class StopWatch:
    """Handle on the watcher running behind `StopSignal.cancelling`."""

    _watcher: asyncio.Task
    _requested: asyncio.Event

    def fired(self) -> bool:
        """True when this watcher is what cancelled the task.

        Lets the cancelled code tell our own Stop from a client disconnect: the
        two end the stream differently.
        """
        return self._requested.is_set()

    def call_off(self) -> None:
        """Stop watching: the run is over and nothing is left to cancel.

        Called before a closing write, so a watcher firing mid-write cannot
        cancel it.
        """
        self._watcher.cancel()


class StopSignal:
    """The stop signal for one conversation's stream."""

    def __init__(self, conversation_id) -> None:
        self.conversation_id = conversation_id
        self._last_check = 0.0
        # Read-and-delete has to be atomic between the two observers: they share
        # this instance and the same event loop, so without it both can see the
        # same armed signal and both act on it. See `_consume`.
        self._consuming = asyncio.Lock()

    @property
    def _cache_key(self) -> str:
        """Cache key holding the stop signal for this conversation's stream."""
        return f"streaming:stop:{self.conversation_id}"

    def arm(self) -> None:
        """Ask the running stream to stop, from the request that handled the click."""
        logger.info("Stopping streaming for conversation %s", self.conversation_id)
        cache.set(self._cache_key, "1", timeout=SIGNAL_TIMEOUT)

    async def clear(self) -> None:
        """Drop a signal left over from an earlier stream, and reset the throttle."""
        self._last_check = 0.0
        await cache.adelete(self._cache_key)

    async def _consume(self) -> bool:
        """Claim the signal if it is armed, so exactly one observer acts on it.

        The lock spans the read and the delete. Without it the in-band check and
        the watcher can both read the armed key before either delete lands, and
        both then fire: the in-band check raises `StreamCancelException` inside
        the node stream while the watcher cancels the producer task. The
        cancellation arrives during the interrupted-turn write and replaces the
        clean stop with a `CancelledError` that nothing upstream catches.
        """
        async with self._consuming:
            if not await cache.aget(self._cache_key):
                return False
            await cache.adelete(self._cache_key)
            return True

    async def raise_if_stopped(self, *, force: bool = False) -> None:
        """Raise `StreamCancelException` if the signal is armed.

        Throttled to one cache read every `CHECK_INTERVAL` seconds unless
        `force` is set, since callers sit in the per-event hot path.
        """
        now = time.time()
        if not force and now - self._last_check < CHECK_INTERVAL:
            return
        self._last_check = now

        if await self._consume():
            logger.info("Streaming stopped by cache key for conversation %s", self.conversation_id)
            raise StreamCancelException()

    @asynccontextmanager
    async def cancelling(self, task: asyncio.Task) -> AsyncIterator[StopWatch]:
        """Cancel `task` as soon as the signal is armed, for as long as the block runs."""
        requested = asyncio.Event()
        watcher = asyncio.create_task(self._watch(task, requested))
        try:
            yield StopWatch(watcher, requested)
        finally:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher

    async def _watch(self, task: asyncio.Task, requested: asyncio.Event) -> None:
        """Poll the signal and cancel `task` wherever it happens to be blocked."""
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            if await self._consume():
                logger.info(
                    "Stop signal observed by the watcher; cancelling the run for conversation %s",
                    self.conversation_id,
                )
                requested.set()
                task.cancel()
                return
