"""
Utility functions to convert between UIMessage (ai_sdk_types.py)
and UserContent/ModelMessage (pydantic_ai.messages.py).
"""

import base64
import json
import logging
import uuid
from dataclasses import asdict
from typing import List, Optional

from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserContent,
    UserPromptPart,
)

from chat.ai_sdk_types import (
    TOOL_PART_PREFIX,
    FileUIPart,
    ReasoningUIPart,
    SourceUrlUIPart,
    StepStartUIPart,
    TextUIPart,
    ToolUIPart,
    UIMessage,
    UIPart,
)
from chat.constants import IMAGE_MIME_PREFIX


def ui_message_to_user_content(message: UIMessage) -> List[UserContent]:
    """
    Convert a UIMessage to a list of UserContent for Pydantic-AI.
    """
    user_contents: List[UserContent] = []
    for part in message.parts:
        if isinstance(part, TextUIPart):
            user_contents.append(part.text)
        elif isinstance(part, FileUIPart):
            user_contents.append(_file_part_to_user_content(part))
        elif isinstance(part, (ToolUIPart, ReasoningUIPart, SourceUrlUIPart, StepStartUIPart)):
            # Nothing the model consumes as user content.
            continue
        else:
            raise ValueError(f"Unsupported UIPart type: {type(part)}")

    return user_contents


def _file_part_to_user_content(part: FileUIPart) -> UserContent:
    """Turn a file part into the content type Pydantic-AI expects for it."""
    if part.url.startswith("data:"):
        return BinaryContent(
            data=base64.b64decode(part.url.split(",")[1]),
            media_type=part.mediaType,
            identifier=part.filename,
        )
    if (part.mediaType or "").startswith(IMAGE_MIME_PREFIX):
        return ImageUrl(url=part.url, media_type=part.mediaType, identifier=part.filename)
    return DocumentUrl(url=part.url, media_type=part.mediaType, identifier=part.filename)


def model_message_to_ui_message(model_message: ModelMessage) -> Optional[UIMessage]:
    """
    Convert a ModelMessage (ModelRequest or ModelResponse) to a UIMessage.

    Returns None for a request holding nothing the UI renders (a system prompt
    or a tool return on its own); callers must skip it rather than store it.
    """
    logging.getLogger(__name__).debug(
        "Converting ModelMessage to UIMessage: %s %s",
        type(model_message),
        asdict(model_message),
    )

    # Unused: kept from the Pydantic AI rewrite as the intended place to carry
    # tool-call state across the parts of one message (pairing a ToolCallPart
    # with the ToolReturnPart that answers it, which is dropped today).
    _states = {"tool-calls": {}}

    if isinstance(model_message, ModelRequest):
        return _model_request_to_ui_message(model_message)

    if isinstance(model_message, ModelResponse):
        return _model_response_to_ui_message(model_message)

    raise ValueError(f"Unsupported ModelMessage part type: {type(model_message)}")


def _model_request_to_ui_message(model_request: ModelRequest) -> Optional[UIMessage]:
    """Build the user-side UIMessage, or None when the request has nothing to show."""
    parts: List[UIPart] = []
    message_timestamp = None

    for part in model_request.parts:
        if isinstance(part, UserPromptPart):
            message_timestamp = part.timestamp
        parts.extend(_request_part_to_ui_parts(part))

    if not parts:
        return None

    return UIMessage(
        id=str(uuid.uuid4()),
        role="user",
        content="".join(part.text for part in parts if isinstance(part, TextUIPart)),
        parts=parts,
        createdAt=message_timestamp,
    )


def _request_part_to_ui_parts(part: ModelRequestPart) -> List[UIPart]:
    """The UI parts a single ModelRequest part contributes, if any."""
    if isinstance(part, (SystemPromptPart, RetryPromptPart, ToolReturnPart)):
        # System prompts, retry prompts and tool returns are not included in
        # UIMessage parts. Tool returns used to be rendered as:
        # ToolInvocationUIPart(
        #     type="tool-invocation",
        #     toolInvocation=ToolInvocationResult(
        #         state="result",
        #         toolCallId=part.tool_call_id,
        #         toolName=part.tool_name,
        #         args={},
        #         result=part.content,
        #     )
        # )
        return []

    if isinstance(part, UserPromptPart):
        if isinstance(part.content, str):
            return [TextUIPart(type="text", text=part.content)]
        if isinstance(part.content, list):
            return [_user_content_to_ui_part(content) for content in part.content]
        return []

    if isinstance(part, TextPart) and part.content:
        return [TextUIPart(type="text", text=part.content)]

    if isinstance(part, ThinkingPart):
        return [ReasoningUIPart(type="reasoning", text=part.content)]

    raise ValueError(f"Unsupported ModelRequest part type: {type(part)}")


def _user_content_to_ui_part(content: UserContent) -> UIPart:
    """The UI part carrying one piece of user content."""
    if isinstance(content, str):
        return TextUIPart(type="text", text=content)

    if isinstance(content, BinaryContent):
        return FileUIPart(
            type="file",
            mediaType=content.media_type,
            url=f"data:{content.media_type};base64,"
            + base64.b64encode(content.data).decode("utf-8"),
        )

    if isinstance(content, (ImageUrl, DocumentUrl)):
        return FileUIPart(
            type="file",
            mediaType=content.media_type,
            url=content.url,
            filename=content.identifier,
        )

    # AudioUrl, VideoUrl
    raise ValueError(f"Unsupported UserContent in UserPromptPart: {type(content)}")


def _model_response_to_ui_message(model_response: ModelResponse) -> UIMessage:
    """Build the assistant-side UIMessage."""
    parts: List[UIPart] = []
    for part in model_response.parts:
        parts.extend(_response_part_to_ui_parts(part))

    return UIMessage(
        id=str(uuid.uuid4()),
        role="assistant",
        content="".join(part.text for part in parts if isinstance(part, TextUIPart)),
        parts=parts,
        createdAt=model_response.timestamp,
    )


def _response_part_to_ui_parts(part: ModelResponsePart) -> List[UIPart]:
    """The UI parts a single ModelResponse part contributes, if any."""
    if isinstance(part, UserPromptPart):
        if isinstance(part.content, str):
            return [TextUIPart(type="text", text=part.content)]
        if isinstance(part.content, list):
            return [_response_user_content_to_ui_part(content) for content in part.content]
        return []

    if isinstance(part, TextPart):
        return [TextUIPart(type="text", text=part.content)]

    if isinstance(part, ToolCallPart):
        return [
            ToolUIPart(
                type=f"{TOOL_PART_PREFIX}{part.tool_name}",
                toolCallId=part.tool_call_id,
                state="input-available",
                input=json.loads(part.args) if isinstance(part.args, str) else part.args or {},
            )
        ]

    if isinstance(part, ThinkingPart):
        return [ReasoningUIPart(type="reasoning", text=part.content)]

    raise ValueError(f"Unsupported ModelMessage part type: {type(part)}")


def _response_user_content_to_ui_part(content: UserContent) -> UIPart:
    """A response only ever carries text back; anything else is unexpected."""
    if isinstance(content, str):
        return TextUIPart(type="text", text=content)

    # ImageUrl, AudioUrl, VideoUrl, DocumentUrl, BinaryContent
    raise ValueError(f"Unsupported UserContent in UserPromptPart: {type(content)}")
