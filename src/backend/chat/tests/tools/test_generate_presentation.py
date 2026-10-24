"""
Tests for generate_presentation and update_presentation.

Real components: Django ORM (factory-built conversation), real default_storage,
the real pptx template and builder, real RunContext + ContextDeps.

The only thing mocked is the PresentationAgent's LLM (via FunctionModel) - the
standard pydantic-ai idiom for driving deterministic model output.
"""

import contextlib
import re
import uuid
from io import BytesIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import pptx
import pytest
from asgiref.sync import sync_to_async
from pydantic_ai import ModelResponse, RunContext
from pydantic_ai.exceptions import AgentRunError, ModelRetry
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ToolCallPart,
    ToolReturn,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage

from core.file_upload.enums import AttachmentStatus
from core.file_upload.mixins import AttachmentMixin

from chat.agents.presentation import PresentationAgent
from chat.clients.schema import ContextDeps
from chat.factories import (
    ChatConversationAttachmentFactory,
    ChatConversationFactory,
    ChatProjectAttachmentFactory,
    ChatProjectFactory,
    UserFactory,
)
from chat.file_generation import Presentation, PresentationBuildError, PresentationStyle
from chat.llm_configuration import LLModel, LLMProvider
from chat.tokens import count_approx_tokens
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.generate_presentation import (
    DOWNLOAD_URL_EXPIRATION,
    GENERATED_FOLDER,
    StoredPresentation,
    build_object_name,
    generate_presentation,
    update_presentation,
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


def prompts_of(messages):
    """Return the user prompts the presentation agent received."""
    return [
        part.content
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, UserPromptPart)
    ]


@sync_to_async
def setup_context(max_retries=2, project=False):
    """Build a conversation and a real RunContext in one sync block."""
    user = UserFactory()
    conversation = ChatConversationFactory(
        owner=user, project=ChatProjectFactory(owner=user) if project else None
    )
    ctx = RunContext(
        model="test",
        usage=RunUsage(input_tokens=0, output_tokens=0),
        deps=ContextDeps(conversation=conversation, user=user),
        max_retries=max_retries,
        retries={},
        tool_name="generate_presentation",
    )
    return ctx, conversation, user


@sync_to_async
def add_document(conversation, content, *, file_name="note.md", project=None, **kwargs):
    """Attach a text document to the conversation (or to `project`) and store it."""
    if project is not None:
        attachment = ChatProjectAttachmentFactory(
            project=project,
            uploaded_by=conversation.owner,
            file_name=file_name,
            content_type="text/markdown",
            upload_state=AttachmentStatus.READY,
            **kwargs,
        )
    else:
        attachment = ChatConversationAttachmentFactory(
            conversation=conversation,
            uploaded_by=conversation.owner,
            file_name=file_name,
            content_type="text/markdown",
            upload_state=kwargs.pop("upload_state", AttachmentStatus.READY),
            **kwargs,
        )
    if content is not None:
        default_storage.save(attachment.key, ContentFile(content.encode("utf-8")))
    return attachment


@contextlib.contextmanager
def stubbed_agent(respond):
    """
    Replace the presentation agent's LLM with `respond`.

    The agent is still built by the tool, so the arguments it receives (such as
    ``slide_count``) are the real ones; only its model is replaced.
    """
    with contextlib.ExitStack() as stack:

        def build_agent(**agent_kwargs):
            agent = PresentationAgent(**agent_kwargs)
            stack.enter_context(agent.override(model=FunctionModel(respond)))
            return agent

        stack.enter_context(
            mock.patch(
                "chat.tools.generate_presentation.PresentationAgent", side_effect=build_agent
            )
        )
        yield


async def run_tool(
    ctx, brief="Un support sur la sobriété énergétique", deck=None, respond=None, **kwargs
):
    """Run generate_presentation with the presentation agent's LLM stubbed out."""
    with stubbed_agent(respond or model_returns_deck(deck or DECK)):
        return await generate_presentation(ctx, brief=brief, **kwargs)


async def run_update(ctx, respond=None, **kwargs):
    """Run update_presentation with the presentation agent's LLM stubbed out."""
    with stubbed_agent(respond or model_returns_deck(DECK)):
        return await update_presentation(ctx, **kwargs)


@sync_to_async
def persist_tool_returns(conversation, *metadatas):
    """Store earlier turns' tool results carrying `metadatas` in the conversation history."""
    messages = [
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="generate_presentation",
                    content="The presentation was generated.",
                    tool_call_id=f"call-{index}",
                    metadata=metadata,
                )
            ]
        )
        for index, metadata in enumerate(metadatas)
    ]
    conversation.pydantic_messages = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    conversation.save()


def stored_deck(title="Sobriété énergétique", **kwargs):
    """Metadata of a stored deck, as generate_presentation leaves it."""
    deck = {**DECK, "title": title}
    return {"presentation": StoredPresentation(presentation=deck, **kwargs).model_dump(mode="json")}


def object_key(url):
    """Recover the S3 object key from a presigned URL."""
    path = urlparse(url).path
    return path.split(f"/{default_storage.bucket_name}/", 1)[1]


def read_deck(url):
    """Open the stored deck behind a download link."""
    blob = default_storage.open(object_key(url)).read()
    return pptx.Presentation(BytesIO(blob))


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


@pytest.mark.asyncio
async def test_tells_the_model_what_was_not_applied():
    """
    The return value spells out what the deck cannot do, so the model does not
    claim to the user that it was done.
    """
    ctx, _conversation, _user = await setup_context()

    result = await run_tool(ctx)

    assert "charts and diagrams were NOT added" in result.return_value
    assert "never claim otherwise" in result.return_value


@pytest.mark.asyncio
async def test_the_brief_alone_is_used_without_documents():
    """With no document in the conversation, the agent works from the brief only."""
    ctx, _conversation, _user = await setup_context()
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    result = await run_tool(ctx, brief="Un sujet précis", respond=respond)

    assert "Un sujet précis" in received[0]
    assert "Source documents" not in received[0]
    assert "brief only" in result.return_value
    assert result.metadata["sources"] == []


@pytest.mark.asyncio
async def test_conversation_documents_reach_the_agent_verbatim():
    """
    By default, every document of the conversation is handed to the agent, so
    the deck is built from the sources rather than from the main model's brief.
    """
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "Le budget atteint 42 M€.", file_name="rapport.md")
    await add_document(conversation, "Trois axes prioritaires.", file_name="annexe.md")
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    result = await run_tool(ctx, respond=respond)

    assert '<document name="rapport.md">\nLe budget atteint 42 M€.' in received[0]
    assert "Trois axes prioritaires." in received[0]
    assert result.metadata["sources"] == ["rapport.md", "annexe.md"]
    assert "rapport.md, annexe.md" in result.return_value


@pytest.mark.asyncio
async def test_document_ids_select_the_sources():
    """
    `document_ids` narrows the sources, e.g. to leave out a pptx template the
    user attached as a model, and may target project-library files.
    """
    ctx, conversation, _user = await setup_context(project=True)
    await add_document(conversation, "Contenu du rapport", file_name="rapport.md")
    await add_document(conversation, "Titre de la présentation", file_name="gabarit.md")
    project_document = await add_document(
        conversation, "Note du projet", file_name="projet.md", project=conversation.project
    )
    report = await sync_to_async(conversation.attachments.get)(file_name="rapport.md")
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    result = await run_tool(
        ctx, respond=respond, document_ids=[str(report.id), str(project_document.id)]
    )

    assert "Contenu du rapport" in received[0]
    assert "Note du projet" in received[0]
    assert "Titre de la présentation" not in received[0]
    assert result.metadata["sources"] == ["rapport.md", "projet.md"]


@pytest.mark.asyncio
async def test_an_empty_document_ids_list_uses_no_document():
    """An explicit empty list opts out of the conversation documents."""
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "Contenu du rapport")
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    result = await run_tool(ctx, respond=respond, document_ids=[])

    assert "Contenu du rapport" not in received[0]
    assert result.metadata["sources"] == []


@pytest.mark.asyncio
async def test_an_unknown_document_id_is_offered_for_retry():
    """An id outside the conversation and its project lets the model correct itself."""
    ctx, _conversation, _user = await setup_context()
    other_conversation = await sync_to_async(ChatConversationFactory)()
    foreign = await add_document(other_conversation, "Secret")

    with pytest.raises(ModelRetry, match="document_id was not found"):
        await run_tool(ctx, document_ids=[str(foreign.id)])


@pytest.mark.asyncio
async def test_documents_not_ready_are_not_used():
    """Uploads still being scanned (or quarantined) never reach the agent."""
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "En cours d'analyse", upload_state=AttachmentStatus.ANALYZING)
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    result = await run_tool(ctx, respond=respond)

    assert "En cours d'analyse" not in received[0]
    assert result.metadata["sources"] == []


@pytest.mark.asyncio
async def test_an_unreadable_document_is_skipped():
    """A document missing from storage does not prevent building the deck."""
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, None, file_name="absent.md")
    await add_document(conversation, "Contenu lisible", file_name="present.md")

    result = await run_tool(ctx)

    assert result.metadata["sources"] == ["present.md"]


def mock_summarization(summary):
    """Stub the summarization pipeline so it returns `summary`."""
    return mock.patch(
        "chat.tools.generate_presentation._summarize_text_attachments",
        new_callable=mock.AsyncMock,
        return_value=ToolReturn(return_value=summary),
    )


def mock_source_budget(tokens):
    """Fix the token budget for source documents."""
    return mock.patch("chat.tools.generate_presentation._source_budget", return_value=tokens)


@pytest.mark.asyncio
async def test_documents_over_budget_are_condensed_first():
    """
    Documents too long for the agent's prompt go through the summarization
    pipeline, asked to keep the details a deck needs.
    """
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "Un très long rapport " * 20, file_name="rapport.md")
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    with mock_source_budget(50), mock_summarization("Synthèse détaillée") as summarize:
        result = await run_tool(ctx, respond=respond)

    assert "slide deck" in summarize.call_args.kwargs["instructions"]
    assert "<documents_summary>\nSynthèse détaillée\n</documents_summary>" in received[0]
    assert "Un très long rapport" not in received[0]
    assert result.metadata["sources"] == ["rapport.md"]


@pytest.mark.asyncio
async def test_a_condensed_summary_over_budget_is_truncated():
    """
    A summary still too long for the budget is cut, so the agent never
    receives more source material than the budget allows.
    """
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "Un très long rapport " * 20, file_name="rapport.md")
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    with mock_source_budget(50), mock_summarization("Synthèse " * 200):
        result = await run_tool(ctx, respond=respond)

    sources = received[0].split("## Source documents\n\n", 1)[1]
    assert sources.startswith("<documents_summary>\nSynthèse")
    assert count_approx_tokens(sources) <= 50
    assert result.metadata["sources"] == ["rapport.md"]


@pytest.mark.asyncio
async def test_without_budget_for_sources_the_deck_uses_the_brief_only():
    """
    With no room at all for source material, nothing is summarized and the
    deck is not presented as built from documents the agent never saw.
    """
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "Un rapport", file_name="rapport.md")
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(DECK)(messages, info)

    with mock_source_budget(0), mock_summarization("Synthèse") as summarize:
        result = await run_tool(ctx, respond=respond)

    summarize.assert_not_called()
    assert "Source documents" not in received[0]
    assert result.metadata["sources"] == []


@pytest.mark.asyncio
async def test_the_requested_slide_count_is_enforced():
    """
    A deck of the wrong length is sent back to the model, which gets told how
    many slides were asked for.
    """
    ctx, _conversation, _user = await setup_context()
    three_slides = {**DECK, "slides": [*DECK["slides"], DECK["slides"][1]]}
    calls = []

    def respond(messages, info):
        calls.append(messages)
        return model_returns_deck(DECK if len(calls) == 1 else three_slides)(messages, info)

    result = await run_tool(ctx, respond=respond, slide_count=3)

    assert len(calls) == 2
    assert "Exactly 3 slides" in prompts_of(calls[0])[0]
    assert "exactly 3 were requested" in str(calls[1][-1])
    assert "3 slides" in result.return_value


@pytest.mark.asyncio
async def test_a_non_positive_slide_count_is_offered_for_retry():
    """A slide count below one is a model mistake it can correct."""
    ctx, _conversation, _user = await setup_context()

    with pytest.raises(ModelRetry, match="slide_count"):
        await run_tool(ctx, slide_count=0)


@pytest.mark.asyncio
async def test_a_slide_count_beyond_the_maximum_is_offered_for_retry():
    """A deck of thousands of slides is refused before costing anything."""
    ctx, _conversation, _user = await setup_context()

    with pytest.raises(ModelRetry, match="slide_count"):
        await run_tool(ctx, slide_count=1000)


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


@pytest.mark.asyncio
async def test_the_deck_is_kept_for_later_edits():
    """The result's metadata keeps the deck, its style and the source material it was built from."""
    ctx, conversation, _user = await setup_context()
    await add_document(conversation, "Contenu du rapport", file_name="rapport.md")

    result = await run_tool(ctx, style=PresentationStyle(title_color="#000091"))

    stored = StoredPresentation.model_validate(result.metadata["presentation"])
    assert stored.presentation == Presentation.model_validate(DECK)
    assert stored.style == PresentationStyle(title_color="#000091")
    assert stored.source_material == '<document name="rapport.md">\nContenu du rapport\n</document>'
    assert stored.source_names == ["rapport.md"]


@pytest.mark.asyncio
async def test_the_requested_style_is_applied():
    """A style passed at generation reaches the deck."""
    ctx, _conversation, _user = await setup_context()

    result = await run_tool(ctx, style=PresentationStyle(text_size=20))

    deck = await sync_to_async(read_deck)(result.metadata["url"])
    body_runs = deck.slides[1].shapes[1].text_frame.paragraphs[0].runs
    assert body_runs[0].font.size == pptx.util.Pt(20)


@pytest.mark.asyncio
async def test_a_style_change_keeps_the_content_word_for_word():
    """
    A style-only update rebuilds the last deck with the merged style, without
    asking the agent to write it again.
    """
    ctx, conversation, _user = await setup_context()
    await persist_tool_returns(
        conversation, stored_deck(style=PresentationStyle(title_color="#000091"))
    )

    def respond(_messages, _info):
        raise AssertionError("The agent must not run for a style-only change.")

    result = await run_update(ctx, respond=respond, style=PresentationStyle(text_size=20))

    stored = StoredPresentation.model_validate(result.metadata["presentation"])
    assert stored.presentation == Presentation.model_validate(DECK)
    assert stored.style == PresentationStyle(title_color="#000091", text_size=20)
    assert "was updated" in result.return_value
    assert result.metadata["sources"] == []

    deck = await sync_to_async(read_deck)(result.metadata["url"])
    title_run = deck.slides[1].shapes[0].text_frame.paragraphs[0].runs[0]
    assert str(title_run.font.color.rgb) == "000091"


@pytest.mark.asyncio
async def test_a_content_change_goes_through_the_agent_with_the_stored_sources():
    """
    The agent receives the current deck, the requested changes and the deck's
    source material as stored, without reading or condensing the documents again,
    and its new deck replaces the old one.
    """
    ctx, conversation, _user = await setup_context()
    await persist_tool_returns(
        conversation,
        stored_deck(
            source_material="<document>Le budget atteint 42 M€.</document>",
            source_names=["rapport.md"],
        ),
    )
    received = []
    edited = {**DECK, "title": "Sobriété énergétique, version longue"}

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(edited)(messages, info)

    with mock.patch("chat.tools.generate_presentation.build_sources") as build_sources:
        result = await run_update(ctx, respond=respond, instructions="Ajoute le budget")

    build_sources.assert_not_called()
    assert '## Current deck\n\n{"title":"Sobriété énergétique"' in received[0]
    assert "## Changes requested\n\nAjoute le budget" in received[0]
    assert "## Source documents\n\n<document>Le budget atteint 42 M€.</document>" in received[0]
    stored = StoredPresentation.model_validate(result.metadata["presentation"])
    assert stored.presentation.title == "Sobriété énergétique, version longue"
    assert stored.source_material == "<document>Le budget atteint 42 M€.</document>"
    assert result.metadata["sources"] == ["rapport.md"]


@pytest.mark.asyncio
async def test_the_latest_deck_is_updated():
    """
    With several decks, the most recent one is updated, whether it comes from
    an earlier turn or from the current one.
    """
    ctx, conversation, _user = await setup_context()
    await persist_tool_returns(conversation, stored_deck("Premier"), stored_deck("Deuxième"))

    result = await run_update(ctx, style=PresentationStyle(text_size=20))
    assert result.metadata["presentation"]["presentation"]["title"] == "Deuxième"

    ctx.messages = [
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="update_presentation",
                    content="The presentation was updated.",
                    tool_call_id="call-current",
                    metadata=stored_deck("Ce tour-ci"),
                )
            ]
        )
    ]
    result = await run_update(ctx, style=PresentationStyle(text_size=20))
    assert result.metadata["presentation"]["presentation"]["title"] == "Ce tour-ci"


@pytest.mark.asyncio
async def test_an_unreadable_stored_deck_is_skipped():
    """A stored deck that no longer validates falls back to an older one."""
    ctx, conversation, _user = await setup_context()
    await persist_tool_returns(
        conversation, stored_deck("Ancien"), {"presentation": {"presentation": {"slides": []}}}
    )

    result = await run_update(ctx, style=PresentationStyle(text_size=20))

    assert result.metadata["presentation"]["presentation"]["title"] == "Ancien"


@pytest.mark.asyncio
async def test_updating_without_a_deck_soft_fails():
    """With no deck in the conversation, the model is told to generate one."""
    ctx, _conversation, _user = await setup_context()

    result = await run_update(ctx, instructions="Mets les titres en bleu")

    assert isinstance(result, str)
    assert "generate_presentation" in result


@pytest.mark.asyncio
async def test_an_update_without_changes_is_offered_for_retry():
    """Neither instructions nor style is a model mistake it can correct."""
    ctx, _conversation, _user = await setup_context()

    with pytest.raises(ModelRetry, match="Nothing to change"):
        await run_update(ctx, instructions="  ")


@pytest.mark.asyncio
async def test_revert_restores_the_previous_version_exactly():
    """Undoing the last change restores the previous deck and style as they were, without the agent."""
    ctx, conversation, _user = await setup_context()
    await persist_tool_returns(
        conversation,
        stored_deck("Avant", style=PresentationStyle(text_size=14)),
        stored_deck("Après", style=PresentationStyle(text_size=20)),
    )

    def respond(_messages, _info):
        raise AssertionError("The agent must not run to revert a change.")

    result = await run_update(ctx, respond=respond, revert=True)

    stored = StoredPresentation.model_validate(result.metadata["presentation"])
    assert stored.presentation.title == "Avant"
    assert stored.style == PresentationStyle(text_size=14)
    assert "restored to its previous version" in result.return_value


@pytest.mark.asyncio
async def test_reverting_a_first_version_soft_fails():
    """A deck with no earlier version has nothing to restore."""
    ctx, conversation, _user = await setup_context()
    await persist_tool_returns(conversation, stored_deck())

    result = await run_update(ctx, revert=True)

    assert isinstance(result, str)
    assert "no earlier version" in result


TEMPLATED_DECK = {
    "title": "Plan vélo",
    "slides": [
        {"template_slide": 1, "texts": {"2": "Plan vélo", "3": ""}},
        {"template_slide": 2, "texts": {"2": "Constats", "3": "- Plus de cyclistes"}},
    ],
}


@sync_to_async
def add_template(conversation):
    """Attach a pptx as an upload leaves it: the file, and its Markdown companion."""
    deck = pptx.Presentation()
    deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text = "Titre de la présentation"
    content = deck.slides.add_slide(deck.slide_layouts[1])
    content.shapes.title.text = "Titre de contenu"
    blob = BytesIO()
    deck.save(blob)

    template = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        file_name="gabarit.pptx",
        # As browsers often send it, rather than the pptx content type.
        content_type="application/octet-stream",
        upload_state=AttachmentStatus.READY,
    )
    default_storage.save(template.key, ContentFile(blob.getvalue()))
    companion = ChatConversationAttachmentFactory(
        conversation=conversation,
        uploaded_by=conversation.owner,
        file_name="gabarit.md",
        content_type="text/markdown",
        upload_state=AttachmentStatus.READY,
        conversion_from=template.key,
    )
    default_storage.save(companion.key, ContentFile(b"Titre de la presentation"))
    return template, companion


@pytest.mark.asyncio
async def test_a_template_id_builds_the_deck_out_of_the_user_slides():
    """
    The agent is shown the user's slides, its deck copies them, and the template
    is kept for later edits rather than read as a source document.
    """
    ctx, conversation, _user = await setup_context()
    template, companion = await add_template(conversation)
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(TEMPLATED_DECK)(messages, info)

    result = await run_tool(ctx, respond=respond, template_id=str(companion.id))

    assert "## User's deck\n\nSlide 1, layout 'Title Slide':" in received[0]
    assert "Source documents" not in received[0]
    stored = StoredPresentation.model_validate(result.metadata["presentation"])
    assert stored.template_key == template.key
    assert "out of the slides of the user's pptx" in result.return_value

    deck = await sync_to_async(read_deck)(result.metadata["url"])
    assert [slide.shapes.title.text for slide in deck.slides] == ["Plan vélo", "Constats"]


@pytest.mark.asyncio
async def test_a_template_id_not_pointing_to_a_pptx_is_offered_for_retry():
    """Only an attached pptx can serve as a template."""
    ctx, conversation, _user = await setup_context()
    document = await add_document(conversation, "Un rapport")

    with pytest.raises(ModelRetry, match="attached pptx"):
        await run_tool(ctx, template_id=str(document.id))


@pytest.mark.asyncio
async def test_a_template_with_too_much_text_is_refused():
    """The user's whole deck goes into the prompt: one too large for it is refused."""
    ctx, conversation, _user = await setup_context()
    _template, companion = await add_template(conversation)

    with mock_source_budget(10):
        result = await run_tool(ctx, template_id=str(companion.id))

    assert "too much text to be used as a template" in result


@pytest.mark.asyncio
async def test_a_templated_deck_is_edited_on_its_template():
    """An edit shows the agent the user's slides again, and keeps building on them."""
    ctx, conversation, _user = await setup_context()
    template, _companion = await add_template(conversation)
    await persist_tool_returns(
        conversation,
        {
            "presentation": StoredPresentation(
                presentation=TEMPLATED_DECK, template_key=template.key
            ).model_dump(mode="json")
        },
    )
    received = []

    def respond(messages, info):
        received.extend(prompts_of(messages))
        return model_returns_deck(TEMPLATED_DECK)(messages, info)

    result = await run_update(ctx, respond=respond, instructions="Raccourcis le titre")

    assert "## User's deck" in received[0]
    assert StoredPresentation.model_validate(result.metadata["presentation"]).template_key == (
        template.key
    )
