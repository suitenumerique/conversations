"""The stop signal, exercised directly against the cache.

No database, no agent and no model: the point of the module is that the
cancellation semantics can be pinned down on their own.
"""
# pylint: disable=protected-access  # tests drive the throttle's clock

import asyncio

from django.core.cache import cache

import pytest

from chat.clients.exceptions import StreamCancelException
from chat.stop_signal import StopSignal

# The watcher polls every POLL_INTERVAL seconds. A test that asserts a watcher
# did *not* fire proves nothing unless it waits past one, so the interval is
# patched down and the waits below are expressed as multiples of it.
TEST_POLL_INTERVAL = 0.01
POLL_MARGIN = TEST_POLL_INTERVAL * 5


@pytest.fixture(name="fast_poll", autouse=True)
def fast_poll_fixture(monkeypatch):
    """Shrink the watcher's poll interval so a test can outlast it."""
    monkeypatch.setattr("chat.stop_signal.POLL_INTERVAL", TEST_POLL_INTERVAL)


@pytest.fixture(name="signal")
def signal_fixture():
    """A signal on its own key, cleared before and after the test."""
    stop_signal = StopSignal("conversation-under-test")
    cache.delete(stop_signal._cache_key)
    yield stop_signal
    cache.delete(stop_signal._cache_key)


@pytest.mark.asyncio
async def test_an_unarmed_signal_does_not_raise(signal):
    """Nothing to stop, nothing happens."""
    await signal.raise_if_stopped(force=True)


@pytest.mark.asyncio
async def test_an_armed_signal_raises(signal):
    """The in-band check unwinds the caller where it stands."""
    signal.arm()

    with pytest.raises(StreamCancelException):
        await signal.raise_if_stopped(force=True)


@pytest.mark.asyncio
async def test_observing_the_signal_consumes_it(signal):
    """A signal is cleared once seen, so it cannot stop the next stream too."""
    signal.arm()
    with pytest.raises(StreamCancelException):
        await signal.raise_if_stopped(force=True)

    await signal.raise_if_stopped(force=True)


@pytest.mark.asyncio
async def test_the_check_is_throttled(signal):
    """A signal armed inside the throttle window is not read yet.

    The per-event callers sit in the hot path; `force` is what the
    out-of-band callers use to bypass the window.
    """
    await signal.raise_if_stopped(force=True)
    signal.arm()

    await signal.raise_if_stopped()

    with pytest.raises(StreamCancelException):
        await signal.raise_if_stopped(force=True)


@pytest.mark.asyncio
async def test_clear_drops_a_leftover_signal(signal):
    """A signal armed after a stream ended must not stop the next one."""
    signal.arm()

    await signal.clear()

    await signal.raise_if_stopped(force=True)


@pytest.mark.asyncio
async def test_the_watcher_cancels_a_blocked_task(signal):
    """A task that reaches no in-band check is cancelled where it is blocked."""
    blocked = asyncio.Event()

    async def _blocked_forever():
        """Park on an await that no stop check can reach."""
        blocked.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(_blocked_forever())
    async with signal.cancelling(task) as watch:
        await blocked.wait()
        signal.arm()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert watch.fired()


@pytest.mark.asyncio
async def test_the_watcher_leaves_an_unstopped_task_alone(signal):
    """Without a signal the watched task runs to completion."""

    async def _quick():
        """Finish before any watcher tick could matter."""
        return "done"

    task = asyncio.create_task(_quick())
    async with signal.cancelling(task) as watch:
        assert await task == "done"
        assert not watch.fired()


@pytest.mark.asyncio
async def test_a_called_off_watcher_stops_watching(signal):
    """`call_off` is what protects a closing write from a late stop."""
    running = asyncio.Event()
    finished = asyncio.Event()

    async def _writes_after_the_run():
        """Stand in for the closing write that must not be cancelled."""
        running.set()
        # Longer than a poll interval, so a watcher that was not called off has
        # time to cancel this and fail the test.
        await asyncio.sleep(POLL_MARGIN)
        finished.set()

    task = asyncio.create_task(_writes_after_the_run())
    async with signal.cancelling(task) as watch:
        await running.wait()
        watch.call_off()
        signal.arm()
        await task

    assert finished.is_set()
    assert not watch.fired()


@pytest.mark.asyncio
async def test_leaving_the_block_stops_the_watcher(signal):
    """No watcher outlives its context, so a later signal cancels nothing."""
    task = asyncio.create_task(asyncio.sleep(60))
    async with signal.cancelling(task):
        pass

    signal.arm()
    # Past a poll interval: a watcher that outlived the block would have fired
    # by now.
    await asyncio.sleep(POLL_MARGIN)

    assert not task.cancelled()
    task.cancel()


@pytest.mark.asyncio
async def test_only_one_observer_consumes_the_signal(signal, monkeypatch):
    """Two observers racing on one armed signal: exactly one wins.

    The in-band check and the watcher read the same key from the same event
    loop. If both could claim it, both would act - the check raising inside the
    node stream while the watcher cancels the producer task mid-write - and the
    clean stop would be replaced by a `CancelledError` nothing upstream catches.
    """
    signal.arm()

    # In production the cache is Redis, so the read is a network round-trip and
    # the loop is free to run the other observer before the delete lands. The
    # locmem backend used in tests never suspends, which would hide the race, so
    # the suspension point is reinstated here.
    real_aget = cache.aget

    async def _aget_that_yields(*args, **kwargs):
        value = await real_aget(*args, **kwargs)
        await asyncio.sleep(0)
        return value

    monkeypatch.setattr(cache, "aget", _aget_that_yields)

    outcomes = await asyncio.gather(signal._consume(), signal._consume())

    assert sorted(outcomes) == [False, True]
