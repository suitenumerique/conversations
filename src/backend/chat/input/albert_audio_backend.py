"""Albert API implementation for audio transcription."""

import logging
from urllib.parse import urljoin

from django.conf import settings

import requests

from chat.exceptions import TranscriptionError
from chat.input.base_audio_backend import BaseAudioBackend

logger = logging.getLogger(__name__)


class AlbertAudioBackend(BaseAudioBackend):
    """
    Audio transcription backend using the Albert API.

    Sends audio files to the Albert ASR endpoint and returns the transcribed text.
    Requires ALBERT_API_URL and ALBERT_API_KEY to be configured in settings.
    """

    def __init__(self):
        self._transcriptions_endpoint = urljoin(settings.ALBERT_API_URL, "/v1/audio/transcriptions")
        self._headers = {"Authorization": f"Bearer {settings.ALBERT_API_KEY}"}

    def transcribe(self, file_name: str, file_content: bytes, content_type: str) -> str:
        """
        Transcribe the given audio file using the Albert ASR API.

        Args:
            file_name (str): The original file name of the audio file.
            file_content (bytes): The raw audio file content.
            content_type (str): The MIME type of the audio file.
            language (str): The language to transcribe the audio content in.

        Returns:
            str: The transcribed text.

        Raises:
            TranscriptionError: If an error occurs during transcription.
        """
        try:
            response = requests.post(
                self._transcriptions_endpoint,
                headers=self._headers,
                files={"file": (file_name, file_content, content_type)},
                # whisper on vLLM does not support language detection yet,
                # so we need to pass the language parameter to Albert API.
                # TODO: Allow passing 'auto' when whisper on vLLM supports language detection,
                #       or when Albert API migrates to whisperx.
                data={
                    "model": settings.ALBERT_API_ASR_MODEL,
                    "language": settings.ALBERT_API_ASR_LANGUAGE,
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            response.raise_for_status()
            return response.json().get("text", "").strip()
        except requests.RequestException as e:
            raise TranscriptionError(f"Error during transcription: {e}") from e
