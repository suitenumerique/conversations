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


def model_message_to_ui_message(model_message: ModelMessage) -> UIMessage:  # noqa: PLR0912  # pylint: disable=too-many-statements
    """
    Convert a ModelMessage (ModelRequest or ModelResponse) to a UIMessage.
    """
    # pylint: disable=too-many-nested-blocks,too-many-branches
    parts: List[UIPart] = []

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
                            parts.append(
                                FileUIPart(
                                    type="file",
                                    mediaType=c.media_type,
                                    url=f"data:{c.media_type};base64,"
                                    + base64.b64encode(c.data).decode("utf-8"),
                                )
                            )
                        elif isinstance(c, (ImageUrl, DocumentUrl)):
                            parts.append(
                                FileUIPart(
                                    type="file",
                                    mediaType=c.media_type,
                                    url=c.url,
                                    filename=c.identifier,
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
                parts.append(ReasoningUIPart(type="reasoning", text=part.content))
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
                    ToolUIPart(
                        type=f"{TOOL_PART_PREFIX}{part.tool_name}",
                        toolCallId=part.tool_call_id,
                        state="input-available",
                        input=json.loads(part.args)
                        if isinstance(part.args, str)
                        else part.args or {},
                    )
                )
            elif isinstance(part, ThinkingPart):
                parts.append(ReasoningUIPart(type="reasoning", text=part.content))
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
