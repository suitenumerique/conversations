"""Backend image guard: text-only models keep images but are told to ignore them.

A text-only model (``supports_image=False``) still receives image parts (these
endpoints tolerate and ignore them) and is instructed that it can't read images.
The image stays in history so a later turn on a vision-capable model can read it.
"""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import ModelRequest
from pydantic_ai.messages import (
    ImageUrl,
    ModelMessage,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from rest_framework import status

from chat.ai_sdk_types import Attachment, TextUIPart, UIMessage
from chat.factories import (
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
)
from chat.llm_configuration import LLModel, LLMProvider
from chat.models import AttachmentStatus

pytestmark = pytest.mark.django_db(transaction=True)

UNREADABLE_MARKER = "cannot read or process images"


@pytest.fixture(autouse=True)
def ai_settings(settings):
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"
    settings.LANGFUSE_ENABLED = False


def _configure_model(settings, *, supports_image):
    """Pin LLM_CONFIGURATIONS to a single model with the given image support."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="single-llm",
            human_readable_name="Single Model",
            is_active=True,
            supports_image=supports_image,
            system_prompt="You are a helpful assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="single-provider",
                base_url="https://www.external-ai-service.com/",
                api_key="test-api-key",
            ),
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"


@pytest.fixture(name="text_only_llm")
def text_only_llm_fixture(settings):
    """Pin LLM_CONFIGURATIONS to a single non-multimodal model."""
    _configure_model(settings, supports_image=False)


def _capturing_model(captured, reply="response"):
    """A FunctionModel that snapshots the request *during* the call.

    Image URLs and the active instruction must be captured here: the
    post-run persistence pass (``_apply_image_actions``) mutates the same
    objects in place (re-presigning history images, dropping pinned project
    images), so reading them after the stream drains is unreliable.
    """

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        requests = [m for m in messages if isinstance(m, ModelRequest)]
        captured["messages"] = list(messages)
        captured["instructions"] = requests[-1].instructions if requests else None
        captured["image_urls"] = [
            content.url
            for request in requests
            for part in request.parts
            if isinstance(part, UserPromptPart)
            for content in part.content
            if isinstance(content, ImageUrl)
        ]
        captured["current_image_urls"] = [
            content.url
            for part in (requests[-1].parts if requests else [])
            if isinstance(part, UserPromptPart)
            for content in part.content
            if isinstance(content, ImageUrl)
        ]
        yield reply

    return FunctionModel(stream_function=agent_model)


def _image_message(text, *, attachments=None, msg_id="1") -> UIMessage:
    return UIMessage(
        id=msg_id,
        role="user",
        content=text,
        parts=[TextUIPart(text=text, type="text")],
        experimental_attachments=attachments,
    )


def _run_turn(api_client, mock_ai_agent_service, conversation, message, model):
    with mock_ai_agent_service(model):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    b"".join(response.streaming_content)  # drain
    return response


def _images_skipped_events(streaming_content: bytes, kind: str) -> list[dict]:
    """Parse `images_skipped` data events of the given kind from an SSE stream."""
    events = []
    for line in streaming_content.decode("utf-8").splitlines():
        if not line.startswith("2:"):
            continue
        for item in json.loads(line[2:]):
            if (
                isinstance(item, dict)
                and item.get("type") == "images_skipped"
                and item.get("kind") == kind
            ):
                events.append(item)
    return events


def _persisted_image_urls(conversation) -> list:
    return [
        content["url"]
        for msg in conversation.pydantic_messages
        if msg.get("kind") == "request"
        for part in msg["parts"]
        for content in (part["content"] if isinstance(part["content"], list) else [])
        if isinstance(content, dict) and content.get("kind") == "image-url"
    ]


def test_image_kept_and_instruction_added_for_text_only_model(
    api_client, mock_ai_agent_service, text_only_llm
):
    """Text-only model receives the image, is told it can't read it, image persists."""
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    message = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
    )

    captured: dict = {}
    _run_turn(
        api_client, mock_ai_agent_service, chat_conversation, message, _capturing_model(captured)
    )

    # The model DOES receive the image, unlike before (it is no longer stripped).
    assert len(captured["current_image_urls"]) == 1

    # It is instructed that it can't read images, and the instruction names the file.
    assert UNREADABLE_MARKER in captured["instructions"]
    assert "sample.png" in captured["instructions"]

    # The notification is preserved: the persisted user bubble keeps the image
    # attachment with a `skipped` marker for the "image ignored" chip.
    chat_conversation.refresh_from_db()
    [user_message] = [m for m in chat_conversation.messages if m.role == "user"]
    [skipped_attachment] = user_message.experimental_attachments or []
    assert skipped_attachment.skipped == {"reason": "model_text_only"}

    # The image is persisted to history (durable local URL form) so a later
    # vision-capable turn can read it.
    assert image_url in _persisted_image_urls(chat_conversation)


def test_project_images_not_sent_but_instruction_added_for_text_only_model(
    api_client, mock_ai_agent_service, text_only_llm
):
    """Pinned project images aren't sent to a text-only model, but it is told they exist."""
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project, content_type="image/png", upload_state=AttachmentStatus.READY
    )
    chat_conversation = ChatConversationFactory(
        owner=project.owner,
        owner__language="en-us",
        model_hrid="default-model",
        project=project,
    )
    api_client.force_login(chat_conversation.owner)

    message = _image_message("Tell me about the project.")
    captured: dict = {}

    with patch(
        "chat.clients.pydantic_ai.build_project_image_urls",
        new=AsyncMock(),
    ) as mock_build:
        _run_turn(
            api_client,
            mock_ai_agent_service,
            chat_conversation,
            message,
            _capturing_model(captured),
        )

    # We never even build the project images for a text-only model.
    mock_build.assert_not_called()

    assert captured["image_urls"] == []
    # ...but the model is told a project image exists that it can't read.
    assert UNREADABLE_MARKER in captured["instructions"]
    assert "project" in captured["instructions"]


def test_image_capable_model_has_no_unreadable_instruction(
    api_client, mock_ai_agent_service, settings
):
    """A vision-capable model is never given the unreadable-images instruction."""
    _configure_model(settings, supports_image=True)
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    message = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
    )

    captured: dict = {}
    _run_turn(
        api_client, mock_ai_agent_service, chat_conversation, message, _capturing_model(captured)
    )

    assert captured["current_image_urls"]  # the image still reaches the model
    assert UNREADABLE_MARKER not in captured["instructions"]


def test_text_only_model_imageless_turn_has_no_unreadable_instruction(
    api_client, mock_ai_agent_service, text_only_llm
):
    """No images present means no unreadable-images instruction (context stays lean)."""
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    message = _image_message("Hello there.")
    captured: dict = {}
    _run_turn(
        api_client, mock_ai_agent_service, chat_conversation, message, _capturing_model(captured)
    )

    assert UNREADABLE_MARKER not in captured["instructions"]


def test_switch_text_only_to_vision_reads_in_message_image(
    api_client, mock_ai_agent_service, settings
):
    """The planned text-only -> vision flip: a persisted image becomes readable."""
    _configure_model(settings, supports_image=False)
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    turn1 = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
        msg_id="1",
    )
    _run_turn(api_client, mock_ai_agent_service, chat_conversation, turn1, _capturing_model({}))

    # The image survived the text-only turn in durable local URL form.
    chat_conversation.refresh_from_db()
    assert image_url in _persisted_image_urls(chat_conversation)

    # Nightly migration flips the conversation onto a vision model.
    _configure_model(settings, supports_image=True)

    turn2 = _image_message("Describe it in more detail.", msg_id="2")
    captured: dict = {}
    _run_turn(
        api_client, mock_ai_agent_service, chat_conversation, turn2, _capturing_model(captured)
    )

    # The history image now reaches the vision model...
    assert captured["image_urls"]

    # ...and the current (vision) turn carries no unreadable-images instruction,
    # even though the persisted text-only turn stored one.
    assert UNREADABLE_MARKER not in captured["instructions"]


def test_switch_text_only_to_vision_reads_project_image(
    api_client, mock_ai_agent_service, settings
):
    """The text-only -> vision flip also restores pinned project images."""
    _configure_model(settings, supports_image=False)
    project = ChatProjectFactory()
    ChatProjectAttachmentFactory(
        project=project, content_type="image/png", upload_state=AttachmentStatus.READY
    )
    chat_conversation = ChatConversationFactory(
        owner=project.owner,
        owner__language="en-us",
        model_hrid="default-model",
        project=project,
    )
    api_client.force_login(chat_conversation.owner)

    turn1 = _image_message("Tell me about the project.", msg_id="1")
    captured1: dict = {}
    with patch("chat.clients.pydantic_ai.build_project_image_urls", new=AsyncMock()) as mock_build:
        _run_turn(
            api_client,
            mock_ai_agent_service,
            chat_conversation,
            turn1,
            _capturing_model(captured1),
        )
    mock_build.assert_not_called()
    assert UNREADABLE_MARKER in captured1["instructions"]

    # Nightly migration flips the conversation onto a vision model. We patch the
    # project-image builder (the real one would hit object storage) to assert it is
    # now invoked and its image reaches the model.
    _configure_model(settings, supports_image=True)
    pinned = ImageUrl(
        url="https://example.com/pinned.png", identifier="pid", media_type="image/png"
    )

    turn2 = _image_message("And what colors are used?", msg_id="2")
    captured2: dict = {}
    with patch(
        "chat.clients.pydantic_ai.build_project_image_urls",
        new=AsyncMock(return_value=[pinned]),
    ) as mock_build:
        _run_turn(
            api_client, mock_ai_agent_service, chat_conversation, turn2, _capturing_model(captured2)
        )

    mock_build.assert_called()
    # The project image is now pinned and reaches the vision model...
    assert "https://example.com/pinned.png" in captured2["current_image_urls"]
    # ...with no unreadable-images instruction.
    assert UNREADABLE_MARKER not in captured2["instructions"]


def test_conversation_event_lists_all_images_for_text_only_model(
    api_client, mock_ai_agent_service, text_only_llm
):
    """A text-only turn emits an images_skipped kind=conversation event naming every image."""
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    message = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
    )

    with mock_ai_agent_service(_capturing_model({})):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    content = b"".join(response.streaming_content)

    events = _images_skipped_events(content, kind="conversation")
    assert len(events) == 1
    assert events[0]["names"] == ["sample.png"]


def test_no_conversation_event_for_image_capable_model(api_client, mock_ai_agent_service, settings):
    """A vision-capable model emits no images_skipped kind=conversation event."""
    _configure_model(settings, supports_image=True)
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    message = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
    )

    with mock_ai_agent_service(_capturing_model({})):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    content = b"".join(response.streaming_content)

    assert not _images_skipped_events(content, kind="conversation")


def test_user_skip_event_emitted_for_text_only_model(
    api_client, mock_ai_agent_service, text_only_llm
):
    """A text-only turn emits the kind="user" strike event (named after the upload)."""
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    message = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
    )

    with mock_ai_agent_service(_capturing_model({})):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    content = b"".join(response.streaming_content)

    user_events = _images_skipped_events(content, kind="user")
    assert len(user_events) == 1
    assert user_events[0]["names"] == ["sample.png"]


def test_no_user_skip_event_for_image_capable_model(api_client, mock_ai_agent_service, settings):
    """A vision-capable model emits no kind="user" strike event."""
    _configure_model(settings, supports_image=True)
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"
    message = _image_message(
        "What is in this image?",
        attachments=[Attachment(name="sample.png", contentType="image/png", url=image_url)],
    )

    with mock_ai_agent_service(_capturing_model({})):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    content = b"".join(response.streaming_content)

    assert not _images_skipped_events(content, kind="user")
