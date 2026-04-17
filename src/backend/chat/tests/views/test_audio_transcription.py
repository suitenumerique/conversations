"""Tests for the audio transcription view."""

from io import BytesIO

import pytest
import responses

from core.factories import UserFactory

pytestmark = pytest.mark.django_db

AUDIO_BYTES = b"RIFF....WAVEfmt "


@responses.activate
def test_audio_transcription_success(api_client, settings):
    """Test successful audio transcription returns stripped text."""
    settings.AUDIO_TRANSCRIPTION_BACKEND = "chat.input.albert_audio_backend.AlbertAudioBackend"
    settings.ALBERT_API_URL = "https://albert.example.com"
    settings.ALBERT_API_KEY = "test-key"
    settings.ALBERT_API_TIMEOUT = 10
    settings.ALBERT_API_ASR_MODEL = "openweight-audio"

    responses.add(
        responses.POST,
        "https://albert.example.com/v1/audio/transcriptions",
        json={"text": "  hello world"},
        status=200,
    )

    user = UserFactory()
    api_client.force_login(user)
    response = api_client.post(
        "/api/v1.0/transcribe/",
        {"audio": BytesIO(AUDIO_BYTES)},
        format="multipart",
    )

    assert response.status_code == 200
    assert response.json() == {"text": "hello world"}


def test_audio_transcription_anonymous(api_client, settings):
    """Anonymous users cannot access the transcription endpoint."""
    settings.AUDIO_TRANSCRIPTION_BACKEND = "chat.input.albert_audio_backend.AlbertAudioBackend"

    response = api_client.post(
        "/api/v1.0/transcribe/",
        {"audio": BytesIO(AUDIO_BYTES)},
        format="multipart",
    )

    assert response.status_code == 401


def test_audio_transcription_backend_disabled(api_client, settings):
    """Returns 501 when no transcription backend is configured."""
    settings.AUDIO_TRANSCRIPTION_BACKEND = None

    user = UserFactory()
    api_client.force_login(user)
    response = api_client.post(
        "/api/v1.0/transcribe/",
        {"audio": BytesIO(AUDIO_BYTES)},
        format="multipart",
    )

    assert response.status_code == 501


def test_audio_transcription_no_file(api_client, settings):
    """Returns 400 when no audio file is provided."""
    settings.AUDIO_TRANSCRIPTION_BACKEND = "chat.input.albert_audio_backend.AlbertAudioBackend"
    settings.ALBERT_API_URL = "https://albert.example.com"
    settings.ALBERT_API_KEY = "test-key"
    settings.ALBERT_API_TIMEOUT = 10
    settings.ALBERT_API_ASR_MODEL = "openweight-audio"

    user = UserFactory()
    api_client.force_login(user)
    response = api_client.post("/api/v1.0/transcribe/", {}, format="multipart")

    assert response.status_code == 400


@responses.activate
def test_audio_transcription_backend_error(api_client, settings):
    """Returns 502 when the transcription backend fails."""
    settings.AUDIO_TRANSCRIPTION_BACKEND = "chat.input.albert_audio_backend.AlbertAudioBackend"
    settings.ALBERT_API_URL = "https://albert.example.com"
    settings.ALBERT_API_KEY = "test-key"
    settings.ALBERT_API_TIMEOUT = 10
    settings.ALBERT_API_ASR_MODEL = "openweight-audio"

    responses.add(
        responses.POST,
        "https://albert.example.com/v1/audio/transcriptions",
        status=500,
    )

    user = UserFactory()
    api_client.force_login(user)
    response = api_client.post(
        "/api/v1.0/transcribe/",
        {"audio": BytesIO(AUDIO_BYTES)},
        format="multipart",
    )

    assert response.status_code == 502
