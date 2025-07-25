"""
Utility functions to convert between UIMessage (ai_sdk_types.py)
and UserContent/ModelMessage (pydantic_ai.messages.py).
"""

import base64
import json
import logging
from dataclasses import asdict
from typing import List

from pydantic_ai.messages import (
    BinaryContent,
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
    Attachment,
    FileUIPart,
    ReasoningDetailText,
    ReasoningUIPart,
    TextUIPart,
    ToolInvocationCall,
    ToolInvocationUIPart,
    UIMessage,
    UIPart,
)


def ui_message_to_model_message(message: UIMessage) -> ModelMessage:  # noqa: PLR0912
    """
    Convert a UIMessage to a ModelMessage (ModelRequest or ModelResponse) for Pydantic-AI.
    """
    # pylint: disable=too-many-branches
    parts_request: List[ModelRequestPart] = []
    parts_response: List[ModelResponsePart] = []
    for part in message.parts:
        if isinstance(part, TextUIPart):
            if message.role == "user":
                parts_request.append(UserPromptPart(content=part.text, timestamp=message.createdAt))
            elif message.role == "assistant":
                parts_response.append(TextPart(content=part.text))
        elif isinstance(part, ToolInvocationUIPart):
            parts_response.append(
                ToolCallPart(
                    tool_call_id=part.toolInvocation.toolCallId,
                    tool_name=part.toolInvocation.toolName,
                    args=part.toolInvocation.args,
                )
            )
        elif isinstance(part, ReasoningUIPart):
            parts_response.append(
                ThinkingPart(
                    content=part.reasoning,
                )
            )
        else:
            raise ValueError(f"Unsupported UIPart type: {type(part)}")
    # Handle experimental attachments
    for experimental_attachment in message.experimental_attachments or []:
        if experimental_attachment.url.startswith("data:"):
            raw_data = base64.b64decode(experimental_attachment.url.split(",")[1])
            if message.role == "user":
                parts_request.append(
                    UserPromptPart(
                        content=[
                            BinaryContent(
                                data=raw_data, media_type=experimental_attachment.contentType
                            )
                        ]
                    )
                )
            elif message.role == "assistant":
                raise ValueError(
                    "Experimental attachments are not supported in assistant responses."
                )
        else:
            raise ValueError(
                f"Unsupported experimental attachment URL format: {experimental_attachment.url}"
            )
    if message.role == "user":
        return ModelRequest(parts=parts_request, kind="request")
    if message.role == "assistant":
        return ModelResponse(parts=parts_response)
    raise ValueError(f"Unsupported message role: {message.role}")


def ui_message_to_user_content(message: UIMessage) -> List[UserContent]:
    """
    Convert a UIMessage to a list of UserContent for Pydantic-AI.
    """
    user_contents: List[UserContent] = []
    for part in message.parts:
        if isinstance(part, TextUIPart):
            user_contents.append(part.text)
        elif isinstance(part, FileUIPart):
            user_contents.append(
                BinaryContent(data=part.data.encode("utf-8"), media_type=part.mimeType)
            )
        elif isinstance(part, ToolInvocationUIPart):
            # Tool invocations are not directly mapped to UserContent, skip or handle as needed
            continue
        elif isinstance(part, ReasoningUIPart):
            # Reasoning parts are not directly mapped to UserContent, skip or handle as needed
            continue
        else:
            raise ValueError(f"Unsupported UIPart type: {type(part)}")
    for experimental_attachment in message.experimental_attachments or []:
        if experimental_attachment.url.startswith("data:"):
            # Handle data URLs
            raw_data = base64.b64decode(experimental_attachment.url.split(",")[1])
            user_contents.append(
                BinaryContent(data=raw_data, media_type=experimental_attachment.contentType)
            )
        else:
            raise ValueError(
                f"Unsupported experimental attachment URL format: {experimental_attachment.url}"
            )

    return user_contents


def model_message_to_ui_message(model_message: ModelMessage) -> UIMessage:  # noqa: PLR0912
    """
    Convert a ModelMessage (ModelRequest or ModelResponse) to a UIMessage.
    """
    # pylint: disable=too-many-nested-blocks,too-many-branches
    parts: List[UIPart] = []
    experimental_attachments: List[Attachment] = []

    logging.getLogger(__name__).debug(
        "Converting ModelMessage to UIMessage: %s %s",
        type(model_message),
        asdict(model_message),
    )
    _states = {"tool-calls": {}}

    if isinstance(model_message, ModelRequest):
        message_timestamp = None

        for part in model_message.parts:
            if isinstance(part, SystemPromptPart):
                # System prompts are not included in UIMessage parts
                continue
            if isinstance(part, UserPromptPart):
                message_timestamp = part.timestamp
                if isinstance(part.content, str):
                    parts.append(TextUIPart(type="text", text=part.content))
                elif isinstance(part.content, list):
                    for c in part.content:
                        if isinstance(c, str):
                            parts.append(TextUIPart(type="text", text=c))
                        elif isinstance(c, BinaryContent):
                            experimental_attachments.append(
                                Attachment(
                                    contentType=c.media_type,
                                    url=f"data:{c.media_type};base64,"
                                    + base64.b64encode(c.data).decode("utf-8"),
                                )
                            )
                        else:  # ImageUrl, AudioUrl, VideoUrl, DocumentUrl, BinaryContent
                            raise ValueError(
                                f"Unsupported UserContent in UserPromptPart: {type(c)}"
                            )
            elif isinstance(part, TextPart):
                parts.append(TextUIPart(type="text", text=part.content))
            elif isinstance(part, ToolReturnPart):
                pass
                # parts.append(ToolInvocationUIPart(
                #     type="tool-invocation",
                #     toolInvocation=ToolInvocationResult(
                #         state="result",
                #         toolCallId=part.tool_call_id,
                #         toolName=part.tool_name,
                #         args={},
                #         result=part.content,
                #     )
                # ))
            elif isinstance(part, ThinkingPart):
                parts.append(
                    ReasoningUIPart(
                        type="reasoning",
                        reasoning=part.content,
                        details=[
                            ReasoningDetailText(
                                type="text",
                                text=part.content,
                                signature=part.signature,
                            )
                        ],
                    )
                )
            elif isinstance(part, RetryPromptPart):
                # Retry prompts are not included in UIMessage parts
                continue
            else:
                raise ValueError(f"Unsupported ModelRequest part type: {type(part)}")

        if not parts:
            return None

        return UIMessage(
            id="",
            role="user",
            content="".join(part.text for part in parts if isinstance(part, TextUIPart)),
            parts=parts,
            experimental_attachments=experimental_attachments or None,
            createdAt=message_timestamp,
        )

    if isinstance(model_message, ModelResponse):
        for part in model_message.parts:
            if isinstance(part, UserPromptPart):
                if isinstance(part.content, str):
                    parts.append(TextUIPart(type="text", text=part.content))
                elif isinstance(part.content, list):
                    for c in part.content:
                        if isinstance(c, str):
                            parts.append(TextUIPart(type="text", text=c))
                        else:  # ImageUrl, AudioUrl, VideoUrl, DocumentUrl, BinaryContent
                            raise ValueError(
                                f"Unsupported UserContent in UserPromptPart: {type(c)}"
                            )
            elif isinstance(part, TextPart):
                parts.append(TextUIPart(type="text", text=part.content))
            elif isinstance(part, ToolCallPart):
                parts.append(
                    ToolInvocationUIPart(
                        type="tool-invocation",
                        toolInvocation=ToolInvocationCall(
                            state="call",
                            toolCallId=part.tool_call_id,
                            toolName=part.tool_name,
                            args=json.loads(part.args) if isinstance(part.args, str) else part.args,
                        ),
                    )
                )
            elif isinstance(part, ThinkingPart):
                parts.append(
                    ReasoningUIPart(
                        type="reasoning",
                        reasoning=part.content,
                        details=[
                            ReasoningDetailText(
                                type="text",
                                text=part.content,
                                signature=part.signature,
                            )
                        ],
                    )
                )
            else:
                raise ValueError(f"Unsupported ModelMessage part type: {type(part)}")

        return UIMessage(
            id="",
            role="assistant",
            content="".join(part.text for part in parts if isinstance(part, TextUIPart)),
            parts=parts,
            createdAt=model_message.timestamp,
        )

    raise ValueError(f"Unsupported ModelMessage part type: {type(model_message)}")
