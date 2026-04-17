"""Tests for the Albert audio transcription backend."""

import pytest
import responses

from chat.exceptions import TranscriptionError
from chat.input.albert_audio_backend import AlbertAudioBackend


@pytest.fixture(name="backend")
def backend_fixture(settings):
    """Fixture providing a configured AlbertAudioBackend instance."""
    settings.ALBERT_API_URL = "https://albert.example.com"
    settings.ALBERT_API_KEY = "test-key"
    settings.ALBERT_API_TIMEOUT = 10
    settings.ALBERT_API_ASR_MODEL = "openweight-audio"
    return AlbertAudioBackend()


@responses.activate
def test_transcribe_strips_whitespace(backend):
    """Transcription result has surrounding whitespace stripped."""
    responses.add(
        responses.POST,
        "https://albert.example.com/v1/audio/transcriptions",
        json={"text": "  bonjour monde  "},
        status=200,
    )

    result = backend.transcribe("audio.webm", b"data", "audio/webm")

    assert result == "bonjour monde"


@responses.activate
def test_transcribe_raises_transcription_error_on_http_failure(backend):
    """An HTTP error from the Albert API raises TranscriptionError."""
    responses.add(
        responses.POST,
        "https://albert.example.com/v1/audio/transcriptions",
        status=503,
    )

    with pytest.raises(TranscriptionError):
        backend.transcribe("audio.webm", b"data", "audio/webm")


@responses.activate
def test_transcribe_sends_correct_request(backend):
    """The backend sends the file and required fields to the Albert API."""
    responses.add(
        responses.POST,
        "https://albert.example.com/v1/audio/transcriptions",
        json={"text": "test"},
        status=200,
    )

    backend.transcribe("recording.webm", b"audio-content", "audio/webm")

    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert "Bearer test-key" in request.headers["Authorization"]
    assert b"audio-content" in request.body
