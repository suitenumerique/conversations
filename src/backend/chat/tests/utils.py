"""tools for testing chat functionality"""

import re

from rest_framework import status

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
    """Assert a response is a valid Vercel AI SDK data-stream SSE response."""
    assert response.status_code == status.HTTP_200_OK
    assert response.get("Content-Type") == "text/event-stream"
    assert response.get("x-vercel-ai-data-stream") == "v1"
    assert response.streaming


def replace_uuids_with_placeholder(text):
    """Replace all UUIDs in the given text with a placeholder."""
    text = re.sub('"toolCallId":"([a-z0-9-]){36}"', '"toolCallId":"XXX"', text)
    text = re.sub('"toolCallId":"pyd_ai_([a-z0-9]){32}"', '"toolCallId":"pyd_ai_YYY"', text)
    text = re.sub('"([a-z0-9-]){36}"', '"<mocked_uuid>"', text)
    return text
