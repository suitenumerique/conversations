"""Voice prompt transcription view."""

import logging
import math
import time

from django.conf import settings
from django.http import Http404, JsonResponse
from django.views import View

from asgiref.sync import sync_to_async
from openai import APIError, AsyncOpenAI

from core.feature_flags.helpers import is_feature_enabled

from chat.rate_limiting import VoicePromptDailyThrottle, VoicePromptHourlyThrottle

logger = logging.getLogger(__name__)

# Accepted recording types and the extension providers need to detect the format.
AUDIO_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
}
THROTTLE_CLASSES = (VoicePromptHourlyThrottle, VoicePromptDailyThrottle)


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


def _rejection(detail: str, status: int) -> JsonResponse:
    """Refuse the request before it reaches the provider, logging the outcome."""
    logger.info("Voice prompt rejected: %s (status=%d)", detail, status)
    return JsonResponse({"detail": detail}, status=status)


def _upload_error(audio) -> JsonResponse | None:
    """Error response if the uploaded recording cannot be transcribed, else None."""
    if audio is None:
        return _rejection("No recording provided.", 400)
    if audio.content_type not in AUDIO_EXTENSIONS:
        return _rejection("Unsupported recording format.", 415)
    if audio.size > settings.VOICE_PROMPT_MAX_SIZE:
        return _rejection("Recording too large.", 413)
    return None


class VoicePromptTranscriptionView(View):
    """Turn a Voice prompt recording into a Transcript; the recording is never stored.

    A native async view rather than a DRF one: under uvicorn every sync view of a
    worker shares one thread, so waiting seconds on the speech-recognition model
    in a sync view would stall every other request of that worker.

    Being a plain Django view, it authenticates with the session cookie only (no
    OIDC bearer token) and keeps Django's CSRF protection: only the web frontend
    calls it.
    """

    http_method_names = ["post"]

    async def post(self, request):
        """Transcribe the uploaded `audio` file."""
        if not settings.VOICE_PROMPT_TRANSCRIPTION_HRID:
            raise Http404

        user = await request.auser()
        if not user.is_authenticated:
            return _rejection("Authentication credentials were not provided.", 401)
        # The flag decides who may dictate; when dynamic it asks PostHog over the
        # network, so it runs off the event loop.
        if not await sync_to_async(is_feature_enabled)(user, "voice_prompt"):
            raise Http404
        # DRF throttles key on request.user; give them the resolved user.
        request.user = user

        # Checked before the throttles so that a rejected upload costs no quota.
        audio = request.FILES.get("audio")
        if error := _upload_error(audio):
            return error

        wait = await sync_to_async(_throttle_wait)(request)
        if wait is not None:
            response = _rejection("Request was throttled.", 429)
            response["Retry-After"] = str(math.ceil(wait))
            return response

        model = settings.LLM_CONFIGURATIONS[settings.VOICE_PROMPT_TRANSCRIPTION_HRID]
        started_at = time.monotonic()
        try:
            async with AsyncOpenAI(
                base_url=model.provider.base_url,
                api_key=model.provider.api_key,
                timeout=settings.VOICE_PROMPT_TRANSCRIPTION_TIMEOUT,
                max_retries=0,
            ) as client:
                transcription = await client.audio.transcriptions.create(
                    model=model.model_name,
                    file=(
                        f"voice-prompt.{AUDIO_EXTENSIONS[audio.content_type]}",
                        audio.read(),
                        audio.content_type,
                    ),
                    language=_transcription_language(user),
                )
            if not isinstance(transcription.text, str):
                raise ValueError("No transcript in the provider response.")
        # ValueError also covers a response body that is not valid JSON.
        except (APIError, ValueError) as error:
            logger.warning(
                "Voice prompt transcription failed: %s (size=%d, type=%s, latency=%.2fs)",
                type(error).__name__,
                audio.size,
                audio.content_type,
                time.monotonic() - started_at,
            )
            return JsonResponse({"detail": "Transcription failed."}, status=502)

        logger.info(
            "Voice prompt transcribed (size=%d, type=%s, latency=%.2fs)",
            audio.size,
            audio.content_type,
            time.monotonic() - started_at,
        )
        return JsonResponse({"text": transcription.text.strip()})
