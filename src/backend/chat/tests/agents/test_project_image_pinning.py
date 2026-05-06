"""Tests for project image pinning into the user prompt."""

import pytest
from asgiref.sync import async_to_sync
from freezegun import freeze_time
from pydantic_ai import ImageUrl
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from core.file_upload.enums import AttachmentStatus

from chat.agents.local_media_url_processors import build_project_image_urls
from chat.clients.pydantic_ai import AIAgentService
from chat.clients.schema import ImagePostRunActions
from chat.factories import ChatProjectAttachmentFactory, ChatProjectFactory

pytestmark = pytest.mark.django_db


def _build(project_id):
    return async_to_sync(build_project_image_urls)(project_id)


def test_returns_empty_when_project_id_is_none():
    """No project means no pinned images."""
    assert _build(None) == []


def test_returns_empty_when_project_has_no_attachments():
    """A fresh project with no uploads pins nothing."""
    project = ChatProjectFactory()
    assert _build(project.pk) == []


def test_returns_image_url_per_ready_image_attachment():
    """Every READY image attachment becomes one ImageUrl in upload order."""
    project = ChatProjectFactory()
    # Pin distinct created_at stamps so the (created_at, id) ordering is deterministic;
    # ids are random UUIDs and would otherwise tie-break unpredictably on a clock collision.
    with freeze_time("2026-01-01 00:00:00"):
        img_a = ChatProjectAttachmentFactory(
            project=project,
            file_name="a.png",
            content_type="image/png",
            upload_state=AttachmentStatus.READY,
        )
    with freeze_time("2026-01-01 00:00:01"):
        img_b = ChatProjectAttachmentFactory(
            project=project,
            file_name="b.jpg",
            content_type="image/jpeg",
            upload_state=AttachmentStatus.READY,
        )

    result = _build(project.pk)

    assert [img.identifier for img in result] == [str(img_a.id), str(img_b.id)]
    assert all(isinstance(img, ImageUrl) for img in result)
    assert all(img.url for img in result)


def test_skips_pending_image_attachments():
    """A PENDING image must not be pinned (not yet malware-scanned)."""
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        file_name="pending.png",
        content_type="image/png",
        upload_state=AttachmentStatus.PENDING,
    )

    assert _build(project.pk) == []


def test_skips_non_image_attachments():
    """Documents, PDFs, and markdown rows must not be pinned as images."""
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        file_name="brief.pdf",
        content_type="application/pdf",
        upload_state=AttachmentStatus.READY,
    )
    ChatProjectAttachmentFactory(
        project=project,
        file_name="notes.md",
        content_type="text/markdown",
        upload_state=AttachmentStatus.READY,
    )

    assert _build(project.pk) == []


# Persistence: pinned project image URLs are appended to the run's user prompt
# and end up in `run.result.new_messages()`, but they MUST be stripped before
# the conversation is persisted - otherwise every turn re-saves them and the
# next turn replays both the persisted copies AND a freshly-pinned set. The
# strip is the pure helper `_apply_image_actions`; tests below call it directly.


def _request_with(*content) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=list(content))], kind="request")


def _image_urls(part: UserPromptPart) -> list:
    return [c.url for c in part.content if isinstance(c, ImageUrl)]


def test_pinned_image_urls_are_stripped_from_persisted_messages():
    """Pinned URLs must not survive into ``final_output`` after the in-place
    pass, while non-pinned (in-message) image URLs and text content stay."""
    pinned_url = "https://s3.example.test/proj-1/attachments/pic.png?signed=1"
    in_message_url = "https://s3.example.test/conv-1/attachments/photo.png?signed=2"

    final_output = [
        _request_with(
            "what do you see?",
            ImageUrl(url=in_message_url, identifier="conv-photo"),
            ImageUrl(url=pinned_url, identifier="proj-pic"),
        ),
        ModelResponse(parts=[TextPart(content="A cat.")], kind="response"),
    ]

    AIAgentService._apply_image_actions(  # pylint: disable=protected-access
        final_output, ImagePostRunActions(drop={pinned_url})
    )

    user_part = final_output[0].parts[0]
    assert _image_urls(user_part) == [in_message_url]
    assert "what do you see?" in user_part.content


def test_pinned_drop_and_rewrite_compose_in_one_pass():
    """Drop and rewrite both apply in the same pass: a pinned URL is stripped,
    an in-message URL is rewritten to its durable form."""
    pinned_url = "https://s3.example.test/proj-1/attachments/pic.png?signed=1"
    in_message_signed = "https://s3.example.test/conv-1/attachments/photo.png?signed=2"
    in_message_local = "/media-key/conv-1/attachments/photo.png"

    final_output = [
        _request_with(
            "what do you see?",
            ImageUrl(url=in_message_signed, identifier="conv-photo"),
            ImageUrl(url=pinned_url, identifier="proj-pic"),
        ),
        ModelResponse(parts=[TextPart(content="A cat.")], kind="response"),
    ]

    AIAgentService._apply_image_actions(  # pylint: disable=protected-access
        final_output,
        ImagePostRunActions(
            rewrite={in_message_signed: in_message_local},
            drop={pinned_url},
        ),
    )

    # In-message image kept, rewritten to its local form. Pinned image dropped.
    assert _image_urls(final_output[0].parts[0]) == [in_message_local]


def test_empty_image_actions_leaves_final_output_unchanged():
    """When neither drop nor rewrite is populated, the helper is a no-op."""
    in_message_url = "https://s3.example.test/conv-1/attachments/photo.png?signed=2"

    final_output = [
        _request_with(
            "what do you see?",
            ImageUrl(url=in_message_url, identifier="conv-photo"),
        ),
        ModelResponse(parts=[TextPart(content="A cat.")], kind="response"),
    ]

    AIAgentService._apply_image_actions(  # pylint: disable=protected-access
        final_output, ImagePostRunActions()
    )

    assert _image_urls(final_output[0].parts[0]) == [in_message_url]
