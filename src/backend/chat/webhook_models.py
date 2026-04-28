"""Pydantic models for transcription webhook payloads."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter


class WhisperXSegment(BaseModel):
    """A single segment from a WhisperX transcription."""

    start: float
    end: float
    text: str
    words: list = Field(default_factory=list)
    speaker: str | None = None


class WhisperXResponse(BaseModel):
    """Full WhisperX transcription response."""

    segments: list[WhisperXSegment]
    word_segments: list = Field(default_factory=list)


class TranscribeWebhookSuccessPayload(BaseModel):
    """Webhook payload for a successful transcription job."""

    job_id: str
    type: str
    status: Literal["success"]
    transcription_data_url: str


class TranscribeWebhookFailurePayload(BaseModel):
    """Webhook payload for a failed transcription job."""

    job_id: str
    type: str
    status: Literal["failure", "pending"]
    error_code: str | None = None


WebhookPayload = Annotated[
    Union[TranscribeWebhookSuccessPayload, TranscribeWebhookFailurePayload],
    Field(discriminator="status"),
]

webhook_payload_adapter = TypeAdapter(WebhookPayload)
