"""Unit tests for ChatConversationSerializer derived fields."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument

import pytest

from core.file_upload.enums import AttachmentStatus

from chat import serializers
from chat.ai_sdk_types import Attachment, TextUIPart, UIMessage
from chat.factories import (
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
)
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db


def _image_message(name: str, msg_id: str = "1") -> UIMessage:
    return UIMessage(
        id=msg_id,
        role="user",
        content="here",
        parts=[TextUIPart(text="here", type="text")],
        experimental_attachments=[
            Attachment(name=name, contentType="image/png", url=f"/media-key/{name}")
        ],
    )


def _make_llm(hrid: str, supports_image: bool) -> LLModel:
    return LLModel(
        hrid=hrid,
        model_name=f"{hrid}-llm",
        human_readable_name=hrid,
        is_active=True,
        supports_image=supports_image,
        system_prompt="ok",
        tools=[],
        provider=LLMProvider(hrid=f"{hrid}-provider", base_url="https://x", api_key="k"),
    )


@pytest.fixture(name="llm_configs", autouse=True)
def llm_configs_fixture(settings):
    settings.LLM_CONFIGURATIONS = {
        "vision-model": _make_llm("vision-model", supports_image=True),
        "text-only-model": _make_llm("text-only-model", supports_image=False),
    }


def test_project_images_skipped_false_when_no_project():
    conversation = ChatConversationFactory(model_hrid="text-only-model")
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["project_images_skipped"] is False


def test_project_images_skipped_false_when_model_supports_image():
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=project.owner,
        content_type="image/png",
        upload_state=AttachmentStatus.READY,
    )
    conversation = ChatConversationFactory(
        owner=project.owner, project=project, model_hrid="vision-model"
    )
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["project_images_skipped"] is False


def test_project_images_skipped_false_when_no_pinned_model():
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=project.owner,
        content_type="image/png",
        upload_state=AttachmentStatus.READY,
    )
    conversation = ChatConversationFactory(owner=project.owner, project=project, model_hrid="")
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["project_images_skipped"] is False


def test_project_images_skipped_true_for_text_model_with_project_images():
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=project.owner,
        content_type="image/png",
        upload_state=AttachmentStatus.READY,
    )
    conversation = ChatConversationFactory(
        owner=project.owner, project=project, model_hrid="text-only-model"
    )
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["project_images_skipped"] is True


def test_project_images_skipped_false_for_text_model_with_only_text_attachments():
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=project.owner,
        content_type="text/plain",
        upload_state=AttachmentStatus.READY,
    )
    conversation = ChatConversationFactory(
        owner=project.owner, project=project, model_hrid="text-only-model"
    )
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["project_images_skipped"] is False


def test_project_images_skipped_ignores_non_ready_attachments():
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project,
        uploaded_by=project.owner,
        content_type="image/png",
        upload_state=AttachmentStatus.PENDING,
    )
    conversation = ChatConversationFactory(
        owner=project.owner, project=project, model_hrid="text-only-model"
    )
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["project_images_skipped"] is False


def test_skipped_image_names_lists_images_for_text_only_model():
    conversation = ChatConversationFactory(
        model_hrid="text-only-model",
        messages=[_image_message("sample.png"), _image_message("scan.jpg", msg_id="2")],
    )
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["skipped_image_names"] == ["sample.png", "scan.jpg"]


def test_skipped_image_names_empty_for_vision_model():
    conversation = ChatConversationFactory(
        model_hrid="vision-model", messages=[_image_message("sample.png")]
    )
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["skipped_image_names"] == []


def test_skipped_image_names_empty_without_pinned_model():
    conversation = ChatConversationFactory(model_hrid="", messages=[_image_message("sample.png")])
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["skipped_image_names"] == []


def test_skipped_image_names_empty_without_images():
    conversation = ChatConversationFactory(model_hrid="text-only-model")
    data = serializers.ChatConversationSerializer(conversation).data
    assert data["skipped_image_names"] == []
