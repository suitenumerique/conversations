"""Common test fixtures for chat conversation endpoint tests."""

import json

from django.utils import timezone

import httpx
import pytest
import respx
from freezegun import freeze_time


def build_openai_stream():
    """
    Constructs a string that simulates an OpenAI streaming response payload.
    
    The returned string contains three OpenAI-style `data:` blocks: a first chunk with content "Hello",
    a second chunk with content " there" and a `finish_reason` of "stop" (including a `usage` object),
    and a final `data: [DONE]` marker. Timestamp fields are generated from timezone.now() converted to
    naive timestamps.
    
    Returns:
        A string containing concatenated `data:` lines representing streaming chunks and a final `[DONE]` marker.
    """
    return (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": "Hello"},
                        "index": 0,
                        "finish_reason": None,
                    }
                ],
                "object": "chat.completion.chunk",
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": " there"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )


@pytest.fixture(name="mock_openai_stream")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_stream():
    """
    Fixture to mock the OpenAI stream response.

    See https://platform.openai.com/docs/api-reference/chat-streaming/streaming
    """
    openai_stream = build_openai_stream()

    async def mock_stream():
        """
        Yield each line of the prepared OpenAI-style streaming payload as encoded bytes.
        
        Yields:
            AsyncGenerator[bytes, None]: Sequential byte chunks for each line in the constructed stream, preserving original line endings.
        """
        for line in openai_stream.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, stream=mock_stream())
    )

    return route


@pytest.fixture(name="mock_openai_stream_with_title_generation")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_stream_with_title_generation():
    """
    Mock pytest fixture that intercepts POST requests to the external chat completions endpoint and returns either a streaming chat response or a non-streaming title-generation response depending on the incoming request.
    
    When the request JSON has "stream" set to True, the fixture returns an HTTP streaming response that imitates OpenAI's chat streaming payload; otherwise it returns a non-streaming JSON response containing a generated title and usage metadata.
    
    Returns:
        respx.Route: A configured respx route that intercepts POST requests to
        "https://www.external-ai-service.com/chat/completions" and replies based on the request body.
    """

    def create_stream_response():
        """
        Create an HTTP response whose body streams encoded lines of an OpenAI-style streaming payload.
        
        Returns:
            httpx.Response: HTTP 200 response with a streaming body that yields encoded bytes for each line of the streaming payload.
        """
        openai_stream = build_openai_stream()

        async def mock_stream():
            """
            Yield encoded byte chunks for each line of the OpenAI stream.
            
            Each yielded value is a bytes object containing one line (including its line ending) from the prebuilt OpenAI streaming payload, suitable for use as an HTTP streaming response body.
            """
            for line in openai_stream.splitlines(keepends=True):
                yield line.encode()

        return httpx.Response(200, stream=mock_stream())

    def create_non_stream_response():
        """
        Create a non-streaming OpenAI-like chat completion response containing a generated title.
        
        Returns:
            httpx.Response: HTTP 200 response whose JSON payload represents a chat completion with a single assistant message containing the generated title and accompanying metadata (id, model, timestamps, choices, and usage).
        """
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-title",
                "object": "chat.completion",
                "created": int(timezone.make_naive(timezone.now()).timestamp()),
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "GENERATED TITLE",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
            },
        )

    def handle_request(request):
        """
        Selects a streaming or non-streaming HTTP response based on the request JSON `stream` flag.
        
        Parameters:
            request (httpx.Request): Incoming request whose JSON body is inspected for the `stream` boolean flag.
        
        Returns:
            httpx.Response: A response that streams the OpenAI-style event lines if `stream` is True, otherwise a non-streaming JSON response.
        """
        body = json.loads(request.content)
        if body.get("stream", False):
            return create_stream_response()
        return create_non_stream_response()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        side_effect=handle_request
    )

    return route


@pytest.fixture(name="mock_openai_no_stream")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_no_stream():
    """
    Create a respx route that returns a fixed, non-streaming OpenAI chat completion response.
    
    The mocked response is an HTTP 200 JSON payload representing a completed assistant message (explaining Rayleigh scattering) with associated metadata and usage details.
    
    Returns:
        respx.Route: The configured respx route intercepting POST requests to https://www.external-ai-service.com/chat/completions.
    """

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-92c413bb5a45426299335d0621324654",
                "object": "chat.completion",
                "created": 1758550429,
                "model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": (
                                "The sky appears blue due to a "
                                "phenomenon called Rayleigh scattering."
                            ),
                            "refusal": None,
                            "annotations": None,
                            "audio": None,
                            "function_call": None,
                            "tool_calls": [],
                            "reasoning_content": None,
                        },
                        "logprobs": None,
                        "finish_reason": "stop",
                        "stop_reason": None,
                    }
                ],
                "service_tier": None,
                "system_fingerprint": None,
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 135,
                    "total_tokens": 135,
                    "cost": 0.0,
                    "carbon": {
                        "kWh": {"min": 0.0, "max": 0.0},
                        "kgCO2eq": {"min": 0.0, "max": 0.0},
                    },
                    "details": [
                        {
                            "id": "chatcmpl-92c413bb5a45426299335d0621324654",
                            "model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
                            "usage": {
                                "prompt_tokens": 0,
                                "completion_tokens": 135,
                                "total_tokens": 135,
                                "cost": 0.0,
                                "carbon": {
                                    "kWh": {"min": 0.0, "max": 0.0},
                                    "kgCO2eq": {"min": 0.0, "max": 0.0},
                                },
                            },
                        }
                    ],
                },
                "prompt_logprobs": None,
                "kv_transfer_params": None,
            },
        ),
    )

    return route


@pytest.fixture(name="mock_openai_stream_image")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_stream_image():
    """
    Mock a very simple OpenAI stream that *mentions* the image
    in its textual reply (the real test is that the image URL is
    forwarded in the request body to the AI service).
    """
    openai_stream = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": "I see a cat"},
                        "index": 0,
                        "finish_reason": None,
                    }
                ],
                "object": "chat.completion.chunk",
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-1234567890",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {
                        "delta": {"content": " in the picture."},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
                "object": "chat.completion.chunk",
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_stream():
        for line in openai_stream.splitlines(keepends=True):
            yield line.encode()

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        return_value=httpx.Response(200, stream=mock_stream())
    )
    return route


@pytest.fixture(name="mock_openai_stream_tool")
@freeze_time("2025-07-25T10:36:35.297675Z")
def fixture_mock_openai_stream_tool():
    """
    Mock both API calls in the tool call flow:
    1. First call returns function call
    2. Second call returns final answer after tool execution
    """

    # First response - tool call
    first_response = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-tool-call",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                                    "type": "function",
                                    "function": {
                                        "name": "get_current_weather",
                                        "arguments": "",
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-tool-call",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "xLDcIljdsDrz0idal7tATWSMm2jhMj47",
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": '{"location":"Paris", "unit":"celsius"}',
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-tool-call",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    # Second response - final answer
    second_response = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"role": "assistant"}, "index": 0}],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {"delta": {"content": "The current weather in Paris is nice"}, "index": 0}
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    # Second response - final answer when failing
    second_response_fail = (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"role": "assistant"}, "index": 0}],
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [
                    {"delta": {"content": "I cannot give you an answer to that."}, "index": 0}
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )
        + "\n\n"
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-final",
                "created": timezone.make_naive(timezone.now()).timestamp(),
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            }
        )
        + "\n\n"
        "data: [DONE]\n\n"
    )

    async def mock_first_response_stream():
        for line in first_response.splitlines(keepends=True):
            yield line.encode()

    async def mock_second_response_stream():
        for line in second_response.splitlines(keepends=True):
            yield line.encode()

    async def mock_second_response_failing_stream():
        for line in second_response_fail.splitlines(keepends=True):
            yield line.encode()

    def tool_answer_side_effect(request):
        if "Unknown tool name:" in request.content.decode():
            # Simulate the second response with tool call failure
            return httpx.Response(200, stream=mock_second_response_failing_stream())
        return httpx.Response(200, stream=mock_second_response_stream())

    route = respx.post("https://www.external-ai-service.com/chat/completions").mock(
        side_effect=[
            httpx.Response(200, stream=mock_first_response_stream()),
            tool_answer_side_effect,
        ]
    )

    return route