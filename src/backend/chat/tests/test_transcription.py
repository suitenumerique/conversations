"""Tests for audio transcription triggering."""

from unittest.mock import patch
from urllib.parse import urljoin

from django.conf import settings

import pytest
import requests
import responses as responses_lib

from core.file_upload.enums import AttachmentStatus

from chat.factories import ChatConversationAttachmentFactory
from chat.transcription import trigger_audio_transcription

pytestmark = pytest.mark.django_db


@pytest.fixture(name="audio_attachment")
def fixture_audio_attachment():
    """Create an audio attachment."""
    return ChatConversationAttachmentFactory(content_type="audio/mpeg")


@responses_lib.activate
@patch("chat.transcription.generate_retrieve_policy", return_value="https://presigned.test/audio")
def test_trigger_audio_transcription_sets_transcribing_status(_mock_policy, audio_attachment):
    """Transcription trigger sets attachment to TRANSCRIBING and stores job_id."""
    responses_lib.add(
        responses_lib.POST,
        urljoin(settings.STT_SERVICE_URL, "async-jobs/transcribe"),
        json={"job_id": "test-job-123"},
        status=200,
    )
    trigger_audio_transcription(audio_attachment)

    audio_attachment.refresh_from_db()
    assert audio_attachment.upload_state == AttachmentStatus.TRANSCRIBING
    assert audio_attachment.transcription_job_id == "test-job-123"


@responses_lib.activate
@patch("chat.transcription.generate_retrieve_policy", return_value="https://presigned.test/audio")
def test_trigger_audio_transcription_failure_does_not_update(_mock_policy, audio_attachment):
    """If transcription service fails, attachment status is unchanged."""
    responses_lib.add(
        responses_lib.POST,
        urljoin(settings.STT_SERVICE_URL, "async-jobs/transcribe"),
        status=500,
    )
    with pytest.raises(requests.HTTPError):
        trigger_audio_transcription(audio_attachment)

    audio_attachment.refresh_from_db()
    assert audio_attachment.upload_state != AttachmentStatus.TRANSCRIBING
