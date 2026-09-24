"""The keepalive loop is what a blocked turn beats from.

It is the only thing that ticks while the stream produces nothing, so a turn
sitting on a document parse or a tool call has nowhere else to say it is still
running. These cover the wiring rather than the keepalive frames themselves.
"""

import asyncio

import pytest

from chat.keepalive import stream_with_keepalive_async


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
    assert "finally" in received


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

    assert "finally" in received
    assert "Keepalive callback failed" in caplog.text
