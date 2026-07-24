"""
Tests for generate_presentation.

Real components: Django ORM (factory-built conversation), real default_storage,
the real pptx template and builder, real RunContext + ContextDeps.

The only thing mocked is the PresentationAgent's LLM (via FunctionModel) - the
standard pydantic-ai idiom for driving deterministic model output.
"""

import re
import uuid
from io import BytesIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.files.storage import default_storage

import pptx
import pytest
from asgiref.sync import sync_to_async
from pydantic_ai import ModelResponse, RunContext
from pydantic_ai.exceptions import AgentRunError, ModelRetry
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from core.file_upload.mixins import AttachmentMixin

from chat.agents.presentation import PresentationAgent
from chat.clients.schema import ContextDeps
from chat.factories import ChatConversationFactory, UserFactory
from chat.file_generation import PresentationBuildError
from chat.llm_configuration import LLModel, LLMProvider
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.generate_presentation import (
    DOWNLOAD_URL_EXPIRATION,
    GENERATED_FOLDER,
    build_object_name,
    generate_presentation,
)

# transaction=True is required so writes done via sync_to_async (which run on
# threadpool connections distinct from the test's wrapping transaction) commit
# and are flushed via TRUNCATE between tests instead of leaking across them.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def fixture_presentation_agent_config(settings):
    """Configure the LLM model used by PresentationAgent."""
    settings.LLM_CONFIGURATIONS = {
        settings.LLM_DEFAULT_MODEL_HRID: LLModel(
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


DECK = {
    "title": "Sobriété énergétique",
    "slides": [
        {"type": "cover", "title": "Sobriété énergétique"},
        {
            "type": "title_one_column",
            "title": "Constats",
            "content": "- Premier **constat**\n- Second constat",
            "slide_notes": "Insister sur le premier point",
        },
    ],
}


def model_returns_deck(deck):
    """Build a FunctionModel callback answering with `deck` as structured output."""

    def respond(_messages, info):
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=deck)])

    return respond


@sync_to_async
def setup_context(max_retries=2):
    """Build a conversation and a real RunContext in one sync block."""
    user = UserFactory()
    conversation = ChatConversationFactory(owner=user)
    ctx = RunContext(
        model="test",
        usage=RunUsage(input_tokens=0, output_tokens=0),
        deps=ContextDeps(conversation=conversation, user=user),
        max_retries=max_retries,
        retries={},
        tool_name="generate_presentation",
    )
    return ctx, conversation, user


async def run_tool(ctx, brief="Un support sur la sobriété énergétique", deck=None):
    """Run the tool with the presentation agent's LLM stubbed out."""
    agent = PresentationAgent()
    with agent.override(model=FunctionModel(model_returns_deck(deck or DECK))):
        with mock.patch("chat.tools.generate_presentation.PresentationAgent", return_value=agent):
            return await generate_presentation(ctx, brief=brief)


def object_key(url):
    """Recover the S3 object key from a presigned URL."""
    path = urlparse(url).path
    return path.split(f"/{default_storage.bucket_name}/", 1)[1]


@pytest.mark.asyncio
async def test_returns_a_signed_time_limited_link():
    """The deck is handed back as a signed URL scoped to the conversation."""
    ctx, conversation, _user = await setup_context()

    result = await run_tool(ctx)

    url = result.metadata["url"]
    assert url in result.return_value

    key = object_key(url)
    assert key.startswith(f"{conversation.pk}/generated/")
    # Readable slug from the deck title, plus a random hex, not a bare UUID.
    assert re.fullmatch(r"sobriete_energetique_[0-9a-f]{8}\.pptx", key.rsplit("/", 1)[1])

    query = parse_qs(urlparse(url).query)
    assert query["X-Amz-Signature"]
    assert query["X-Amz-Expires"] == [str(DOWNLOAD_URL_EXPIRATION)]


@pytest.mark.asyncio
async def test_the_stored_file_is_a_readable_deck():
    """What lands in storage opens as a deck holding the generated slides."""
    ctx, _conversation, _user = await setup_context()

    result = await run_tool(ctx)

    key = object_key(result.metadata["url"])
    blob = await sync_to_async(lambda: default_storage.open(key).read())()
    deck = pptx.Presentation(BytesIO(blob))

    assert len(deck.slides) == 2
    assert deck.slides[0].slide_layout.name == "Titre et sous-titre"
    assert deck.slides[1].notes_slide.notes_text_frame.text == "Insister sur le premier point"


@pytest.mark.asyncio
async def test_no_attachment_row_is_created():
    """Generated decks live in storage only; nothing is recorded in database."""
    ctx, conversation, _user = await setup_context()

    await run_tool(ctx)

    attachment_count = await sync_to_async(conversation.attachments.count)()
    assert attachment_count == 0


@pytest.mark.asyncio
async def test_tells_the_model_not_to_restate_the_deck():
    """The return value steers the model away from repeating the slides in chat."""
    ctx, _conversation, _user = await setup_context()

    result = await run_tool(ctx)

    assert "2 slides" in result.return_value
    assert "do not restate" in result.return_value.lower()


@pytest.mark.asyncio
async def test_a_recoverable_error_is_raised_while_retries_remain():
    """
    While the retry budget is not exhausted, a recoverable error bubbles up as a
    plain ModelRetry so the model gets another attempt.

    This exercises the ``last_model_retry_soft_fail`` "retries remain" branch
    generically, using the empty-brief guard as a convenient trigger. It uses
    ``max_retries=2``; note the tool ships registered with ``retries=1``
    (see ``pydantic_ai.py``), so on this specific tool the first empty brief
    soft-fails immediately rather than reaching here — that deployed behaviour is
    covered by ``test_an_empty_brief_soft_fails_once_retries_run_out``.
    """
    ctx, _conversation, _user = await setup_context(max_retries=2)

    with pytest.raises(ModelRetry, match="brief is empty") as exc_info:
        await run_tool(ctx, brief="   ")

    # A recoverable error, not a terminal one: the model may retry.
    assert not isinstance(exc_info.value, ModelCannotRetry)


@pytest.mark.asyncio
async def test_an_empty_brief_soft_fails_once_retries_run_out():
    """
    Out of retries, the tool returns guidance instead of raising.

    The tool is registered with `retries=1`, so this is what the model actually
    sees on a second empty brief: a message to relay, rather than an exception
    that would let it answer from its own knowledge.
    """
    ctx, _conversation, _user = await setup_context(max_retries=1)

    result = await run_tool(ctx, brief="   ")

    assert "brief is empty" in result


@pytest.mark.asyncio
async def test_nothing_is_written_when_the_brief_is_empty():
    """A rejected brief writes no orphan file to storage."""
    ctx, conversation, _user = await setup_context(max_retries=2)

    with pytest.raises(ModelRetry):
        await run_tool(ctx, brief="")

    _dirs, files = await sync_to_async(default_storage.listdir)(
        f"{conversation.pk}/{GENERATED_FOLDER}"
    )
    assert files == []


@pytest.mark.asyncio
async def test_a_transient_agent_error_is_offered_for_retry():
    """
    A model/API failure while producing the outline is transient: the tool raises
    a plain ModelRetry so the model can try again while it has budget.
    """
    ctx, _conversation, _user = await setup_context(max_retries=2)

    with mock.patch.object(
        PresentationAgent, "run", new_callable=mock.AsyncMock, side_effect=AgentRunError("boom")
    ):
        with pytest.raises(ModelRetry, match="outline could not be produced") as exc_info:
            await generate_presentation(ctx, brief="Un sujet")

    assert not isinstance(exc_info.value, ModelCannotRetry)


@pytest.mark.asyncio
async def test_an_unexpected_agent_error_is_not_retried():
    """
    Anything other than an AgentRunError while producing the outline is a
    server-side bug: it soft-fails to a message string instead of retrying.
    """
    ctx, _conversation, _user = await setup_context()

    with mock.patch.object(
        PresentationAgent, "run", new_callable=mock.AsyncMock, side_effect=RuntimeError("boom")
    ):
        result = await generate_presentation(ctx, brief="Un sujet")

    assert isinstance(result, str)
    assert "outline could not be produced" in result


@pytest.mark.asyncio
async def test_a_build_failure_is_a_server_side_soft_fail():
    """
    The template is bundled with the app, so a build failure is a deployment
    problem, not something a different brief would fix: soft-fail, no retry.
    """
    ctx, _conversation, _user = await setup_context()

    with mock.patch(
        "chat.tools.generate_presentation.build_presentation",
        side_effect=PresentationBuildError("boom"),
    ):
        result = await run_tool(ctx)

    assert isinstance(result, str)
    assert "server-side error" in result


@pytest.mark.asyncio
async def test_a_storage_failure_soft_fails():
    """A deck that builds but cannot be stored soft-fails without a retry."""
    ctx, _conversation, _user = await setup_context()

    with mock.patch(
        "chat.tools.generate_presentation.store_presentation",
        new_callable=mock.AsyncMock,
        side_effect=Exception("boom"),
    ):
        result = await run_tool(ctx)

    assert isinstance(result, str)
    assert "could not be saved" in result


def test_generated_key_cannot_be_served_through_the_media_proxy(settings):
    """
    The download must be reachable ONLY via the presigned URL, never through the
    cookie-authenticated media proxy. The generated key lives under the
    ``generated`` prefix with a readable slug, where the proxy pattern requires the
    ``attachments`` folder and a UUID, so it deliberately fails to match.
    """
    conversation_pk = uuid.uuid4()
    media_path = (
        f"{settings.MEDIA_URL}{conversation_pk}/{GENERATED_FOLDER}/{build_object_name('Deck')}"
    )

    assert AttachmentMixin.MEDIA_STORAGE_URL_PATTERN.search(media_path) is None

    # Control: a UUID-named key under the attachments folder does match, proving
    # the pattern is otherwise live and it is the generated key that evades it.
    attachments = AttachmentMixin.ATTACHMENTS_FOLDER
    uuid_path = f"{settings.MEDIA_URL}{conversation_pk}/{attachments}/{uuid.uuid4()}.pptx"
    assert AttachmentMixin.MEDIA_STORAGE_URL_PATTERN.search(uuid_path) is not None


@pytest.mark.parametrize(
    "title,expected_slug",
    [
        ("Sobriété énergétique", "sobriete_energetique"),
        ("Bilan 2026 / T1 : résultats !", "bilan_2026_t1_resultats"),
        ("   ", "presentation"),  # empty title falls back
        ("///", "presentation"),  # no alphanumerics falls back
        ("A" * 120, "a" * 60),  # long titles are capped
    ],
)
def test_build_object_name_is_readable_and_unguessable(title, expected_slug):
    """The file name is a snake_case slug plus a random hex, ending in .pptx."""
    name = build_object_name(title)
    assert re.fullmatch(rf"{expected_slug}_[0-9a-f]{{8}}\.pptx", name)


def test_build_object_name_hex_suffix_varies():
    """Two calls for the same title yield different, non-guessable names."""
    first = build_object_name("Deck")
    second = build_object_name("Deck")
    assert first != second
