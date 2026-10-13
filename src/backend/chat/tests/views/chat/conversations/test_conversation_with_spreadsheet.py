"""
End-to-end: a CSV attached to a message is not RAG-parsed; the model gets the tabular
tools, calls query_table, and the eager Celery task computes the answer from the file.
"""

import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
import respx
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
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
            assert "ventes.csv" in messages[0].instructions
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
