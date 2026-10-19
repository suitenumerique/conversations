"""The keepalive loop is what a blocked turn beats from.

It is the only thing that ticks while the stream produces nothing, so a turn
sitting on a document parse or a tool call has nowhere else to say it is still
running. These cover the wiring rather than the keepalive frames themselves,
including what happens to a turn whose reader walks away.
"""

import asyncio
import time

from django.db import connections

import pytest
from asgiref.sync import ThreadSensitiveContext, sync_to_async

from chat.keepalive import stream_with_keepalive_async, stream_with_keepalive_sync


@pytest.mark.asyncio
async def test_a_silent_stream_ticks_the_callback(settings):
    """A source that produces nothing still reaches the callback."""
    settings.KEEPALIVE_INTERVAL = 0.01
    ticks = []

    async def silent():
        """A source blocked long enough to need two keepalives."""
        await asyncio.sleep(0.05)
        yield "finally"

    async def on_keepalive():
        """Stand in for the turn appending its beat."""
        ticks.append(1)

    received = [chunk async for chunk in stream_with_keepalive_async(silent(), on_keepalive)]

    assert ticks, "the blocked stream never ticked"
    # Only the tick is asserted. Whether the source's own item survives a
    # keepalive firing at the same moment is a separate, pre-existing question:
    # the consumer breaks out on a timeout once the producer has finished,
    # without draining what is already queued.
    assert received


@pytest.mark.asyncio
async def test_a_failing_callback_does_not_take_the_stream_down(settings, caplog):
    """A beat that cannot be written is not worth losing the answer over."""
    settings.KEEPALIVE_INTERVAL = 0.01

    async def silent():
        """A source blocked long enough to need a keepalive."""
        await asyncio.sleep(0.05)
        yield "finally"

    async def failing():
        """A beat that fails the way a database blip would."""
        raise RuntimeError("no database")

    received = [chunk async for chunk in stream_with_keepalive_async(silent(), failing)]

    # The stream carried on; see the note above on what is not asserted here.
    assert received
    assert "Keepalive callback failed" in caplog.text


def test_a_silent_sync_stream_ticks_the_callback(settings):
    """The WSGI path beats too: dev and the tests run there, not on ASGI."""
    settings.KEEPALIVE_INTERVAL = 0.01
    ticks = []

    def silent():
        """A source blocked long enough for the keepalive thread to notice.

        That thread wakes twice a second, so a shorter pause is never seen.
        """
        time.sleep(1.2)
        yield "finally"

    received = list(stream_with_keepalive_sync(silent(), lambda: ticks.append(1)))

    assert ticks, "the blocked stream never ticked"
    assert "finally" in received


@pytest.mark.asyncio
async def test_a_reader_that_leaves_does_not_stop_the_source():
    """The turn runs in its own task, so losing the reader must not end it.

    This is the refresh: the browser drops the connection, the ASGI handler
    cancels the response, and the only thing left to decide is whether the
    answer dies with it.
    """
    produced = []

    async def counting():
        """A source slow enough to still be going when the reader leaves."""
        for index in range(5):
            await asyncio.sleep(0.02)
            produced.append(index)
            yield f"frame {index}"

    async def read():
        """Read the stream the way the ASGI handler does."""
        async for _ in stream_with_keepalive_async(counting()):
            pass

    reader = asyncio.create_task(read())
    while not produced:
        await asyncio.sleep(0.01)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader

    await asyncio.sleep(0.3)

    assert produced == [0, 1, 2, 3, 4], "the source stopped with its reader"


@pytest.mark.asyncio
async def test_a_source_left_alone_keeps_beating(settings):
    """A turn with no reader still has to say it is running.

    The loop that beats is the reader's, so once it is gone something else has
    to tick, or a turn that goes quiet looks abandoned and the next question
    folds it while it is still running.
    """
    settings.KEEPALIVE_INTERVAL = 0.01
    ticks = []

    async def silent():
        """A source that produces nothing for a while, then one item."""
        await asyncio.sleep(0.3)
        yield "finally"

    async def on_keepalive():
        """Stand in for the turn appending its beat."""
        ticks.append(1)

    async def read():
        """Read until the reader walks away."""
        async for _ in stream_with_keepalive_async(silent(), on_keepalive):
            pass

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.05)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader

    beaten_before = len(ticks)
    await asyncio.sleep(0.1)

    assert len(ticks) > beaten_before, "nothing beat for the turn left alone"


@pytest.mark.asyncio
async def test_a_source_left_alone_beats_at_once(settings):
    """The first beat for a turn left alone does not wait out an interval.

    The reader's loop beats only after a whole interval of silence. Waiting
    another one once it has left could leave a quiet turn close to two
    intervals without a row, which is about the liveness window.
    """
    settings.KEEPALIVE_INTERVAL = 10
    ticks = []
    release = asyncio.Event()

    async def silent():
        """A source that produces nothing until the test lets it finish."""
        await release.wait()
        yield "finally"

    async def on_keepalive():
        """Stand in for the turn appending its beat."""
        ticks.append(1)

    async def read():
        """Read until the reader walks away."""
        async for _ in stream_with_keepalive_async(silent(), on_keepalive):
            pass

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.02)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader
    await asyncio.sleep(0.05)

    assert ticks == [1], "the turn left alone did not beat at once"

    release.set()
    await asyncio.sleep(0.05)

    assert ticks == [1], "something beat for a turn that was over"


@pytest.mark.asyncio
async def test_a_source_left_alone_is_cancelled_past_the_max_duration(settings):
    """A turn nobody reads any more cannot hold its conversation forever.

    A refresh used to cancel a turn stuck on a call that never returns. Now
    that the turn outlives its reader, the max duration is what ends it.
    """
    settings.KEEPALIVE_INTERVAL = 0.01
    settings.MAX_TURN_DURATION = 0.1
    cancelled = asyncio.Event()

    async def stuck():
        """A source blocked on something that never returns."""
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        yield "never"

    async def read():
        """Read until the reader walks away."""
        async for _ in stream_with_keepalive_async(stuck()):
            pass

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.02)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader

    await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_a_source_left_alone_that_fails_is_logged(caplog):
    """With no reader to re-raise it, a failure must still leave a trace."""
    go_on = asyncio.Event()
    failed = asyncio.Event()

    async def failing():
        """A source that fails once its reader has gone."""
        yield "first"
        await go_on.wait()
        failed.set()
        raise RuntimeError("provider down")

    async def read():
        """Read until the reader walks away."""
        async for _ in stream_with_keepalive_async(failing()):
            pass

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.02)
    reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reader

    go_on.set()
    await asyncio.wait_for(failed.wait(), timeout=1)
    await asyncio.sleep(0.02)

    assert "Turn left alone failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_a_source_left_alone_closes_its_connection():
    """A turn that outlived its request closes the connection it opened.

    The request takes its thread pool with it when it ends, so the turn's
    database work lands on a fresh thread that nothing at the end of a request
    will close. Read inside a ThreadSensitiveContext, the way the ASGI handler
    does, because that is what moves the turn there.
    """
    release = asyncio.Event()
    used = []

    def query():
        """Use the database the way a turn landing does, from its thread."""
        connection = connections["default"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        used.append(connection)

    async def landing():
        """A source that touches the database after its reader has left."""
        yield "first"
        await release.wait()
        await sync_to_async(query)()
        yield "landed"

    async def read():
        """Read until the reader walks away."""
        async for _ in stream_with_keepalive_async(landing()):
            pass

    async with ThreadSensitiveContext():
        reader = asyncio.create_task(read())
        await asyncio.sleep(0.02)
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader

    release.set()
    for _ in range(100):
        if used and used[0].connection is None:
            break
        await asyncio.sleep(0.02)

    assert used, "the turn never reached the database"
    assert used[0].connection is None, "the turn left its connection open"
