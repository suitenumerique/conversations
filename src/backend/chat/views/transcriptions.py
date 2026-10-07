"""Voice prompt transcription view."""

import logging
import math
import time

from django.conf import settings
from django.http import Http404, JsonResponse
from django.views import View

from asgiref.sync import sync_to_async
from openai import APIError, AsyncOpenAI

from chat.rate_limiting import TranscriptionDailyThrottle, TranscriptionHourlyThrottle

logger = logging.getLogger(__name__)

ACCEPTED_AUDIO_TYPES = frozenset({"audio/webm", "audio/mp4", "audio/wav", "audio/mpeg"})
THROTTLE_CLASSES = (TranscriptionHourlyThrottle, TranscriptionDailyThrottle)


def _transcription_language(user) -> str:
    """ISO-639-1 code of the user's interface language, e.g. 'fr-fr' -> 'fr'.

    Always sent: the Whisper served by vLLM on Albert cannot detect the language.
    """
    return (user.language or settings.LANGUAGE_CODE).split("-")[0]


def _throttle_wait(request) -> float | None:
    """Seconds to wait if any transcription throttle refuses the request, else None."""
    waits = []
    for throttle_class in THROTTLE_CLASSES:
        throttle = throttle_class()
        if not throttle.allow_request(request, None):
            waits.append(throttle.wait())
    return max(waits) if waits else None


def _error(detail: str, status: int) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


def _upload_error(audio) -> JsonResponse | None:
    """Error response if the uploaded recording cannot be transcribed, else None."""
    if audio is None:
        return _error("No recording provided.", 400)
    if audio.content_type not in ACCEPTED_AUDIO_TYPES:
        return _error("Unsupported recording format.", 415)
    if audio.size > settings.VOICE_PROMPT_MAX_SIZE:
        return _error("Recording too large.", 413)
    return None


class TranscriptionView(View):
    """Turn a Voice prompt recording into a Transcript; the recording is never stored.

    A native async view rather than a DRF one: under uvicorn every sync view of a
    worker shares one thread, so waiting seconds on the speech-recognition model
    in a sync view would stall every other request of that worker.
    """

    http_method_names = ["post"]

    async def post(self, request):
        """Transcribe the uploaded `audio` file."""
        if not settings.TRANSCRIPTION_HRID:
            raise Http404

        user = await request.auser()
        if not user.is_authenticated:
            return _error("Authentication credentials were not provided.", 401)
        # DRF throttles key on request.user; give them the resolved user.
        request.user = user

        wait = await sync_to_async(_throttle_wait)(request)
        if wait is not None:
            response = _error("Request was throttled.", 429)
            response["Retry-After"] = str(math.ceil(wait))
            return response

        audio = request.FILES.get("audio")
        if error := _upload_error(audio):
            return error

        model = settings.LLM_CONFIGURATIONS[settings.TRANSCRIPTION_HRID]
        started_at = time.monotonic()
        try:
            async with AsyncOpenAI(
                base_url=model.provider.base_url,
                api_key=model.provider.api_key,
                timeout=settings.TRANSCRIPTION_TIMEOUT,
                max_retries=0,
            ) as client:
                transcription = await client.audio.transcriptions.create(
                    model=model.model_name,
                    file=(audio.name, audio.read(), audio.content_type),
                    language=_transcription_language(user),
                )
        except APIError as error:
            logger.warning(
                "Voice prompt transcription failed: %s (size=%d, type=%s, latency=%.2fs)",
                type(error).__name__,
                audio.size,
                audio.content_type,
                time.monotonic() - started_at,
            )
            return _error("Transcription failed.", 502)

        logger.info(
            "Voice prompt transcribed (size=%d, type=%s, latency=%.2fs)",
            audio.size,
            audio.content_type,
            time.monotonic() - started_at,
        )
        return JsonResponse({"text": transcription.text.strip()})
