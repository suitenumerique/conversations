"""Chat request bodies and answer-stream parsing for both wire formats.

Tags before v0.0.23 speak the Vercel AI SDK v4 data stream; v0.0.23 and later
speak the AI SDK v5 SSE stream.
"""

import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

FIRST_V5_RELEASE = (0, 0, 23)
_RELEASE_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)(?:-[\w.]+)?")
_CURRENT_REFS = {"HEAD", "main"}


class Wire(StrEnum):
    """Wire format spoken by a target."""

    V4 = "v4"
    V5 = "v5"


def tag_at_least(tag: str, release: tuple[int, int, int]) -> bool:
    """Whether a git ref runs `release` or later.

    vX.Y.Z tags (and their pre-releases) compare numerically; HEAD and main are
    current code. Any other ref has no known release and is rejected.
    """
    if tag in _CURRENT_REFS:
        return True
    match = _RELEASE_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(f"unknown target ref {tag}: use a vX.Y.Z tag, HEAD or main")
    return tuple(int(part) for part in match.groups()) >= release


def wire_for_tag(tag: str) -> Wire:
    """Return the wire format of a git ref."""
    return Wire.V5 if tag_at_least(tag, FIRST_V5_RELEASE) else Wire.V4


@dataclass(frozen=True)
class AttachmentRef:
    """A ready attachment, as referenced from a chat message."""

    key: str
    file_name: str
    content_type: str

    @property
    def media_url(self) -> str:
        """URL the frontend puts in messages for an uploaded attachment."""
        return f"/media-key/{self.key}"


def build_user_message(wire: Wire, text: str, attachments: list[AttachmentRef]) -> dict:
    """Return a user message shaped like the frontend's for this wire format."""
    message = {"id": str(uuid.uuid4()), "role": "user"}
    if wire is Wire.V4:
        message["content"] = text
        message["parts"] = [{"type": "text", "text": text}]
        message["experimental_attachments"] = [
            {"name": item.file_name, "contentType": item.content_type, "url": item.media_url}
            for item in attachments
        ]
        return message
    message["parts"] = [{"type": "text", "text": text}] + [
        {
            "type": "file",
            "mediaType": item.content_type,
            "url": item.media_url,
            "filename": item.file_name,
        }
        for item in attachments
    ]
    return message


def build_assistant_message(wire: Wire, text: str) -> dict:
    """Return a previous assistant turn, as the frontend replays it."""
    message = {"id": str(uuid.uuid4()), "role": "assistant"}
    if wire is Wire.V4:
        message["content"] = text
    message["parts"] = [{"type": "text", "text": text}]
    return message


def conversation_query(wire: Wire) -> dict[str, str]:
    """Query parameters of the conversation endpoint for this wire format."""
    return {"protocol": "data"} if wire is Wire.V4 else {}


@dataclass
class StreamResult:
    """What an answer stream produced."""

    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)


def _as_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _read_v4_line(line: str, chunks: list[str], result: StreamResult) -> None:
    code, separator, payload = line.partition(":")
    if not separator:
        return
    if code == "0":
        chunks.append(json.loads(payload))
    elif code == "9":
        call = json.loads(payload)
        result.tool_calls.append({"name": call["toolName"], "args": call.get("args", {})})
    elif code == "h":
        result.sources.append(json.loads(payload)["url"])
    elif code == "a":
        result.tool_outputs.append(_as_text(json.loads(payload).get("result")))
    elif code == "3":
        result.errors.append(json.loads(payload))


def _read_v5_line(line: str, chunks: list[str], result: StreamResult) -> None:
    if not line.startswith("data: "):
        return
    payload = line.removeprefix("data: ")
    if payload == "[DONE]":
        return
    event = json.loads(payload)
    event_type = event.get("type")
    if event_type == "text-delta":
        chunks.append(event["delta"])
    elif event_type == "tool-input-available":
        result.tool_calls.append({"name": event["toolName"], "args": event.get("input", {})})
    elif event_type == "source-url":
        result.sources.append(event["url"])
    elif event_type == "tool-output-available":
        result.tool_outputs.append(_as_text(event.get("output")))
    elif event_type == "error":
        result.errors.append(event.get("errorText", ""))


def parse_stream(lines: Iterable[str], wire: Wire) -> StreamResult:
    """Collect answer text, tool calls and errors from a conversation stream."""
    read_line = _read_v4_line if wire is Wire.V4 else _read_v5_line
    chunks: list[str] = []
    result = StreamResult()
    for line in lines:
        read_line(line, chunks, result)
    result.text = "".join(chunks)
    return result
