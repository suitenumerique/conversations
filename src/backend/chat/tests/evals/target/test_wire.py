"""Tests for chat request bodies and stream parsing on both wire formats."""

import json

import pytest

from chat.evals.target.wire import (
    AttachmentRef,
    Wire,
    build_assistant_message,
    build_user_message,
    conversation_query,
    parse_stream,
    tag_at_least,
    wire_for_tag,
)


@pytest.fixture(name="attachment")
def attachment_fixture():
    """A ready docx attachment."""
    return AttachmentRef(
        key="conv-1/attachments/file-1.docx",
        file_name="cr.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.0.19", Wire.V4),
        ("v0.0.21", Wire.V4),
        ("v0.0.22", Wire.V4),
        ("v0.0.23", Wire.V5),
        ("v0.1.0", Wire.V5),
        ("HEAD", Wire.V5),
        ("main", Wire.V5),
    ],
)
def test_wire_for_tag(tag, expected):
    """v0.0.23 switched to AI SDK v5; non-release refs are current code."""
    assert wire_for_tag(tag) is expected


def test_v4_message_uses_experimental_attachments(attachment):
    """v4 sends text in content + parts and documents as experimental_attachments."""
    message = build_user_message(Wire.V4, "Résume", [attachment])

    assert message["role"] == "user"
    assert message["content"] == "Résume"
    assert message["parts"] == [{"type": "text", "text": "Résume"}]
    assert message["experimental_attachments"] == [
        {
            "name": "cr.docx",
            "contentType": attachment.content_type,
            "url": "/media-key/conv-1/attachments/file-1.docx",
        }
    ]
    assert message["id"]


def test_v5_message_uses_file_parts(attachment):
    """v5 sends documents as file parts after the text part."""
    message = build_user_message(Wire.V5, "Résume", [attachment])

    assert message["role"] == "user"
    assert "content" not in message
    assert message["parts"] == [
        {"type": "text", "text": "Résume"},
        {
            "type": "file",
            "mediaType": attachment.content_type,
            "url": "/media-key/conv-1/attachments/file-1.docx",
            "filename": "cr.docx",
        },
    ]


def test_conversation_query():
    """Only v4 needs the protocol query parameter."""
    assert conversation_query(Wire.V4) == {"protocol": "data"}
    assert not conversation_query(Wire.V5)


def test_parse_v4_text_and_tool_calls():
    """Text parts are JSON strings; tool calls carry name and args."""
    lines = [
        'f:{"messageId":"m1"}',
        '9:{"toolCallId":"c1","toolName":"summarize","args":{"instructions":"en 3 points"}}',
        '0:"Bonjour"',
        '0:" à tous\\n"',
        'd:{"finishReason":"stop"}',
    ]

    result = parse_stream(lines, Wire.V4)

    assert result.text == "Bonjour à tous\n"
    assert result.tool_calls == [{"name": "summarize", "args": {"instructions": "en 3 points"}}]
    assert not result.errors


def test_parse_v4_collects_errors():
    """An error part is reported even when no text was produced."""
    result = parse_stream(['3:"Albert RAG request failed"'], Wire.V4)

    assert result.text == ""
    assert result.errors == ["Albert RAG request failed"]


def test_parse_v4_ignores_keepalive_and_unknown():
    """Keep-alive data parts, blank lines and unknown codes do not affect the result."""
    lines = ['2:[{"status":"WAITING"}]', "", 'h:{"url":"x"}', '0:"ok"']

    result = parse_stream(lines, Wire.V4)

    assert result.text == "ok"
    assert not result.tool_calls
    assert not result.errors


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}"


def test_parse_v5_text_and_tool_calls():
    """text-delta events are concatenated; tool-input-available gives name and input."""
    lines = [
        _sse({"type": "start", "messageId": "m1"}),
        "",
        _sse(
            {
                "type": "tool-input-available",
                "toolCallId": "c1",
                "toolName": "document_search_rag",
                "input": {"query": "budget"},
            }
        ),
        "",
        _sse({"type": "text-delta", "id": "t1", "delta": "Bonjour"}),
        "",
        _sse({"type": "text-delta", "id": "t1", "delta": " à tous"}),
        "",
        "data: [DONE]",
        "",
    ]

    result = parse_stream(lines, Wire.V5)

    assert result.text == "Bonjour à tous"
    assert result.tool_calls == [{"name": "document_search_rag", "args": {"query": "budget"}}]
    assert not result.errors


def test_parse_v5_collects_errors():
    """An error event is reported even when no text was produced."""
    result = parse_stream([_sse({"type": "error", "errorText": "model unavailable"})], Wire.V5)

    assert result.text == ""
    assert result.errors == ["model unavailable"]


def test_parse_v5_ignores_done_and_unknown():
    """Keep-alive data parts, [DONE] and non-data lines do not affect the result."""
    lines = [
        _sse({"type": "data-keepalive", "data": {"status": "WAITING"}}),
        ": comment",
        "data: [DONE]",
        _sse({"type": "text-delta", "id": "t1", "delta": "ok"}),
    ]

    result = parse_stream(lines, Wire.V5)

    assert result.text == "ok"
    assert not result.tool_calls
    assert not result.errors


def test_v4_assistant_message():
    """v4 assistant turns carry text in content and parts."""
    message = build_assistant_message(Wire.V4, "Réponse")

    assert message["role"] == "assistant"
    assert message["content"] == "Réponse"
    assert message["parts"] == [{"type": "text", "text": "Réponse"}]
    assert message["id"]


def test_v5_assistant_message():
    """v5 assistant turns carry text in parts only."""
    message = build_assistant_message(Wire.V5, "Réponse")

    assert message["role"] == "assistant"
    assert "content" not in message
    assert message["parts"] == [{"type": "text", "text": "Réponse"}]


def test_parse_v4_collects_sources_and_tool_results():
    """h: parts are streamed sources; a: parts are tool results."""
    lines = [
        'h:{"sourceType":"url","id":"s1","url":"https://a.fr"}',
        'a:{"toolCallId":"c1","result":"Résultat https://b.fr"}',
        'a:{"toolCallId":"c2","result":{"state":"done"}}',
        '0:"ok"',
    ]

    result = parse_stream(lines, Wire.V4)

    assert result.sources == ["https://a.fr"]
    assert result.tool_outputs == ["Résultat https://b.fr", '{"state": "done"}']


def test_parse_v5_collects_sources_and_tool_outputs():
    """source-url events are streamed sources; tool-output-available carries tool results."""
    lines = [
        _sse({"type": "source-url", "sourceId": "s1", "url": "https://a.fr"}),
        _sse({"type": "tool-output-available", "toolCallId": "c1", "output": "texte"}),
        _sse({"type": "text-delta", "id": "t1", "delta": "ok"}),
    ]

    result = parse_stream(lines, Wire.V5)

    assert result.sources == ["https://a.fr"]
    assert result.tool_outputs == ["texte"]


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.0.21", False),
        ("v0.0.22", True),
        ("v0.1.0", True),
        ("v0.0.21-rc1", False),
        ("v0.0.22-rc1", True),
        ("HEAD", True),
        ("main", True),
    ],
)
def test_tag_at_least(tag, expected):
    """Release tags (pre-releases included) compare numerically; HEAD and main are current."""
    assert tag_at_least(tag, (0, 0, 22)) is expected


@pytest.mark.parametrize("ref", ["3f0b4e99", "feature/x"])
def test_tag_at_least_rejects_unknown_refs(ref):
    """A SHA or branch has no known release: guessing would pick the wrong wire format."""
    with pytest.raises(ValueError, match=ref):
        tag_at_least(ref, (0, 0, 22))
