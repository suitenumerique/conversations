"""Unit tests for document_search_rag tool."""

import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import RunUsage

from chat.tools.document_search_rag import add_document_rag_search_tool


def test_document_search_rag_schema_accepts_document_id():
    """The tool schema must expose document_id as an optional argument."""
    agent = Agent("test")
    add_document_rag_search_tool(agent)

    schema = agent._function_toolset.tools["document_search_rag"].function_schema.json_schema  # pylint: disable=protected-access

    assert "query" in schema["properties"]
    assert "document_id" in schema["properties"]
    assert schema["required"] == ["query"]


@pytest.mark.asyncio
async def test_document_search_rag_forwards_document_id_to_backend(settings):
    """The optional document_id argument must target and forward selected document."""
    settings.RAG_DOCUMENT_SEARCH_BACKEND = (
        "chat.agent_rag.document_rag_backends.albert_rag_backend.AlbertRagBackend"
    )

    mock_backend = mock.Mock()
    mock_backend.search.return_value = SimpleNamespace(
        data=[SimpleNamespace(url="doc1.pdf", content="snippet")],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
    )
    mock_backend_factory = mock.Mock(return_value=mock_backend)

    agent = Agent("test")
    add_document_rag_search_tool(agent)

    attachment_1_id = uuid.uuid4()
    attachment_2_id = uuid.uuid4()
    run_ctx = RunContext(
        model="test",
        usage=RunUsage(),
        deps=SimpleNamespace(
            conversation=SimpleNamespace(
                collection_id="123",
                attachments=SimpleNamespace(
                    filter=mock.Mock(
                        return_value=SimpleNamespace(
                            order_by=mock.Mock(
                                return_value=[
                                    SimpleNamespace(
                                        id=attachment_1_id,
                                        file_name="doc_a.md",
                                        conversion_from=None,
                                    ),
                                    SimpleNamespace(
                                        id=attachment_2_id,
                                        file_name="dark_matter.pdf.md",
                                        conversion_from="123/attachments/dark_matter.pdf",
                                    ),
                                ]
                            )
                        )
                    )
                ),
            ),
            session={"trace": "abc"},
        ),
    )

    with mock.patch(
        "chat.tools.document_search_rag.import_string", return_value=mock_backend_factory
    ):
        result = agent._function_toolset.tools["document_search_rag"].function(  # pylint: disable=protected-access
            run_ctx,
            query="test query",
            document_id=str(attachment_2_id),
        )

    mock_backend_factory.assert_called_once_with("123")
    mock_backend.search.assert_called_once_with(
        "test query",
        session={"trace": "abc"},
        document_name="dark_matter.pdf",
    )
    assert result.metadata == {"sources": {"doc1.pdf"}}
