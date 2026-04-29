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


class BaseWebhook(BaseModel):
    """Base webhook payload."""

    job_id: str = Field(
        title="Job ID",
        description="The ID of the job document in the receiver system.",
    )


class TranscribeWebhookSuccessPayload(BaseWebhook):
    """Payload for a successful transcription webhook."""

    type: Literal["transcript"] = Field(default="transcript")
    status: Literal["success"] = Field(default="success")
    transcription_data_url: str = Field(
        title="Transcript", description="URL to the raw transcription data."
    )


class TranscribeWebhookPendingPayload(BaseWebhook):
    """Payload for a pending transcription webhook-like response."""

    type: Literal["transcript"] = Field(default="transcript")
    status: Literal["pending"] = Field(default="pending")


class TranscribeWebhookFailurePayload(BaseWebhook):
    """Payload for a failed transcription webhook."""

    type: Literal["transcript"] = Field(default="transcript")
    status: Literal["failure"] = Field(default="failure")
    error_code: str = Field(title="Error code", description="The error code.")


TranscribeWebhookPayloads = Annotated[
    Union[
        TranscribeWebhookSuccessPayload,
        TranscribeWebhookPendingPayload,
        TranscribeWebhookFailurePayload,
    ],
    Field(discriminator="status"),
]


webhook_payload_adapter = TypeAdapter(TranscribeWebhookPayloads)
