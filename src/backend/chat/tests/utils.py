"""tools for testing chat functionality"""

import json
import re

from rest_framework import status

UI_MESSAGE_STREAM_HEADER = "x-vercel-ai-ui-message-stream"

ZERO_USAGE = {
    "cache_audio_read_tokens": 0,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "details": {},
    "input_audio_tokens": 0,
    "input_tokens": 0,
    "output_audio_tokens": 0,
    "output_tokens": 0,
}


def assert_data_stream_response(response):
    """Assert a response is a valid Vercel AI SDK UI message stream response."""
    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get(UI_MESSAGE_STREAM_HEADER) == "v1"
    assert response.streaming


def stream_frames(chunks):
    """Split a UI message stream into its SSE payloads, terminator included."""
    stream = chunks if isinstance(chunks, str) else "".join(chunks)
    return [frame.removeprefix("data: ") for frame in stream.split("\n\n") if frame]


def stream_body(chunks):
    """The stream payloads, without the opening `start` frame and the terminator."""
    frames = stream_frames(chunks)
    assert frames[0].startswith('{"type":"start"'), frames[0]
    assert frames[-1] == "[DONE]", frames[-1]
    return frames[1:-1]


def stream_text(chunks):
    """Concatenate the text deltas of a UI message stream."""
    return "".join(
        event["delta"]
        for event in map(json.loads, stream_body(chunks))
        if event["type"] == "text-delta"
    )


def replace_uuids_with_placeholder(text):
    """Replace all UUIDs in the given text with a placeholder."""
    text = re.sub('"toolCallId":"([a-z0-9-]){36}"', '"toolCallId":"XXX"', text)
    text = re.sub('"toolCallId":"pyd_ai_([a-z0-9]){32}"', '"toolCallId":"pyd_ai_YYY"', text)
    text = re.sub('"([a-z0-9-]){36}"', '"<mocked_uuid>"', text)
    return text
