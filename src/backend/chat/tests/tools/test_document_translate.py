"""Tests for document_translate functionality."""

import io
from unittest import mock

from django.core.files.storage import default_storage

import pytest
from pydantic_ai import ModelResponse, RunContext, TextPart
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from chat.llm_configuration import LLModel, LLMProvider
from chat.tools.document_translate import document_translate


@pytest.fixture(autouse=True)
def fixture_translation_agent_config(settings):
    """Fixture to set used settings for agent configuration."""
    settings.TRANSLATION_MAX_CHARS = 100_000
    settings.LLM_CONFIGURATIONS = {
        settings.LLM_DEFAULT_MODEL_HRID: LLModel(
            hrid="mistral-model",
            model_name="mistral-medium-2508",
            human_readable_name="Mistral Medium 2508",
            profile=None,
            provider=LLMProvider(
                hrid="mistral-medium-2508",
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


def _mock_attachments_queryset(attachment):
    """Create a mock queryset that chains .filter().order_by().afirst() returning the attachment."""
    mock_qs = mock.Mock()
    mock_qs.order_by.return_value = mock_qs
    mock_qs.afirst = mock.AsyncMock(return_value=attachment)

    mock_attachments = mock.Mock()
    mock_attachments.filter.return_value = mock_qs
    return mock_attachments


def mocked_translation(_messages, _info=None):
    """Mocked translation response."""
    return ModelResponse(parts=[TextPart(content="Ceci est une traduction du document.")])


@pytest.mark.asyncio
async def test_document_translate_single_document(mocked_context, mock_translation_agent):
    """Test document_translate with a single document."""
    mock_attachment = mock.Mock()
    mock_attachment.key = "test_doc.txt"
    mock_attachment.file_name = "test_doc.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    file_content = "This is a test document. " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_translate_full(_message, _info=None):
            """Mocked translation for full flow."""
            return ModelResponse(parts=[TextPart(content="Ceci est un document de test.")])

        with mock_translation_agent(FunctionModel(mocked_translate_full)):
            result = await document_translate(
                mocked_context, target_language="French", instructions=None
            )

        assert "Ceci est un document de test." in result.return_value
        assert result.metadata["sources"] == {"test_doc.txt"}


@pytest.mark.asyncio
async def test_document_translate_uses_last_document(mocked_context, mock_translation_agent):
    """Test document_translate uses the last uploaded document."""
    mock_attachment = mock.Mock()
    mock_attachment.key = "latest_doc.txt"
    mock_attachment.file_name = "latest_doc.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    file_content = "Content of the latest document."

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        with mock_translation_agent(FunctionModel(mocked_translation)):
            result = await document_translate(
                mocked_context, target_language="French", instructions=None
            )

        assert result.metadata["sources"] == {"latest_doc.txt"}
        # Verify order_by was called with -created_at
        mock_conversation.attachments.filter.return_value.order_by.assert_called_once_with(
            "-created_at"
        )


@pytest.mark.asyncio
async def test_document_translate_with_custom_instructions(mocked_context, mock_translation_agent):
    """Test document_translate with custom instructions."""
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        captured_prompts = []

        def mocked_translate_with_instructions(messages, _info=None):
            """Mocked translation that captures prompt."""
            messages_text = messages[0].parts[-1].content
            captured_prompts.append(messages_text)
            return ModelResponse(parts=[TextPart(content="Traduction formelle")])

        with mock_translation_agent(FunctionModel(mocked_translate_with_instructions)):
            result = await document_translate(
                mocked_context, target_language="French", instructions="Use formal tone"
            )

        assert result.return_value is not None
        assert len(captured_prompts) == 1
        assert "Use formal tone" in captured_prompts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("target_language", [None, ""])
async def test_document_translate_no_target_language(
    target_language, mocked_context, mock_translation_agent
):
    """Test document_translate asks the user for language when target_language is not specified."""
    mocked_context.deps = mock.Mock()

    with mock_translation_agent(FunctionModel(mocked_translation)):
        result = await document_translate(
            mocked_context, target_language=target_language, instructions=None
        )

    assert "target language is not specified" in result


@pytest.mark.asyncio
async def test_document_translate_no_text_attachments(mocked_context, mock_translation_agent):
    """Test document_translate returns error message when no text documents found."""
    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(None)

    mocked_context.deps = mock.Mock()
    mocked_context.deps.conversation = mock_conversation

    with mock_translation_agent(FunctionModel(mocked_translation)):
        result = await document_translate(
            mocked_context, target_language="French", instructions=None
        )

    assert "No text documents found in the conversation" in result


@pytest.mark.asyncio
async def test_document_translate_error_reading_document(mocked_context, mock_translation_agent):
    """Test document_translate handles errors when reading documents."""
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    with mock.patch.object(default_storage, "open", side_effect=IOError("File read error")):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        with mock_translation_agent(FunctionModel(mocked_translation)):
            result = await document_translate(
                mocked_context, target_language="French", instructions=None
            )

        assert "An unexpected error occurred during document translation" in result


@pytest.mark.asyncio
async def test_document_translate_error_during_translation(mocked_context, mock_translation_agent):
    """Test document_translate handles ModelRetry during translation."""
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_translate_error(_messages, _info=None):
            """Mocked translation that raises an error."""
            raise ValueError("Translation error")

        with mock_translation_agent(FunctionModel(mocked_translate_error)):
            with pytest.raises(ModelRetry):
                await document_translate(
                    mocked_context, target_language="French", instructions=None
                )


@pytest.mark.asyncio
async def test_document_translate_too_large(settings, mocked_context, mock_translation_agent):
    """Test document_translate rejects documents exceeding max chars."""
    settings.TRANSLATION_MAX_CHARS = 100  # Very small limit

    mock_attachment = mock.Mock()
    mock_attachment.key = "large_doc.txt"
    mock_attachment.file_name = "large_doc.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    file_content = "This is a word. " * 100  # Much larger than 100 chars

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        with mock_translation_agent(FunctionModel(mocked_translation)):
            result = await document_translate(
                mocked_context, target_language="French", instructions=None
            )

        assert "too large to translate" in result


@pytest.mark.asyncio
async def test_document_translate_empty_result(mocked_context, mock_translation_agent):
    """Test document_translate raises ModelRetry when translation produces empty result."""
    mock_attachment = mock.Mock()
    mock_attachment.key = "test.txt"
    mock_attachment.file_name = "test.txt"
    mock_attachment.content_type = "text/plain"
    mock_attachment.size = None

    mock_conversation = mock.Mock()
    mock_conversation.attachments = _mock_attachments_queryset(mock_attachment)

    file_content = "Test content " * 20

    with mock.patch.object(
        default_storage, "open", return_value=io.BytesIO(file_content.encode("utf-8"))
    ):
        mocked_context.deps = mock.Mock()
        mocked_context.deps.conversation = mock_conversation

        def mocked_empty_translation(_messages, _info=None):
            """Mocked translation that returns empty."""
            return ModelResponse(parts=[TextPart(content="   ")])

        with mock_translation_agent(FunctionModel(mocked_empty_translation)):
            with pytest.raises(ModelRetry) as exc_info:
                await document_translate(
                    mocked_context, target_language="French", instructions=None
                )

            assert "produced an empty result" in str(exc_info.value)
