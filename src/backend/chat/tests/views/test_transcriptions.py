"""Tests for the voice prompt transcription endpoint."""

import logging

from django.core.files.uploadedfile import SimpleUploadedFile

import httpx
import pytest
import respx
from openai import AsyncOpenAI
from respx.mocks import HTTPCoreMocker, Mocker
from rest_framework import status

from core.factories import UserFactory

from chat.llm_configuration import LLModel, LLMProvider
from chat.tests.utils import throttle_rates

# transaction=True: the async view resolves the user outside the test's thread.
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("clear_cache")]

URL = "/api/v1.0/transcriptions/"
ALBERT_URL = "https://albert.example.com/v1/audio/transcriptions"


# respx only patches httpcore; the OpenAI SDK's httpx2 client runs on httpcore2.
# Subclassing a Mocker registers it under its name, which pytest-httpx2 already
# does when it is installed.
if "httpcore2" not in Mocker.registry:

    class HTTPCore2Mocker(HTTPCoreMocker):
        """Let respx mock the OpenAI SDK's transport."""

        name = "httpcore2"
        targets = [
            "httpcore2._async.connection.AsyncHTTPConnection",
            "httpcore2._async.connection_pool.AsyncConnectionPool",
            "httpcore2._async.http_proxy.AsyncHTTPProxy",
        ]


@pytest.fixture(name="albert")
def albert_fixture():
    """Mock the Albert API; requests to any other host fail the test."""
    with respx.mock(using="httpcore2") as router:
        yield router


@pytest.fixture(name="transcription_enabled")
def transcription_enabled_fixture(settings):
    """Point TRANSCRIPTION_HRID at a speech-recognition model entry."""
    settings.TRANSCRIPTION_HRID = "speech-model"
    settings.LLM_CONFIGURATIONS = {
        "speech-model": LLModel(
            hrid="speech-model",
            model_name="openweight-audio",
            human_readable_name="Speech recognition",
            is_active=True,
            system_prompt="",
            tools=[],
            provider=LLMProvider(
                hrid="albert",
                base_url="https://albert.example.com/v1/",
                api_key="test-key",
            ),
        ),
    }


def _voice_prompt(content_type="audio/webm", size=16):
    """Build a fake recording upload."""
    return SimpleUploadedFile("voice-prompt", b"x" * size, content_type=content_type)


def _post(api_client, **kwargs):
    return api_client.post(URL, {"audio": _voice_prompt(**kwargs)}, format="multipart")


def test_transcription_disabled_returns_404(api_client, settings):
    """Without TRANSCRIPTION_HRID the endpoint does not exist."""
    settings.TRANSCRIPTION_HRID = None
    api_client.force_login(UserFactory())

    assert _post(api_client).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_anonymous_returns_401(api_client):
    """Anonymous users cannot transcribe."""
    assert _post(api_client).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_returns_stripped_transcript(api_client, albert):
    """The Transcript comes back stripped, and the provider gets model, key and language."""
    route = albert.post(ALBERT_URL).mock(
        return_value=httpx.Response(200, json={"text": "  Résume ce document  "})
    )
    api_client.force_login(UserFactory(language="fr-fr"))

    response = _post(api_client)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"text": "Résume ce document"}
    upstream = route.calls.last.request
    assert upstream.headers["Authorization"] == "Bearer test-key"
    assert b'name="model"\r\n\r\nopenweight-audio\r\n' in upstream.content
    assert b'name="language"\r\n\r\nfr\r\n' in upstream.content


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_language_falls_back_to_language_code(api_client, albert, settings):
    """A user who never picked a language dictates in the instance language."""
    settings.LANGUAGE_CODE = "fr-fr"
    route = albert.post(ALBERT_URL).mock(return_value=httpx.Response(200, json={"text": "ok"}))
    api_client.force_login(UserFactory(language=None))

    assert _post(api_client).status_code == status.HTTP_200_OK
    assert b'name="language"\r\n\r\nfr\r\n' in route.calls.last.request.content


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_accepts_codec_parameter(api_client, albert):
    """Browsers label MediaRecorder output with its codec, e.g. audio/webm;codecs=opus."""
    albert.post(ALBERT_URL).mock(return_value=httpx.Response(200, json={"text": "ok"}))
    api_client.force_login(UserFactory())

    response = _post(api_client, content_type="audio/webm;codecs=opus")

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_missing_file_returns_400(api_client):
    """A request without a recording is rejected."""
    api_client.force_login(UserFactory())

    response = api_client.post(URL, {}, format="multipart")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_unsupported_type_returns_415(api_client):
    """Only the audio types the recorder produces are accepted."""
    api_client.force_login(UserFactory())

    response = _post(api_client, content_type="video/mp4")

    assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_too_large_returns_413(api_client, settings):
    """Recordings above VOICE_PROMPT_MAX_SIZE are rejected before reaching the provider."""
    settings.VOICE_PROMPT_MAX_SIZE = 8
    api_client.force_login(UserFactory())

    response = _post(api_client, size=16)

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_of_silence_returns_empty_text(api_client, albert):
    """Nothing recognized is a success with an empty Transcript."""
    albert.post(ALBERT_URL).mock(return_value=httpx.Response(200, json={"text": "   "}))
    api_client.force_login(UserFactory())

    response = _post(api_client)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"text": ""}


@pytest.mark.parametrize(
    "upstream",
    [httpx.Response(500), httpx.Response(413), httpx.ConnectTimeout("timed out")],
)
@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_upstream_failure_returns_502(api_client, albert, upstream):
    """Provider errors and timeouts surface as a bad gateway."""
    route = albert.post(ALBERT_URL)
    if isinstance(upstream, Exception):
        route.mock(side_effect=upstream)
    else:
        route.mock(return_value=upstream)
    api_client.force_login(UserFactory())

    response = _post(api_client)

    assert response.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.parametrize("scope", ["transcription_hourly", "transcription_daily"])
@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_is_throttled_per_user(api_client, albert, scope):
    """Once a user's budget is spent, further transcriptions get a 429 with Retry-After."""
    albert.post(ALBERT_URL).mock(return_value=httpx.Response(200, json={"text": "ok"}))
    api_client.force_login(UserFactory())

    with throttle_rates(**{scope: "1/day"}):
        assert _post(api_client).status_code == status.HTTP_200_OK
        response = _post(api_client)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert int(response["Retry-After"]) > 0


@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_never_logs_the_transcript(api_client, albert, caplog):
    """The Transcript is personal content: it must never reach the logs."""
    albert.post(ALBERT_URL).mock(
        return_value=httpx.Response(200, json={"text": "mon numéro fiscal secret"})
    )
    api_client.force_login(UserFactory())

    with caplog.at_level(logging.DEBUG):
        assert _post(api_client).status_code == status.HTTP_200_OK

    assert "secret" not in caplog.text


@pytest.mark.parametrize(
    "upstream", [httpx.Response(200, json={"text": "ok"}), httpx.Response(500)]
)
@pytest.mark.usefixtures("transcription_enabled")
def test_transcription_closes_its_provider_client(api_client, albert, monkeypatch, upstream):
    """Each request releases the provider connections it opened, success or not."""
    albert.post(ALBERT_URL).mock(return_value=upstream)
    closed = []
    original_close = AsyncOpenAI.close

    async def close(client):
        closed.append(client)
        await original_close(client)

    monkeypatch.setattr(AsyncOpenAI, "close", close)
    api_client.force_login(UserFactory())

    _post(api_client)

    assert len(closed) == 1
