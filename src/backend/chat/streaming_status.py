"""Whether a conversation has a turn in flight right now.

A client that navigates away mid-answer loses its stream for good: the
generation keeps running server-side, but the tokens go to a reader that is no
longer there. Coming back, the conversation holds the latest checkpoint, which
looks exactly like an interrupted turn. This marker is what tells the two
apart, so the frontend can wait for the answer instead of calling it lost.

It lives in the cache rather than on the row because it is liveness, not state:
the streaming process renews it while it runs, and it expires on its own when
that process dies, which is the case no cleanup code can cover.
"""

from django.core.cache import cache

# Renewed on the turn's periodic tick (every couple of seconds), so the TTL only
# has to outlast the gaps between ticks. It is the upper bound on how long a
# conversation keeps claiming to stream after the process handling it died, and
# therefore on how long a client polls for an answer that is never coming.
STREAM_ALIVE_TTL_SECONDS = 60

_STREAM_ALIVE_KEY = "streaming:alive:{pk}"


def stream_alive_key(conversation_pk) -> str:
    """Cache key holding the liveness marker of this conversation's turn."""
    return _STREAM_ALIVE_KEY.format(pk=conversation_pk)


async def amark_stream_alive(conversation_pk) -> None:
    """Renew the marker, from the turn that is streaming."""
    await cache.aset(stream_alive_key(conversation_pk), "1", timeout=STREAM_ALIVE_TTL_SECONDS)


async def aclear_stream_alive(conversation_pk) -> None:
    """Drop the marker, once the turn has nothing left to stream."""
    await cache.adelete(stream_alive_key(conversation_pk))


def is_stream_alive(conversation_pk) -> bool:
    """True while a turn is streaming for this conversation."""
    return bool(cache.get(stream_alive_key(conversation_pk)))
