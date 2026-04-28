"""Audio transcription helpers for chat attachments."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import default_storage

import requests
from asgiref.sync import sync_to_async

from core.file_upload.enums import AttachmentStatus
from core.file_upload.utils import generate_retrieve_policy

from chat.models import ChatConversationAttachment
from chat.webhook_models import WhisperXResponse

logger = logging.getLogger(__name__)


def parse_whisper_response(whisper_data: WhisperXResponse) -> str:
    """Convert WhisperX segments into a markdown transcript string."""
    out_str = "# Transcription \n"
    last_speaker = None
    for chunk in whisper_data.segments:
        speaker = chunk.speaker or "Unknown"
        if speaker != last_speaker:
            out_str += f"\n## {speaker}\n"
            last_speaker = speaker
        out_str += f"{chunk.text}\n"
    return out_str


def trigger_audio_transcription(attachment: ChatConversationAttachment) -> None:
    """
    Trigger async transcription for an audio attachment.

    Posts to the transcription service, stores the returned job_id on the
    attachment, and sets its status to TRANSCRIBING.

    Args:
        attachment: ChatConversationAttachment instance with an audio content_type.

    Raises:
        requests.HTTPError: If the transcription service returns an error.
    """
    if not settings.STT_SERVICE_URL:
        raise ImproperlyConfigured("STT_SERVICE_URL must be configured to use audio transcription.")

    presigned_url = generate_retrieve_policy(attachment.key)

    response = requests.post(
        urljoin(settings.STT_SERVICE_URL, "async-jobs/transcribe"),
        json={
            "user_sub": str(attachment.uploaded_by.sub),
            "language": "fr",
            "cloud_storage_url": presigned_url,
        },
        headers={
            "Authorization": f"Bearer {settings.STT_SERVICE_API_KEY}",
        },
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    attachment.transcription_job_id = data["job_id"]
    attachment.upload_state = AttachmentStatus.TRANSCRIBING
    attachment.save(update_fields=["transcription_job_id", "upload_state", "updated_at"])

    logger.info("Transcription job %s created for attachment %s", data["job_id"], attachment.pk)


async def wait_for_transcript(attachment_key: str, conversation) -> str:
    """
    Wait for an audio transcript to be ready and return the transcript text.

    Polls the DB every 2 seconds until the attachment reaches a terminal_states state.

    Args:
        attachment_key: The S3 key of the audio attachment.
        conversation: The ChatConversation instance the attachment belongs to.

    Returns:
        The transcript text.

    Raises:
        ValueError: If transcription times out or fails.
    """
    poll_interval = 2.0
    timeout = 1200.0
    terminal_states = {
        AttachmentStatus.READY,
        AttachmentStatus.SUSPICIOUS,
        AttachmentStatus.FILE_TOO_LARGE_TO_ANALYZE,
        AttachmentStatus.TRANSCRIPTION_FAILED,
    }

    attachment = await ChatConversationAttachment.objects.aget(
        key=attachment_key,
        conversation=conversation,
    )
    elapsed = 0.0
    while attachment.upload_state not in terminal_states:
        if elapsed >= timeout:
            raise ValueError("The audio transcription took too long. Please try again.")
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        attachment = await ChatConversationAttachment.objects.aget(
            key=attachment_key,
            conversation=conversation,
        )

    if attachment.upload_state != AttachmentStatus.READY:
        raise ValueError(
            "The transcription of this audio failed. Please try again with another file."
        )

    text_attachment = await ChatConversationAttachment.objects.aget(
        conversation=conversation,
        conversion_from=attachment_key,
    )

    @sync_to_async
    def read_transcript():
        with default_storage.open(text_attachment.key) as f:
            return f.read().decode("utf-8")

    return await read_transcript()
