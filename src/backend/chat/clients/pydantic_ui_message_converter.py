"""
Utility functions to convert between UIMessage (ai_sdk_types.py)
and UserContent/ModelMessage (pydantic_ai.messages.py).
"""

import base64
import json
import logging
import uuid
from dataclasses import asdict
from typing import List

from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
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
                BinaryContent(
                    data=raw_data,
                    media_type=experimental_attachment.contentType,
                    identifier=experimental_attachment.name,
                )
            )
        elif experimental_attachment.contentType.startswith("image/"):
            user_contents.append(
                ImageUrl(
                    url=experimental_attachment.url,
                    media_type=experimental_attachment.contentType,
                    identifier=experimental_attachment.name,
                )
            )
        else:
            user_contents.append(
                DocumentUrl(
                    url=experimental_attachment.url,
                    media_type=experimental_attachment.contentType,
                    identifier=experimental_attachment.name,
                )
            )

    return user_contents


def model_message_to_ui_message(model_message: ModelMessage) -> UIMessage:  # noqa: PLR0912, PLR0915  # pylint: disable=too-many-statements
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
                        elif isinstance(c, ImageUrl):
                            experimental_attachments.append(
                                Attachment(
                                    contentType=c.media_type,
                                    url=c.url,
                                    name=c.identifier,
                                )
                            )
                        elif isinstance(c, DocumentUrl):
                            experimental_attachments.append(
                                Attachment(
                                    contentType=c.media_type,
                                    url=c.url,
                                    name=c.identifier,
                                )
                            )
                        else:  # AudioUrl, VideoUrl
                            raise ValueError(
                                f"Unsupported UserContent in UserPromptPart: {type(c)}"
                            )
            elif isinstance(part, TextPart) and part.content:
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
            id=str(uuid.uuid4()),
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
                            args=json.loads(part.args)
                            if isinstance(part.args, str)
                            else part.args or {},
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
            id=str(uuid.uuid4()),
            role="assistant",
            content="".join(part.text for part in parts if isinstance(part, TextUIPart)),
            parts=parts,
            createdAt=model_message.timestamp,
        )

    raise ValueError(f"Unsupported ModelMessage part type: {type(model_message)}")
