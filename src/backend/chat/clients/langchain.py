"""LangChainAgentService class for handling AI agent interactions using LangChain."""

import asyncio
import json
import logging
import queue
import threading
import uuid
from contextlib import AsyncExitStack
from typing import List

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.tools import tool

from chat.ai_sdk_types import (
    TextUIPart,
    ToolInvocationPartialCall,
    ToolInvocationResult,
    ToolInvocationUIPart,
    UIMessage,
)
from chat.mcp_servers import get_mcp_servers

logger = logging.getLogger(__name__)

# LangChain imports
from langchain.agents import AgentType, create_react_agent, initialize_agent
from langchain.chat_models import init_chat_model
from langchain.schema import (
    AIMessage,
    BaseMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
)
from langchain.tools import Tool


@tool(parse_docstring=True)
def get_current_weather(location: str, unit: str):
    """
    Get the current weather in a given location.

    Args:
        location (str): The city and state, e.g. San Francisco, CA.
        unit (str): The unit of temperature, either 'celsius' or 'fahrenheit'.
    """
    return {
        "location": location,
        "temperature": 22 if unit == "celsius" else 72,
        "unit": unit,
    }


def convert_async_generator_to_sync(async_gen):
    """Convert an async generator to a sync generator."""
    q = queue.Queue()
    sentinel = object()

    async def run_async_gen():
        try:
            async for item in async_gen:
                q.put(item)
        finally:
            q.put(sentinel)

    def start_async_loop():
        asyncio.run(run_async_gen())

    thread = threading.Thread(target=start_async_loop)
    thread.start()

    while True:
        item = q.get()
        if item is sentinel:
            break
        yield item

    thread.join()


class AIAgentService:
    """Service class for AI-related operations using LangChain."""

    def __init__(self, conversation):
        """Ensure that the AI configuration is set properly."""
        if settings.AI_API_KEY is None or settings.AI_MODEL is None:
            raise ImproperlyConfigured("LangChainAgentService configuration not set")

        self.model = init_chat_model(
            openai_api_key=settings.AI_API_KEY,
            model=settings.AI_MODEL,
            model_provider="openai",
            base_url=settings.AI_BASE_URL,
        )
        self.conversation = conversation

    @staticmethod
    def _convert_to_langchain_messages(messages: List[UIMessage]) -> List[BaseMessage]:
        lc_messages = []
        for message in messages:
            logger.info(f"Converting message: {message}")
            content = []
            # Handle main parts
            for part in message.parts:
                if part.type == "text":
                    content.append({"type": "text", "text": part.text})
                    # content.append(part.text)
                elif part.type == "tool-invocation":
                    # Represent tool invocation as a FunctionMessage
                    tool_invocation = part.toolInvocation
                    lc_messages.append(
                        FunctionMessage(
                            name=tool_invocation.toolName, content=json.dumps(tool_invocation.args)
                        )
                    )
                elif part.type == "image":
                    # Represent image as a string with a tag or metadata
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": part.url},
                        }
                    )
                    # content.append(f"[image: {getattr(part, 'url', '')}]")
                elif part.type == "file":
                    # Represent file as a string with a tag or metadata
                    content.append(
                        f"[file: {getattr(part, 'name', '')} {getattr(part, 'url', '')}]"
                    )
                # Add more types as needed

            # Handle experimental_attachments if present
            if hasattr(message, "experimental_attachments") and message.experimental_attachments:
                for attachment in message.experimental_attachments:
                    if getattr(attachment, "contentType", "").startswith("image"):
                        content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": attachment.url},
                            }
                        )
                    elif getattr(attachment, "contentType", "").startswith("text"):
                        content.append(
                            f"[file: {getattr(attachment, 'name', '')} {getattr(attachment, 'url', '')}]"
                        )

            # Compose the message
            lc_messages.append(
                {
                    "role": message.role,
                    "content": content,
                }
            )
            # if message.role == "system":
            #    lc_messages.append(SystemMessage(content=content))
            # elif message.role == "user":
            #    lc_messages.append(HumanMessage(content=content))
            # elif message.role == "assistant":
            #    lc_messages.append(AIMessage(content=content))
            # FunctionMessage already appended above for tool-invocation
            # Add more roles/types as needed
        return lc_messages

    def stream_data(self, messages: List[UIMessage]):  # noqa: PLR0912
        lc_messages = self._convert_to_langchain_messages(messages)
        logger.info("[LangChain stream_data_async] Received messages: %s", lc_messages)

        tools = [get_current_weather]

        from langchain_core.prompts import ChatPromptTemplate
        from langgraph.prebuilt import create_react_agent
        from langgraph.prebuilt.chat_agent_executor import AgentState

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a helpful assistant."),
                ("placeholder", "{messages}"),
            ]
        )

        langgraph_agent_executor = create_react_agent(self.model, tools, prompt=prompt)

        finish_reason = "stop"

        _current_tool_call_id = None
        _current_tool_call_arguments = ""
        for stream_mode, step in langgraph_agent_executor.stream(
            {"messages": lc_messages},
            stream_mode=["messages", "values"],
        ):
            # (
            #     AIMessageChunk(
            #         content=" with",
            #         additional_kwargs={},
            #         response_metadata={},
            #         id="run--c9fbf725-0ca0-408f-8158-da347a26b64b",
            #     ),
            #     {
            #         "langgraph_step": 1,
            #         "langgraph_node": "agent",
            #         "langgraph_triggers": ("branch:to:agent",),
            #         "langgraph_path": ("__pregel_pull", "agent"),
            #         "langgraph_checkpoint_ns": "agent:980f9c50-3cfa-6522-f9be-de139f9b4ece",
            #         "checkpoint_ns": "agent:980f9c50-3cfa-6522-f9be-de139f9b4ece",
            #         "ls_provider": "openai",
            #         "ls_model_name": "ai/smollm2",
            #         "ls_model_type": "chat",
            #         "ls_temperature": None,
            #     },
            # )
            if stream_mode == "messages":
                chunk, metadata = step

                try:
                    logger.info(
                        "[LangChain stream_data_async] Received chunk: %s %s", type(chunk), chunk
                    )
                    if isinstance(chunk, AIMessageChunk):
                        if chunk.tool_call_chunks:
                            for tool_call_chunk in chunk.tool_call_chunks:
                                # Handle tool call chunks
                                if tool_call_chunk["id"]:
                                    _current_tool_call_id = tool_call_chunk["id"]
                                    _tool_name = tool_call_chunk["name"]
                                    logger.info(
                                        "[LangChain stream_data_async] Tool call chunk: %s %s",
                                        _current_tool_call_id,
                                        _tool_name,
                                    )
                                    # yield f'b:{{"toolCallId":"{_current_tool_call_id}","toolName":"{_tool_name}"}}\n'

                                else:
                                    _argument_delta = tool_call_chunk["args"]
                                    _current_tool_call_arguments += _argument_delta
                                    logger.info(
                                        "[LangChain stream_data_async] Tool call argument delta: %s %s",
                                        _current_tool_call_id,
                                        _argument_delta,
                                    )
                                    # yield f'c:{{"toolCallId":"{_current_tool_call_id}","argsTextDelta":"{_argument_delta}"}}\n'
                        elif chunk.response_metadata.get("finish_reason"):
                            finish_reason = chunk.response_metadata["finish_reason"]
                            logger.info(
                                "[LangChain stream_data_async] Finish reason: %s", finish_reason
                            )
                        else:
                            yield f"0:{json.dumps(chunk.content)}\n"
                    elif isinstance(chunk, ToolMessage) and chunk.content:
                        _tool_call = {
                            "toolCallId": chunk.tool_call_id,
                            "toolName": chunk.name,
                            "args": json.loads(_current_tool_call_arguments),
                        }
                        yield f"9:{json.dumps(_tool_call)}\n"
                        # content='{"location": "Paris, France", "temperature": 22, "unit": "celsius"}' name='get_current_weather' id='159415d7-046d-43bf-982e-8a69cb50a486' tool_call_id='qk6PXRocvUzh9QTQS6HQNI5qpNujsrzr'
                        _tool_result_part = {
                            "toolCallId": chunk.tool_call_id,
                            "toolName": chunk.name,
                            "result": json.loads(chunk.content),
                        }
                        _current_tool_call_id = None
                        _current_tool_call_arguments = ""
                        yield f"a:{json.dumps(_tool_result_part)}\n"
                    else:
                        yield f"0:{json.dumps(chunk.content)}\n"

                except Exception as e:
                    logger.exception("Error in LangChain stream_data_async")
                    yield f"3:{json.dumps(str(e))}\n"
                    finish_reason = "error"

            elif stream_mode == "values":
                logger.info("[LangChain stream_data_async] Received values: %s", step)
                last_message = step["messages"][-1]
                # if isinstance(last_message, AIMessage) and last_message.tool_calls:
                #    for tool_call in last_message.tool_calls:
                #        _tool_call = {
                #            "toolCallId": tool_call["id"],
                #            "toolName": tool_call["name"],
                #            "args": tool_call["args"],
                #        }
                #        yield f"9:{json.dumps(_tool_call)}\n"

        # Simulate finish message
        _finish_message = {
            "finishReason": finish_reason,
            "usage": {},  # LangChain does not provide token usage by default
        }
        yield f"d:{json.dumps(_finish_message)}\n"

    def _update_conversation(
        self,
        input_messages,
        result_raw_responses,
        response_usage,
    ):
        # For now, just save the input and output messages
        # self.conversation.langchain_messages = input_messages
        self.conversation.messages = self.conversation.ui_messages + [
            {"content": str(result_raw_responses)}
        ]
        self.conversation.save()

    def _convert_langchain_output_to_ui_messages(self, output):
        # Convert LangChain output to UI messages (simple version)
        ui_messages = []
        if isinstance(output, str):
            text_parts = [TextUIPart(type="text", text=output)]
            ui_messages.append(
                UIMessage(
                    id=str(uuid.uuid4()),
                    role="assistant",
                    parts=text_parts,
                    content=output,
                )
            )
        # Add more conversion logic as needed
        return ui_messages
