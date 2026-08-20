"""Golden tests for the v4 -> v5 stream translation.

These assert the exact SSE bytes the frontend receives: they are the contract
with the Vercel AI SDK's ``processUIMessageStream``.
"""

import pytest

from chat.vercel_ai_sdk.core import events_v4, events_v5
from chat.vercel_ai_sdk.encoder.encoder import DONE_FRAME, EventEncoder, EventEncoderVersion
from chat.vercel_ai_sdk.encoder.v4_to_v5 import V4ToV5Translator, data_part_type


def encode_stream(events, message_id="trace-abc"):
    """Run v4 events through the translator and return the full SSE stream."""
    encoder = EventEncoder(EventEncoderVersion.V5)
    translator = V4ToV5Translator()
    chunks = [encoder.encode(events_v5.MessageStartEvent(messageId=message_id))]
    for event in events:
        chunks += [encoder.encode(translated) for translated in translator.translate(event)]
    chunks += [encoder.encode(translated) for translated in translator.flush()]
    chunks.append(DONE_FRAME)
    return "".join(chunks)


def frames(stream):
    """Split an SSE stream into its ``data:`` payloads."""
    return [frame[len("data: ") :] for frame in stream.split("\n\n") if frame]


def test_translates_a_full_turn():
    """A complete text turn translates to the exact expected SSE stream."""
    stream = encode_stream(
        [
            events_v4.TextPart(text="Hello"),
            events_v4.TextPart(text=" there"),
            events_v4.StartStepPart(message_id="trace-abc"),
            events_v4.MessageAnnotationPart(annotations=[{"co2_impact": 0.5}]),
            events_v4.FinishMessagePart(
                finish_reason=events_v4.FinishReason.STOP,
                usage=events_v4.Usage(prompt_tokens=10, completion_tokens=3, co2_impact=0.5),
            ),
        ]
    )

    assert stream == (
        'data: {"type":"start","messageId":"trace-abc"}\n\n'
        'data: {"type":"text-start","id":"0"}\n\n'
        'data: {"type":"text-delta","id":"0","delta":"Hello"}\n\n'
        'data: {"type":"text-delta","id":"0","delta":" there"}\n\n'
        'data: {"type":"text-end","id":"0"}\n\n'
        'data: {"type":"start-step"}\n\n'
        'data: {"type":"finish","messageMetadata":'
        '{"usage":{"promptTokens":10,"completionTokens":3,"co2Impact":0.5},"co2_impact":0.5}}\n\n'
        "data: [DONE]\n\n"
    )


def test_translates_a_tool_call_turn():
    """Streamed tool input, result and sources map to their v5 counterparts."""
    stream = encode_stream(
        [
            events_v4.ToolCallStreamingStartPart(tool_call_id="c1", tool_name="document_search"),
            events_v4.ToolCallDeltaPart(tool_call_id="c1", args_text_delta='{"q":'),
            events_v4.ToolCallPart(tool_call_id="c1", tool_name="document_search", args={"q": "x"}),
            events_v4.SourcePart(id="s1", url="https://example.test", title="Example"),
            events_v4.ToolResultPart(tool_call_id="c1", result={"state": "done"}),
        ]
    )

    assert frames(stream) == [
        '{"type":"start","messageId":"trace-abc"}',
        '{"type":"tool-input-start","toolCallId":"c1","toolName":"document_search"}',
        '{"type":"tool-input-delta","toolCallId":"c1","inputTextDelta":"{\\"q\\":"}',
        '{"type":"tool-input-available","toolCallId":"c1","toolName":"document_search",'
        '"input":{"q":"x"}}',
        '{"type":"source-url","sourceId":"s1","url":"https://example.test","title":"Example"}',
        '{"type":"tool-output-available","toolCallId":"c1","output":{"state":"done"}}',
        "[DONE]",
    ]


def test_text_and_reasoning_blocks_are_opened_and_closed():
    """Switching between text and reasoning closes the previous block."""
    stream = encode_stream(
        [
            events_v4.ReasoningPart(reasoning="thinking"),
            events_v4.TextPart(text="answer"),
            events_v4.ReasoningPart(reasoning="more"),
        ]
    )

    assert frames(stream) == [
        '{"type":"start","messageId":"trace-abc"}',
        '{"type":"reasoning-start","id":"0"}',
        '{"type":"reasoning-delta","id":"0","delta":"thinking"}',
        '{"type":"reasoning-end","id":"0"}',
        '{"type":"text-start","id":"1"}',
        '{"type":"text-delta","id":"1","delta":"answer"}',
        '{"type":"text-end","id":"1"}',
        '{"type":"reasoning-start","id":"2"}',
        '{"type":"reasoning-delta","id":"2","delta":"more"}',
        '{"type":"reasoning-end","id":"2"}',
        "[DONE]",
    ]


def test_data_parts_are_named_and_transient():
    """Each data item becomes its own named, transient part."""
    stream = encode_stream(
        [
            events_v4.DataPart(
                data=[
                    {"type": "cooldown", "seconds": 12},
                    {
                        "type": "conversation_metadata",
                        "conversationId": "c-1",
                        "title": "A title",
                    },
                ]
            ),
            events_v4.DataPart(data=[{"type": "keep_alive"}]),
        ]
    )

    assert frames(stream)[1:] == [
        '{"type":"data-cooldown","data":{"type":"cooldown","seconds":12},"transient":true}',
        '{"type":"data-conversation-metadata","data":{"type":"conversation_metadata",'
        '"conversationId":"c-1","title":"A title"},"transient":true}',
        '{"type":"data-keep-alive","data":{"type":"keep_alive"},"transient":true}',
        "[DONE]",
    ]


def test_error_part_keeps_the_error_code():
    """The frontend keys its error handling on the code, so it must survive."""
    stream = encode_stream([events_v4.TextPart(text="oops"), events_v4.ErrorPart(error="llm_429")])

    assert frames(stream)[-2:] == ['{"type":"error","errorText":"llm_429"}', "[DONE]"]
    # The dangling text block is closed before the error.
    assert '{"type":"text-end","id":"0"}' in frames(stream)


def test_flush_closes_a_dangling_block():
    """A stream cut short after text still closes its block."""
    translator = V4ToV5Translator()
    translator.translate(events_v4.TextPart(text="partial"))

    assert [event.type for event in translator.flush()] == [events_v5.EventType.TEXT_END]
    assert not translator.flush()


def test_data_item_without_a_type_is_dropped():
    """An unnamed data item cannot be routed by the client, so it is not emitted."""
    translator = V4ToV5Translator()

    assert translator.translate(events_v4.DataPart(data=[{"status": "WAITING"}])) == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("cooldown", "data-cooldown"),
        ("keep_alive", "data-keep-alive"),
        ("images_skipped", "data-images-skipped"),
    ],
)
def test_data_part_type_is_kebab_cased(name, expected):
    """Data part names are kebab-cased on the wire."""
    assert data_part_type(name) == expected
