"""Backend image guard: drop input images when the active model can't see them."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-argument

from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from pydantic_ai import ModelRequest
from pydantic_ai.messages import (
    ImageUrl,
    ModelMessage,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from rest_framework import status

from chat.ai_sdk_types import Attachment, TextUIPart, UIMessage
from chat.factories import ChatConversationFactory, ChatProjectFactory
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ai_settings(settings):
    settings.AI_BASE_URL = "https://www.external-ai-service.com/"
    settings.AI_API_KEY = "test-api-key"
    settings.AI_MODEL = "test-model"
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"


@pytest.fixture(name="text_only_llm")
def text_only_llm_fixture(settings):
    """Pin LLM_CONFIGURATIONS to a single non-multimodal model."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="text-only-llm",
            human_readable_name="Text Only",
            is_active=True,
            supports_image=False,
            system_prompt="You are a helpful assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="text-only-provider",
                base_url="https://www.external-ai-service.com/",
                api_key="test-api-key",
            ),
        ),
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"


@freeze_time("2025-10-18T20:48:20.286204Z")
def test_image_is_dropped_for_non_multimodal_model(
    api_client, mock_ai_agent_service, text_only_llm
):
    """A non-multimodal model must never receive ImageUrl content."""
    chat_conversation = ChatConversationFactory(owner__language="en-us", model_hrid="default-model")
    api_client.force_login(chat_conversation.owner)

    image_url = f"/media-key/{chat_conversation.pk}/sample.png"

    message = UIMessage(
        id="1",
        role="user",
        content="What is in this image?",
        parts=[TextUIPart(text="What is in this image?", type="text")],
        experimental_attachments=[
            Attachment(
                name="sample.png",
                contentType="image/png",
                url=image_url,
            )
        ],
    )

    captured: dict = {}

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        captured["messages"] = messages
        yield "I cannot see images."

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)  # drain

    # Single ModelRequest with a single UserPromptPart and only the text inside.
    [request] = captured["messages"]
    assert isinstance(request, ModelRequest)
    [user_prompt] = [p for p in request.parts if isinstance(p, UserPromptPart)]
    assert user_prompt.content == ["What is in this image?"]
    assert not any(isinstance(c, ImageUrl) for c in user_prompt.content)

    # The persisted user message keeps the image attachment with a `skipped`
    # marker so the UI can render an inline "image removed" chip on reload.
    chat_conversation.refresh_from_db()
    user_messages = [m for m in chat_conversation.messages if m.role == "user"]
    assert len(user_messages) == 1
    [skipped_attachment] = user_messages[0].experimental_attachments or []
    assert skipped_attachment.name == "sample.png"
    assert skipped_attachment.contentType == "image/png"
    assert skipped_attachment.skipped == {"reason": "model_text_only"}


@freeze_time("2025-10-18T20:48:20.286204Z")
def test_pinned_project_images_are_skipped_for_non_multimodal_model(
    api_client, mock_ai_agent_service, text_only_llm
):
    """Pinned project images must not leak into a non-multimodal model's prompt."""
    project = ChatProjectFactory()
    chat_conversation = ChatConversationFactory(
        owner=project.owner,
        owner__language="en-us",
        model_hrid="default-model",
        project=project,
    )
    api_client.force_login(chat_conversation.owner)

    pinned_project_image = ImageUrl(
        url=f"http://test.minio/{project.pk}/attachments/pinned.png",
        identifier="pinned-image-id",
        media_type="image/png",
    )

    message = UIMessage(
        id="1",
        role="user",
        content="Tell me about the project.",
        parts=[TextUIPart(text="Tell me about the project.", type="text")],
    )

    captured: dict = {}

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        captured["messages"] = messages
        yield "Project info, no images visible."

    with (
        mock_ai_agent_service(FunctionModel(stream_function=agent_model)),
        patch(
            "chat.clients.pydantic_ai.build_project_image_urls",
            new=AsyncMock(return_value=[pinned_project_image]),
        ) as mock_build,
    ):
        response = api_client.post(
            f"/api/v1.0/chats/{chat_conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    _ = b"".join(response.streaming_content)  # drain

    # build_project_image_urls must not even be called when the resolved model
    # cannot see images - the guard skips the whole project-image block.
    mock_build.assert_not_called()

    [request] = captured["messages"]
    assert isinstance(request, ModelRequest)
    [user_prompt] = [p for p in request.parts if isinstance(p, UserPromptPart)]
    assert not any(isinstance(c, ImageUrl) for c in user_prompt.content)
