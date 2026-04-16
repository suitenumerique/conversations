"""Tests for the transcription webhook endpoint."""

import json
from unittest import mock

from django.core.files.storage import default_storage
from django.urls import reverse

import pytest
import responses as responses_lib

from core.file_upload.enums import AttachmentStatus

from chat import models
from chat.factories import ChatConversationAttachmentFactory

pytestmark = pytest.mark.django_db

AUTH_HEADER = {"HTTP_AUTHORIZATION": "Bearer test-webhook-key"}


WHISPER_TRANSCRIPT_DATA = {
    "segments": [
        {
            "start": 0.0,
            "end": 2.5,
            "text": "Hello world",
            "words": [],
            "speaker": "SPEAKER_00",
        },
        {
            "start": 2.5,
            "end": 5.0,
            "text": "How are you?",
            "words": [],
            "speaker": "SPEAKER_01",
        },
    ],
    "word_segments": [],
}


@pytest.fixture(name="transcribing_attachment")
def fixture_transcribing_attachment():
    """Create a TRANSCRIBING audio attachment with a known job_id."""
    return ChatConversationAttachmentFactory(
        content_type="audio/mpeg",
        upload_state=AttachmentStatus.TRANSCRIBING,
        transcription_job_id="job-abc-123",
    )


@responses_lib.activate
def test_transcription_webhook_success(client, transcribing_attachment):
    """Successful webhook creates a text/markdown S3 attachment and sets audio to READY."""
    transcript_url = "http://ai-service.test/transcripts/job-abc-123.json"
    responses_lib.add(
        responses_lib.GET,
        transcript_url,
        json=WHISPER_TRANSCRIPT_DATA,
        status=200,
    )

    payload = {
        "job_id": "job-abc-123",
        "type": "transcript",
        "status": "success",
        "transcription_data_url": transcript_url,
    }

    url = reverse("transcription-webhook")
    with mock.patch.object(default_storage, "save") as mock_save:
        response = client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **AUTH_HEADER,
        )

    assert response.status_code == 200
    transcribing_attachment.refresh_from_db()
    assert transcribing_attachment.upload_state == AttachmentStatus.READY

    # A text/markdown attachment should have been created
    text_attachment = models.ChatConversationAttachment.objects.get(
        conversion_from=transcribing_attachment.key
    )
    assert text_attachment.content_type == "text/markdown"
    assert text_attachment.upload_state == AttachmentStatus.READY

    # Transcript saved to S3 with correct content
    mock_save.assert_called_once()
    saved_content = mock_save.call_args[0][1].read().decode("utf-8")
    assert "# Transcription" in saved_content
    assert "SPEAKER_00" in saved_content
    assert "Hello world" in saved_content
    assert "SPEAKER_01" in saved_content


def test_transcription_webhook_unknown_job_id(client):
    """Webhook with unknown job_id returns 404."""
    payload = {
        "job_id": "nonexistent-job",
        "type": "transcript",
        "status": "success",
        "transcription_data_url": "https://example.com/data.json",
    }
    url = reverse("transcription-webhook")
    response = client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **AUTH_HEADER,
    )
    assert response.status_code == 404


def test_transcription_webhook_invalid_auth(client, transcribing_attachment):  # pylint: disable=unused-argument
    """Webhook with wrong API key returns 403."""
    payload = {
        "job_id": "job-abc-123",
        "type": "transcript",
        "status": "failure",
        "error_code": "unknown_error",
    }
    url = reverse("transcription-webhook")
    response = client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer wrong-key",
    )
    assert response.status_code == 403


def test_transcription_webhook_failure_payload(client, transcribing_attachment):
    """Failure webhook payload marks attachment as TRANSCRIPTION_FAILED."""
    payload = {
        "job_id": "job-abc-123",
        "type": "transcript",
        "status": "failure",
        "error_code": "unknown_error",
    }
    url = reverse("transcription-webhook")
    response = client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **AUTH_HEADER,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "failed"}
    transcribing_attachment.refresh_from_db()
    assert transcribing_attachment.upload_state == AttachmentStatus.TRANSCRIPTION_FAILED
