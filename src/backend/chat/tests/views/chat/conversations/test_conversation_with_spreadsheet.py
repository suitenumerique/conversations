"""
End-to-end: a CSV attached to a message is not RAG-parsed; the model gets the tabular
tools, calls query_table, and the eager Celery task computes the answer from the file.
"""

import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
import respx
from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from rest_framework import status

from core.file_upload.enums import AttachmentStatus

from chat.ai_sdk_types import FileUIPart, TextUIPart, UIMessage
from chat.factories import ChatConversationAttachmentFactory, ChatConversationFactory

pytestmark = pytest.mark.django_db(transaction=True)

SALES_CSV = "région;montant\nNord;1 000,5\nSud;4\nNord;1,5\n".encode("cp1252")
QUERY = {
    "table": "ventes",
    "filters": [{"column": "region", "op": "==", "value": "Nord"}],
    "aggregations": [{"func": "sum", "column": "montant"}],
}


@pytest.fixture(autouse=True)
def ai_settings(settings):
    """Configure the agent instructions."""
    settings.AI_AGENT_INSTRUCTIONS = "You are a helpful test assistant :)"
    return settings


@respx.mock  # no route: any RAG backend call would fail the test
def test_post_conversation_with_csv_answers_through_query_table(api_client, mock_ai_agent_service):
    """The CSV is queried with query_table instead of being parsed into the RAG store."""
    conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=conversation.owner)
    attachment = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        file_name="ventes.csv",
        content_type="text/csv",
        upload_state=AttachmentStatus.READY,
    )
    default_storage.save(attachment.key, ContentFile(SALES_CSV))

    tool_results = []

    async def agent_model(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            assert {"describe_tables", "query_table"} <= {tool.name for tool in info.function_tools}
            assert '["ventes.csv"]' in messages[0].instructions
            yield {0: DeltaToolCall(name="query_table", json_args=json.dumps(QUERY))}
        else:
            last_request = messages[-1]
            assert isinstance(last_request, ModelRequest)
            tool_results.extend(
                part.content for part in last_request.parts if isinstance(part, ToolReturnPart)
            )
            yield "Nord totals 1002."

    message = UIMessage(
        id="1",
        role="user",
        content="Total for Nord?",
        parts=[
            TextUIPart(text="Total for Nord?", type="text"),
            FileUIPart(
                type="file",
                filename="ventes.csv",
                mediaType="text/csv",
                url=f"/media-key/{attachment.key}",
            ),
        ],
    )

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    content = b"".join(response.streaming_content).decode("utf-8")

    assert "document_parsing" not in content
    assert tool_results == ["| montant_sum |\n|---|\n| 1002 |"]
    conversation.refresh_from_db()
    assert conversation.collection_id is None


# An aggregation query_table does not offer: the model keeps sending it.
UNSUPPORTED_QUERY = {"table": "ventes", "aggregations": [{"func": "std", "column": "montant"}]}


@respx.mock
def test_invalid_tool_arguments_end_with_an_answer_not_an_error(
    api_client, mock_ai_agent_service, caplog
):
    """A model that keeps calling a tool with invalid arguments is told to stop, not crashed.

    pydantic-ai rejects the arguments before the tool runs and, once the retries are
    used up, would end the turn with an error.
    """
    conversation = ChatConversationFactory(owner__language="en-us")
    api_client.force_authenticate(user=conversation.owner)
    attachment = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        file_name="ventes.csv",
        content_type="text/csv",
        upload_state=AttachmentStatus.READY,
    )
    default_storage.save(attachment.key, ContentFile(SALES_CSV))

    calls = []
    tool_results = []

    async def agent_model(messages: list[ModelMessage], _info: AgentInfo):
        last_parts = messages[-1].parts
        tool_results.extend(p.content for p in last_parts if isinstance(p, ToolReturnPart))
        if len(messages) == 1 or any(isinstance(p, RetryPromptPart) for p in last_parts):
            calls.append(1)
            yield {0: DeltaToolCall(name="query_table", json_args=json.dumps(UNSUPPORTED_QUERY))}
        else:
            yield "I cannot compute a standard deviation from this file."

    message = UIMessage(
        id="1",
        role="user",
        content="Standard deviation of montant?",
        parts=[TextUIPart(text="Standard deviation of montant?", type="text")],
    )

    with mock_ai_agent_service(FunctionModel(stream_function=agent_model)):
        response = api_client.post(
            f"/api/v1.0/chats/{conversation.pk}/conversation/",
            data={"messages": [message.model_dump(mode="json")]},
            format="json",
        )
        content = b"".join(response.streaming_content).decode("utf-8")

    assert response.status_code == status.HTTP_200_OK
    assert "I cannot compute a standard deviation" in content
    assert len(calls) == 3  # query_table allows 3 tries
    assert len(tool_results) == 1
    assert tool_results[0].startswith(
        "The query_table tool could not be called with valid arguments"
    )
    [line] = [
        r.msg
        for r in caplog.records
        if isinstance(r.msg, dict) and r.msg["event"] == "tool_max_retries_reached"
    ]
    assert line["tool_name"] == "query_table"
    assert line["cause"] == "ValidationError"
    assert "std" not in str(line)
