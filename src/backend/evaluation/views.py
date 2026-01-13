"""
OpenAI-compatible API endpoint for AIAgentService.

This module provides a /v1/chat/completions endpoint that translates
between OpenAI's API format and our AIAgentService.

This is for evaluation purposes only and is not intended for production use.
Works with EvalAP (https://github.com/etalab-ia/evalap/tree/main)
"""

import json
import time
import uuid
from typing import List, Optional

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from core.models import User

from chat.ai_sdk_types import TextUIPart, UIMessage
from chat.clients.pydantic_ai import AIAgentService
from chat.models import ChatConversation
from chat.vercel_ai_sdk.core.events_v4 import (
    FinishMessagePart,
    TextPart,
)


def create_openai_response(
    response_id: str,
    model: str,
    content: str,
    finish_reason: str = "stop",
    usage: Optional[dict] = None,
) -> dict:
    """
    Create an OpenAI-compatible non-streaming response.

    Note: we could use ChatCompletion from openai library.
    """
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def openai_messages_to_ui_messages(openai_messages: List[dict]) -> List[UIMessage]:
    """
    Convert OpenAI message format to UIMessage format for the backend view.
    """
    ui_messages = []
    for msg in openai_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Handle content that can be string or list of content parts
        if isinstance(content, list):
            parts = []
            for part in content:
                if part.get("type") == "text":
                    parts.append(TextUIPart(type="text", text=part.get("text", "")))
                # Add handling for images, etc. as needed
            ui_messages.append(
                UIMessage(
                    id=msg.get("id", str(uuid.uuid4())),
                    role=role,
                    parts=parts,
                    content="".join(content),
                )
            )
        else:
            ui_messages.append(
                UIMessage(
                    id=msg.get("id", str(uuid.uuid4())),
                    role=role,
                    parts=[TextUIPart(type="text", text=content or "")],
                    content=content or "",
                )
            )
    return ui_messages


@method_decorator(csrf_exempt, name="dispatch")
class ChatCompletionsView(View):
    """
    OpenAI-compatible /v1/chat/completions endpoint.

    Usage:
        POST /v1/chat/completions
        {
            "model": "your-model-id",
            "messages": [{"role": "user", "content": "Hello!"}],
            "stream": true,
            "stream_options": {"include_usage": true}
        }
    """

    async def post(self, request):
        """
        Handle POST requests to the chat completions endpoint.
        """
        if settings.ENVIRONMENT not in ["development", "tests"]:
            return JsonResponse(
                {"error": "This endpoint is for evaluation purposes only."}, status=403
            )

        # Enforce the user
        user = await User.objects.aget(email="conversations@conversations.world")

        # Parse request body to get parameters
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Extract parameters
        model = body.get("model", "default-model")
        messages = body.get("messages", [])
        feature_flags = body.get("feature_flags", {})

        # Monkey patch is_feature_enabled to use feature_flags from request
        from core.feature_flags.helpers import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
            is_feature_enabled as original_is_feature_enabled,
        )

        def is_feature_enabled(tested_user: User, flag_name: str) -> bool:
            if feature_flag := feature_flags.get(flag_name):
                return feature_flag.upper() == "ENABLED"
            return original_is_feature_enabled(tested_user, flag_name)

        import core.feature_flags.helpers  # noqa: PLC0415 # pylint: disable=import-outside-toplevel

        core.feature_flags.helpers.is_feature_enabled = is_feature_enabled

        if not messages:
            return JsonResponse(
                {"error": {"message": "messages is required", "type": "invalid_request_error"}},
                status=400,
            )

        # Create a new conversation
        conversation = await ChatConversation.objects.acreate(
            owner=user,
            messages=[],
            pydantic_messages=[],
        )

        # Convert messages
        ui_messages = openai_messages_to_ui_messages(messages)

        # Initialize service
        service = AIAgentService(
            conversation=conversation,
            user=user,
            model_hrid=model,
        )

        # Non-streaming response
        full_content = ""
        final_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        async for event in service._run_agent(ui_messages):  # noqa: SLF001   # pylint: disable=protected-access
            if isinstance(event, TextPart):
                full_content += event.text
            elif isinstance(event, FinishMessagePart):
                if event.usage:
                    final_usage = {
                        "prompt_tokens": event.usage.prompt_tokens,
                        "completion_tokens": event.usage.completion_tokens,
                        "total_tokens": event.usage.prompt_tokens + event.usage.completion_tokens,
                    }

        response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        response = JsonResponse(
            create_openai_response(response_id, model, full_content, "stop", final_usage)
        )

        # Remove the conversation to avoid accumulation
        await conversation.adelete()

        return response
