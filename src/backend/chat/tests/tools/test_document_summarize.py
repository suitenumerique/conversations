"""
Tests for document_summarize.

Real components: Django ORM (factory-built conversation + attachments), real
default_storage (actual content read/write), real RunContext + ContextDeps.

The only thing mocked is the SummarizationAgent's LLM (via FunctionModel) -
the standard pydantic-ai test idiom for driving deterministic model output.
"""

import uuid
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai import ModelResponse, RunContext, TextPart
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from chat.agents.summarize import SummarizationAgent
from chat.clients.schema import ContextDeps
from chat.factories import (
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
    UserFactory,
)
from chat.llm_configuration import LLModel, LLMProvider
from chat.tools.document_summarize import (
    document_summarize,
    document_summarize_project,
    summarize_chunk,
)

# transaction=True is required so writes done via sync_to_async (which run on
# threadpool connections distinct from the test's wrapping transaction) commit
# and are flushed via TRUNCATE between tests instead of leaking across them.
pytestmark = pytest.mark.django_db(transaction=True)


# Setup


@pytest.fixture(autouse=True)
def fixture_summarization_agent_config(settings):
    """Configure the LLM model used by SummarizationAgent."""
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


@pytest.fixture(autouse=True)
def summarization_settings(settings):
    """Sensible defaults for chunking-related settings used by document_summarize."""
    settings.SUMMARIZATION_CHUNK_SIZE = 100
    settings.SUMMARIZATION_OVERLAP_SIZE = 10
    settings.SUMMARIZATION_CONCURRENT_REQUESTS = 2
    return settings


@sync_to_async
def _setup_conversation(attachment_specs):
    """
    Build a conversation, attachments, and a real RunContext in one sync block.

    `attachment_specs` is a list of dicts with keys: file_name, content,
    write (optional, default True).
    Returns (ctx, attachments) where attachments preserves the input order.
    """
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    attachments = []
    for spec in attachment_specs:
        attachment = ChatConversationAttachmentFactory(
            conversation=conversation,
            uploaded_by=user,
            file_name=spec["file_name"],
            content_type="text/plain",
        )
        if spec.get("write", True):
            default_storage.save(attachment.key, ContentFile(spec["content"].encode("utf-8")))
        attachments.append(attachment)
    ctx = RunContext(
        model="test",
        usage=RunUsage(input_tokens=0, output_tokens=0),
        deps=ContextDeps(conversation=conversation, user=user),
        max_retries=2,
        retries={},
        tool_name="document_summarize",
    )
    return ctx, attachments


def mocked_summary(_messages, _info=None):
    """Mocked summary response."""
    return ModelResponse(parts=[TextPart(content="This is a summary of the test chunk.")])


#  pure unit tests


@pytest.fixture(name="mocked_context")
def mocked_context_fixture():
    """Lightweight RunContext stand-in for summarize_chunk - no DB needed."""
    mock_ctx = mock.Mock(spec=RunContext)
    mock_ctx.usage = RunUsage(input_tokens=0, output_tokens=0)
    mock_ctx.max_retries = 2
    mock_ctx.retries = {}
    return mock_ctx


@pytest.mark.asyncio
async def test_summarize_chunk_returns_summary(mocked_context):
    """summarize_chunk returns the model's summary for a chunk."""
    summarization_agent = SummarizationAgent()
    with summarization_agent.override(model=FunctionModel(mocked_summary)):
        result = await summarize_chunk(1, "test chunk", 1, summarization_agent, mocked_context)
    assert result == "This is a summary of the test chunk."


@pytest.mark.asyncio
async def test_summarize_chunk_raises_model_retry_on_error(mocked_context):
    """If the agent raises mid-chunk, summarize_chunk surfaces a ModelRetry."""
    summarization_agent = SummarizationAgent()

    def mocked_summary_error(_messages, _info=None):
        """Mocked summary that raises an error."""
        raise ValueError("Simulated LLM error")

    with summarization_agent.override(model=FunctionModel(mocked_summary_error)):
        with pytest.raises(ModelRetry, match="An error occurred while summarizing"):
            await summarize_chunk(1, "chunk", 1, summarization_agent, mocked_context)


@pytest.mark.asyncio
async def test_summarize_chunk_handles_empty_response(mocked_context):
    """Empty model output is treated as a retryable failure by pydantic-ai."""
    summarization_agent = SummarizationAgent()

    def mocked_empty_summary(_messages, _info=None):
        """Mocked summary that returns empty content."""
        return ModelResponse(parts=[TextPart(content="")])

    with summarization_agent.override(model=FunctionModel(mocked_empty_summary)):
        with pytest.raises(ModelRetry):
            await summarize_chunk(1, "chunk", 1, summarization_agent, mocked_context)


#  tests with real components


@pytest.mark.asyncio
async def test_document_summarize_single_document(mock_summarization_agent):
    """A single document yields a final merged summary; sources include its file name."""
    ctx, _ = await _setup_conversation([{"file_name": "report.txt", "content": "Lorem " * 200}])

    def mocked_summary_full(messages, _info=None):
        """Mocked summary for full flow."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(parts=[TextPart(content="Final merged summary")])
        return ModelResponse(parts=[TextPart(content="Chunk summary")])

    with mock_summarization_agent(FunctionModel(mocked_summary_full)):
        result = await document_summarize(ctx, instructions=None)

    assert result.return_value == "Final merged summary"
    assert result.metadata["sources"] == {"report.txt"}


@pytest.mark.asyncio
async def test_document_summarize_multiple_documents(mock_summarization_agent):
    """All text attachments contribute their content; sources contain every file name."""
    ctx, _ = await _setup_conversation(
        [
            {"file_name": "doc1.txt", "content": "alpha " * 50},
            {"file_name": "doc2.txt", "content": "beta " * 50},
        ]
    )

    def mocked_summary_multi(messages, _info=None):
        """Mocked summary for multiple documents."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(parts=[TextPart(content="Combined summary")])
        return ModelResponse(parts=[TextPart(content="Chunk summary")])

    with mock_summarization_agent(FunctionModel(mocked_summary_multi)):
        result = await document_summarize(ctx, instructions=None)

    assert result.return_value == "Combined summary"
    assert result.metadata["sources"] == {"doc1.txt", "doc2.txt"}


@pytest.mark.asyncio
async def test_document_summarize_document_id_selects_attachment(mock_summarization_agent):
    """document_id restricts summarization to a single attachment."""
    ctx, attachments = await _setup_conversation(
        [
            {"file_name": "doc1.txt", "content": "alpha " * 30},
            {"file_name": "doc2.txt", "content": "beta " * 30},
        ]
    )
    target = attachments[1]

    def mocked_summary_for_selected_doc(messages, _info=None):
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(parts=[TextPart(content="Selected document summary")])
        return ModelResponse(parts=[TextPart(content="Chunk summary")])

    with mock_summarization_agent(FunctionModel(mocked_summary_for_selected_doc)):
        result = await document_summarize(ctx, instructions=None, document_id=str(target.id))

    assert result.return_value == "Selected document summary"
    # Only the targeted document appears in sources.
    assert result.metadata["sources"] == {"doc2.txt"}


@pytest.mark.asyncio
async def test_document_summarize_invalid_document_id(mock_summarization_agent):
    """A non-UUID document_id raises ModelRetry before any chunking begins."""
    ctx, _ = await _setup_conversation([{"file_name": "doc.txt", "content": "ignored"}])

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        with pytest.raises(ModelRetry, match="Expected a valid UUID"):
            await document_summarize(ctx, instructions=None, document_id="not-a-uuid")


@pytest.mark.asyncio
async def test_document_summarize_unknown_document_id(mock_summarization_agent):
    """A valid UUID that doesn't match any attachment raises ModelRetry."""
    ctx, _ = await _setup_conversation([{"file_name": "doc.txt", "content": "ignored"}])

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        with pytest.raises(ModelRetry, match="not found"):
            await document_summarize(ctx, instructions=None, document_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_document_summarize_with_custom_instructions(mock_summarization_agent):
    """User-provided instructions are forwarded into the merge prompt."""
    ctx, _ = await _setup_conversation([{"file_name": "doc.txt", "content": "data " * 80}])

    captured_merge_prompt = []

    def mocked_summary_with_instructions(messages, _info=None):
        """Mocked summary that captures merge prompt."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            captured_merge_prompt.append(prompt)
            return ModelResponse(parts=[TextPart(content="Summary in 2 paragraphs")])
        return ModelResponse(parts=[TextPart(content="Chunk summary")])

    with mock_summarization_agent(FunctionModel(mocked_summary_with_instructions)):
        result = await document_summarize(ctx, instructions="summary in 2 paragraphs")

    assert result.return_value == "Summary in 2 paragraphs"
    assert len(captured_merge_prompt) == 1
    assert "summary in 2 paragraphs" in captured_merge_prompt[0]


@pytest.mark.asyncio
async def test_document_summarize_no_text_attachments(mock_summarization_agent):
    """Conversation without text attachments returns a ModelCannotRetry message."""
    ctx, _ = await _setup_conversation([])  # no attachments

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        result = await document_summarize(ctx, instructions=None)

    assert "No text documents found in the conversation" in result


@pytest.mark.asyncio
async def test_document_summarize_error_reading_document(mock_summarization_agent):
    """If reading the attachment fails (no content in storage), surface a soft-fail message."""
    # Attachment exists in DB but no bytes were written to storage -> open() raises.
    ctx, _ = await _setup_conversation(
        [{"file_name": "missing.txt", "content": "(unused)", "write": False}]
    )

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        result = await document_summarize(ctx, instructions=None)

    assert "None of the attached documents could be read" in result


@pytest.mark.asyncio
async def test_document_summarize_error_during_chunk_summarization(mock_summarization_agent):
    """An error during chunk summarization propagates as ModelRetry."""
    ctx, _ = await _setup_conversation([{"file_name": "doc.txt", "content": "data " * 80}])

    def mocked_summary_error(messages, _info=None):
        """Mocked summary that raises an error during chunks."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" not in prompt:
            raise ValueError("Chunk processing error")
        return ModelResponse(parts=[TextPart(content="Final summary")])

    with mock_summarization_agent(FunctionModel(mocked_summary_error)):
        with pytest.raises(ModelRetry):
            await document_summarize(ctx, instructions=None)


@pytest.mark.asyncio
async def test_document_summarize_error_during_merge(mock_summarization_agent):
    """An error during the final merge propagates as ModelRetry."""
    ctx, _ = await _setup_conversation([{"file_name": "doc.txt", "content": "data " * 80}])

    def mocked_summary_merge_error(messages, _info=None):
        """Mocked summary that raises an error during merge."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            raise ValueError("Merge error")
        return ModelResponse(parts=[TextPart(content="Chunk summary")])

    with mock_summarization_agent(FunctionModel(mocked_summary_merge_error)):
        with pytest.raises(ModelRetry, match="An error occurred"):
            await document_summarize(ctx, instructions=None)


@pytest.mark.asyncio
async def test_document_summarize_empty_result(mock_summarization_agent):
    """A whitespace-only merge output is treated as empty and raises ModelRetry."""
    ctx, _ = await _setup_conversation([{"file_name": "doc.txt", "content": "data " * 80}])

    def mocked_empty_summary(messages, _info=None):
        """Mocked summary that returns empty for merge."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(parts=[TextPart(content="   ")])
        return ModelResponse(parts=[TextPart(content="Chunk summary")])

    with mock_summarization_agent(FunctionModel(mocked_empty_summary)):
        with pytest.raises(ModelRetry, match="The summarization produced an empty result"):
            await document_summarize(ctx, instructions=None)


@pytest.mark.asyncio
async def test_document_summarize_large_document_multiple_chunks(
    mock_summarization_agent, settings
):
    """A large document is split into multiple chunks; the merge sees all of them."""
    settings.SUMMARIZATION_CHUNK_SIZE = 20  # Force many chunks.
    settings.SUMMARIZATION_OVERLAP_SIZE = 5

    ctx, _ = await _setup_conversation([{"file_name": "big.txt", "content": "word " * 200}])

    chunk_count = {"n": 0}

    def mocked_summary_multi_chunks(messages, _info=None):
        """Mocked summary that counts chunks."""
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(
                parts=[TextPart(content=f"Final summary of {chunk_count['n']} chunks")]
            )
        chunk_count["n"] += 1
        return ModelResponse(parts=[TextPart(content=f"Summary of chunk {chunk_count['n']}")])

    with mock_summarization_agent(FunctionModel(mocked_summary_multi_chunks)):
        result = await document_summarize(ctx, instructions=None)

    assert "Final summary of" in result.return_value
    assert chunk_count["n"] > 1


# document_summarize_project: same chunk/merge core as document_summarize, but
# scoped to project-library files. Tests focus on the scope-specific contracts:
# the no-project guard, the no-project-files message, the project IDOR
# boundary, and a happy path proving the shared core is exercised.


@sync_to_async
def _setup_project_conversation(*, project_specs=None, conversation_specs=None):
    """Build a conversation in a project, optionally with attachments on each side.

    `project_specs` and `conversation_specs` follow the same shape as
    `_setup_conversation`'s spec list. Returns
    `(ctx, project_attachments, conversation_attachments)`.
    """
    project_specs = project_specs or []
    conversation_specs = conversation_specs or []

    user = UserFactory()
    project = ChatProjectFactory(owner=user)
    conversation = ChatConversationFactory(owner=user, project=project)

    project_attachments = []
    for spec in project_specs:
        attachment = ChatProjectAttachmentFactory(
            project=project,
            uploaded_by=user,
            file_name=spec["file_name"],
            content_type="text/plain",
        )
        if spec.get("write", True):
            default_storage.save(attachment.key, ContentFile(spec["content"].encode("utf-8")))
        project_attachments.append(attachment)

    conversation_attachments = []
    for spec in conversation_specs:
        attachment = ChatConversationAttachmentFactory(
            conversation=conversation,
            uploaded_by=user,
            file_name=spec["file_name"],
            content_type="text/plain",
        )
        if spec.get("write", True):
            default_storage.save(attachment.key, ContentFile(spec["content"].encode("utf-8")))
        conversation_attachments.append(attachment)

    ctx = RunContext(
        model="test",
        usage=RunUsage(input_tokens=0, output_tokens=0),
        deps=ContextDeps(conversation=conversation, user=user),
        max_retries=2,
        retries={},
        tool_name="document_summarize_project",
    )
    return ctx, project_attachments, conversation_attachments


@pytest.mark.asyncio
async def test_summarize_project_no_project_returns_soft_fail(mock_summarization_agent):
    """A standalone conversation (no project) yields a soft-fail message."""
    ctx, _ = await _setup_conversation([])

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        result = await document_summarize_project(ctx, instructions=None)

    assert "does not belong to a project" in result


@pytest.mark.asyncio
async def test_summarize_project_no_project_files_returns_soft_fail(mock_summarization_agent):
    """A project with zero text attachments yields a clear no-files message."""
    ctx, _, _ = await _setup_project_conversation()

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        result = await document_summarize_project(ctx, instructions=None)

    assert "No text documents found in the project library" in result


@pytest.mark.asyncio
async def test_summarize_project_summarizes_all_project_files(mock_summarization_agent):
    """Without document_id, every project text attachment is summarized."""
    ctx, _, _ = await _setup_project_conversation(
        project_specs=[
            {"file_name": "brief.txt", "content": "alpha " * 30},
            {"file_name": "handbook.txt", "content": "beta " * 30},
        ],
    )

    def mocked(messages, _info=None):
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(parts=[TextPart(content="Project library summary")])
        return ModelResponse(parts=[TextPart(content="chunk")])

    with mock_summarization_agent(FunctionModel(mocked)):
        result = await document_summarize_project(ctx, instructions=None)

    assert result.return_value == "Project library summary"
    assert result.metadata["sources"] == {"brief.txt", "handbook.txt"}


@pytest.mark.asyncio
async def test_summarize_project_targets_one_project_file(mock_summarization_agent):
    """document_id restricts summarization to a single project attachment."""
    ctx, project_attachments, _ = await _setup_project_conversation(
        project_specs=[
            {"file_name": "brief.txt", "content": "alpha " * 30},
            {"file_name": "handbook.txt", "content": "beta " * 30},
        ],
    )
    target = project_attachments[1]

    def mocked(messages, _info=None):
        prompt = messages[0].parts[-1].content
        if "Produce a coherent synthesis" in prompt:
            return ModelResponse(parts=[TextPart(content="Targeted summary")])
        return ModelResponse(parts=[TextPart(content="chunk")])

    with mock_summarization_agent(FunctionModel(mocked)):
        result = await document_summarize_project(
            ctx, instructions=None, document_id=str(target.id)
        )

    assert result.return_value == "Targeted summary"
    assert result.metadata["sources"] == {"handbook.txt"}


@pytest.mark.asyncio
async def test_summarize_project_rejects_conversation_attachment_id(mock_summarization_agent):
    """document_id pointing at a conversation attachment is rejected (IDOR boundary)."""
    ctx, _, conversation_attachments = await _setup_project_conversation(
        project_specs=[{"file_name": "brief.txt", "content": "alpha " * 30}],
        conversation_specs=[{"file_name": "convo.txt", "content": "convo " * 30}],
    )
    convo_attachment_id = str(conversation_attachments[0].id)

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        with pytest.raises(ModelRetry, match="not found"):
            await document_summarize_project(
                ctx, instructions=None, document_id=convo_attachment_id
            )


@pytest.mark.asyncio
async def test_summarize_project_invalid_document_id(mock_summarization_agent):
    """A non-UUID document_id raises ModelRetry before any chunking begins."""
    ctx, _, _ = await _setup_project_conversation(
        project_specs=[{"file_name": "brief.txt", "content": "alpha " * 30}],
    )

    with mock_summarization_agent(FunctionModel(mocked_summary)):
        with pytest.raises(ModelRetry, match="Expected a valid UUID"):
            await document_summarize_project(ctx, instructions=None, document_id="not-a-uuid")
