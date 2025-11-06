"""Tests for document_summarize functionality."""

import io
from unittest import mock

from django.core.files.storage import default_storage

import pytest
from pydantic_ai import ModelResponse, RunContext, TextPart
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from chat.agents.summarize import SummarizationAgent
from chat.llm_configuration import LLModel, LLMProvider
from chat.tools.document_summarize import document_summarize, summarize_chunk


@pytest.fixture(autouse=True)
def fixture_summarization_agent_config(settings):
    """Fixture to set used settings for agent configuration."""
    settings.LLM_CONFIGURATIONS = {
        settings.LLM_SUMMARIZATION_MODEL_HRID: LLModel(
            hrid="mistral-model",
            model_name="mistral-7b-instruct-v0.1",
            human_readable_name="Mistral 7B Instruct",
            profile=None,
            provider=LLMProvider(
                hrid="mistral",
                kind="mistral",
                base_url="https://api.mistral.ai/v1",
                api_key="testkey",
            ),
            is_active=True,
            system_prompt="direct",
            tools=[],
        ),
    }


@pytest.fixture(name="mocked_context")
def fixture_mocked_context():
    """Fixture for a mocked RunContext."""
    mock_ctx = mock.Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)
    mock_ctx.max_retries = 2
    mock_ctx.retries = {}
    return mock_ctx


def mocked_summary(_messages, _info=None):
    """Mocked summary response."""
    return ModelResponse(parts=[TextPart(content="This is a summary of the test chunk.")])


@pytest.mark.asyncio
async def test_summarize_chunk_returns_summary(mocked_context):
    """Test that summarize_chunk returns a summary."""
    summarization_agent = SummarizationAgent()

    with summarization_agent.override(model=FunctionModel(mocked_summary)):
        chunk = "This is a test chunk of text that needs to be summarized."

        result = await summarize_chunk(1, chunk, 1, summarization_agent, mocked_context)

        assert result == "This is a summary of the test chunk."


@pytest.mark.asyncio
async def test_summarize_chunk_raises_model_retry_on_error(mocked_context):
    """Test that summarize_chunk raises ModelRetry when agent fails."""
    summarization_agent = SummarizationAgent()

    def mocked_summary_error(_messages, _info=None):
        """Mocked summary that raises an error."""
        raise ValueError("Simulated LLM error")

    with summarization_agent.override(model=FunctionModel(mocked_summary_error)):
        chunk = "This is a test chunk."

        with pytest.raises(ModelRetry) as exc_info:
            await summarize_chunk(1, chunk, 1, summarization_agent, mocked_context)

        assert "An error occurred while summarizing a part of the document chunk" in str(
            exc_info.value
        )


@pytest.mark.asyncio
async def test_summarize_chunk_handles_empty_response(mocked_context):
    """Test that summarize_chunk handles empty responses from the agent."""
    summarization_agent = SummarizationAgent()

    def mocked_empty_summary(_messages, _info=None):
        """Mocked summary that returns empty content."""
        return ModelResponse(parts=[TextPart(content="")])

    with summarization_agent.override(model=FunctionModel(mocked_empty_summary)):
        chunk = "This is a test chunk."

        # Empty responses cause ModelRetry since pydantic-ai considers them invalid
        with pytest.raises(ModelRetry):
            await summarize_chunk(1, chunk, 1, summarization_agent, mocked_context)


@pytest.mark.asyncio
async def test_document_summarize_single_document(
    settings, mocked_context, mock_summarization_agent
):
    """Test document_summarize with a single document."""
    settings.SUMMARIZATION_CHUNK_SIZE = 100
    settings.SUMMARIZATION_OVERLAP_SIZE = 10
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    # Create mock conversation with a text attachment
    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "test_doc.txt"
    mock_attachment.file_name = "test_doc.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    # Mock file storage
    file_content = "This is a test document. " * 20  # Create a document with some content
    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        call_count = {"chunk": 0, "merge": 0}

        def mocked_summary_full(messages, _info=None):
            """Mocked summary for full flow."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" in messages_text:
                call_count["merge"] += 1
                return ModelResponse(
                    parts=[TextPart(content="# Final Summary\n\nThis is the final merged summary.")]
                )

            call_count["chunk"] += 1
            return ModelResponse(
                parts=[TextPart(content=f"Summary of chunk {call_count['chunk']}")]
            )

        with mock_summarization_agent(FunctionModel(mocked_summary_full)):
            result = await document_summarize(mocked_context, instructions=None)

        assert result.return_value == "# Final Summary\n\nThis is the final merged summary."
        assert result.metadata["sources"] == {"test_doc.txt"}
        assert call_count["merge"] == 1


@pytest.mark.asyncio
async def test_document_summarize_multiple_documents(
    settings, mocked_context, mock_summarization_agent
):
    """Test document_summarize with multiple documents."""
    settings.SUMMARIZATION_CHUNK_SIZE = 50
    settings.SUMMARIZATION_OVERLAP_SIZE = 5
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    # Create mock conversation with multiple text attachments
    mock_conversation = mock.Mock()
    mock_attachment1 = mock.Mock()
    mock_attachment1.key = "doc1.txt"
    mock_attachment1.file_name = "doc1.txt"
    mock_attachment1.content_type = "text/plain"

    mock_attachment2 = mock.Mock()
    mock_attachment2.key = "doc2.txt"
    mock_attachment2.file_name = "doc2.txt"
    mock_attachment2.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment1, mock_attachment2]

    file_content1 = "Content of document one. " * 10
    file_content2 = "Content of document two. " * 10

    def mock_open_side_effect(key):
        """Mock file opening based on key."""
        if key == "doc1.txt":
            return io.BytesIO(file_content1.encode("utf-8"))
        return io.BytesIO(file_content2.encode("utf-8"))

    with mock.patch.object(default_storage, "open", side_effect=mock_open_side_effect):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_summary_multi(messages, _info=None):
            """Mocked summary for multiple documents."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" in messages_text:
                return ModelResponse(parts=[TextPart(content="Combined summary of all documents")])

            return ModelResponse(parts=[TextPart(content="Chunk summary")])

        with mock_summarization_agent(FunctionModel(mocked_summary_multi)):
            result = await document_summarize(mocked_context, instructions=None)

        assert result.return_value == "Combined summary of all documents"
        assert result.metadata["sources"] == {"doc1.txt", "doc2.txt"}


@pytest.mark.asyncio
async def test_document_summarize_with_custom_instructions(
    settings, mocked_context, mock_summarization_agent
):
    """Test document_summarize with custom instructions."""
    settings.SUMMARIZATION_CHUNK_SIZE = 100
    settings.SUMMARIZATION_OVERLAP_SIZE = 10
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        captured_merge_prompt = []

        def mocked_summary_with_instructions(messages, _info=None):
            """Mocked summary that captures merge prompt."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" in messages_text:
                captured_merge_prompt.append(messages_text)
                return ModelResponse(parts=[TextPart(content="Summary in 2 paragraphs")])

            return ModelResponse(parts=[TextPart(content="Chunk summary")])

        with mock_summarization_agent(FunctionModel(mocked_summary_with_instructions)):
            result = await document_summarize(
                mocked_context, instructions="summary in 2 paragraphs"
            )

        assert result.return_value == "Summary in 2 paragraphs"
        assert len(captured_merge_prompt) == 1
        assert "summary in 2 paragraphs" in captured_merge_prompt[0]


@pytest.mark.asyncio
async def test_document_summarize_no_text_attachments(mocked_context, mock_summarization_agent):
    """Test document_summarize returns error message when no text documents found."""
    mock_conversation = mock.Mock()
    mock_conversation.attachments.filter.return_value = []

    # Set up mocked_context with conversation
    mocked_context.deps = mock.Mock()
    mocked_context.deps.conversation = mock_conversation

    # The decorator @last_model_retry_soft_fail catches ModelCannotRetry and returns a message
    # We still need to provide a mock agent even if it won't be called
    with mock_summarization_agent(FunctionModel(mocked_summary)):
        result = await document_summarize(mocked_context, instructions=None)

    assert "No text documents found in the conversation" in result


@pytest.mark.asyncio
async def test_document_summarize_error_reading_document(mocked_context, mock_summarization_agent):
    """Test document_summarize handles errors when reading documents."""
    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    with mock.patch.object(default_storage, "open", side_effect=IOError("File read error")):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        # The decorator @last_model_retry_soft_fail catches ModelCannotRetry and returns a message
        # We still need to provide a mock agent even if it won't be called
        with mock_summarization_agent(FunctionModel(mocked_summary)):
            result = await document_summarize(mocked_context, instructions=None)

        assert "An unexpected error occurred during document summarization" in result


@pytest.mark.asyncio
async def test_document_summarize_error_during_chunk_summarization(
    settings, mocked_context, mock_summarization_agent
):
    """Test document_summarize handles ModelRetry during chunk summarization."""
    settings.SUMMARIZATION_CHUNK_SIZE = 100
    settings.SUMMARIZATION_OVERLAP_SIZE = 10
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_summary_error(messages, _info=None):
            """Mocked summary that raises an error during chunks."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" not in messages_text:
                raise ValueError("Chunk processing error")

            return ModelResponse(parts=[TextPart(content="Final summary")])

        with mock_summarization_agent(FunctionModel(mocked_summary_error)):
            with pytest.raises(ModelRetry):
                await document_summarize(mocked_context, instructions=None)


@pytest.mark.asyncio
async def test_document_summarize_error_during_merge(
    settings, mocked_context, mock_summarization_agent
):
    """Test document_summarize handles errors during final merge."""
    settings.SUMMARIZATION_CHUNK_SIZE = 100
    settings.SUMMARIZATION_OVERLAP_SIZE = 10
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_summary_merge_error(messages, _info=None):
            """Mocked summary that raises an error during merge."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" in messages_text:
                raise ValueError("Merge error")

            return ModelResponse(parts=[TextPart(content="Chunk summary")])

        with mock_summarization_agent(FunctionModel(mocked_summary_merge_error)):
            with pytest.raises(ModelRetry) as exc_info:
                await document_summarize(mocked_context, instructions=None)

            # Should raise ModelRetry regardless of which phase failed
            assert "An error occurred" in str(exc_info.value)


@pytest.mark.asyncio
async def test_document_summarize_empty_result(settings, mocked_context, mock_summarization_agent):
    """Test document_summarize raises ModelRetry when summarization produces empty result."""
    settings.SUMMARIZATION_CHUNK_SIZE = 100
    settings.SUMMARIZATION_OVERLAP_SIZE = 10
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_empty_summary(messages, _info=None):
            """Mocked summary that returns empty for merge."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" in messages_text:
                return ModelResponse(parts=[TextPart(content="   ")])

            return ModelResponse(parts=[TextPart(content="Chunk summary")])

        with mock_summarization_agent(FunctionModel(mocked_empty_summary)):
            with pytest.raises(ModelRetry) as exc_info:
                await document_summarize(mocked_context, instructions=None)

            # Should raise ModelRetry with the specific message
            assert "The summarization produced an empty result" in str(exc_info.value)


@pytest.mark.asyncio
async def test_document_summarize_large_document_multiple_chunks(
    settings, mocked_context, mock_summarization_agent
):
    """Test document_summarize with a large document requiring multiple chunks."""
    settings.SUMMARIZATION_CHUNK_SIZE = 20  # Small chunk size to force multiple chunks
    settings.SUMMARIZATION_OVERLAP_SIZE = 5
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2

    mock_conversation = mock.Mock()
    mock_attachment = mock.Mock()
    mock_attachment.key = "large_doc.txt"
    mock_attachment.file_name = "large_doc.txt"
    mock_attachment.content_type = "text/plain"

    mock_conversation.attachments.filter.return_value = [mock_attachment]

    # Create a large document
    file_content = "This is a word. " * 100  # Should create multiple chunks

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        # Set up mocked_context with conversation
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        chunk_count = {"count": 0}

        def mocked_summary_multi_chunks(messages, _info=None):
            """Mocked summary that counts chunks."""
            messages_text = messages[0].parts[-1].content

            if "Produce a coherent synthesis" in messages_text:
                return ModelResponse(
                    parts=[TextPart(content=f"Final summary of {chunk_count['count']} chunks")]
                )

            chunk_count["count"] += 1
            return ModelResponse(
                parts=[TextPart(content=f"Summary of chunk {chunk_count['count']}")]
            )

        with mock_summarization_agent(FunctionModel(mocked_summary_multi_chunks)):
            result = await document_summarize(mocked_context, instructions=None)

        assert "Final summary of" in result.return_value
        assert chunk_count["count"] > 1  # Ensure multiple chunks were processed
