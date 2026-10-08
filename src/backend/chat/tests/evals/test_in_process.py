"""Tests for the in-process task: production setup, fixture documents and stubbed tools."""

import asyncio
import json

from django.db import connections

import pytest
from asgiref.sync import sync_to_async
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from chat.agents.history_processors import SUMMARY_SYSTEM_PREFIX
from chat.evals import EvalInputs
from chat.evals.in_process import make_in_process_task_fn
from chat.evals.production_agent import reset_eval_session_cache
from chat.llm_configuration import LLModel, LLMProvider

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True, name="ai_settings")
def ai_settings_fixture(settings):
    """A model with a context large enough to inline small documents."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="provider/model",
            human_readable_name="Provider Model",
            is_active=True,
            icon=None,
            system_prompt="You are an assistant.",
            tools=[],
            max_token_context=128_000,
            provider=LLMProvider(
                hrid="provider", base_url="https://example.com", api_key="key", kind="openai"
            ),
        )
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    reset_eval_session_cache()
    yield settings
    reset_eval_session_cache()
    # The task builds its service in asgiref's sync thread: close that thread's connection.
    asyncio.run(sync_to_async(connections.close_all)())


@pytest.fixture(name="documents_dir")
def documents_dir_fixture(tmp_path):
    """Three fixture documents, each with its fixed summary."""
    for name in ("cr-a", "cr-b", "fiche"):
        (tmp_path / f"{name}.md").write_text(f"Texte complet de {name}.", encoding="utf-8")
        (tmp_path / f"{name}.summary.md").write_text(f"Résumé de {name}.", encoding="utf-8")
    return tmp_path


class ScriptedModel:
    """Answers each model request with the next scripted response, recording what it saw."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, messages, info):
        self.requests.append((messages, info))
        response = self.responses.pop(0)
        return response(messages) if callable(response) else response


@pytest.fixture(name="model")
def model_fixture(settings, monkeypatch):
    """Route the agent to a scripted model, through the app's mock-agent hook."""
    scripted = ScriptedModel()
    settings.WARNING_MOCK_CONVERSATION_AGENT = True
    monkeypatch.setattr(
        "chat.agents.conversation.FunctionModel",
        lambda **_kwargs: FunctionModel(function=scripted),
    )
    return scripted


@pytest.fixture(name="attributes")
def attributes_fixture(monkeypatch):
    """Eval attributes the task records."""
    recorded = {}
    monkeypatch.setattr("chat.evals.in_process.set_eval_attribute", recorded.__setitem__)
    return recorded


def _text(content: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=content)])


def _call(tool_name: str, **args) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args)])


def _run(documents_dir, inputs: EvalInputs) -> str:
    return asyncio.run(make_in_process_task_fn(documents_dir)("default-model")(inputs))


def _instructions(model, request_index: int = 0) -> str:
    messages, _info = model.requests[request_index]
    return messages[-1].instructions


def _listing(model) -> dict:
    instructions = _instructions(model)
    start = instructions.index("List of documents attached to this conversation:\n")
    payload = instructions[start:].split("\n", 1)[1]
    return json.JSONDecoder().raw_decode(payload)[0]


def _tool_return(model, request_index: int) -> ToolReturnPart:
    messages, _info = model.requests[request_index]
    return next(part for part in messages[-1].parts if isinstance(part, ToolReturnPart))


def test_conversation_documents_are_inlined_and_project_files_tool_call_only(model, documents_dir):
    """The listing is production's: small attachments inlined, project files via tools."""
    model.responses = [_text("ok")]

    _run(
        documents_dir,
        EvalInputs(user_message="Résume", attachments=["cr-a"], project_attachments=["fiche"]),
    )

    listing = _listing(model)
    assert [(doc["title"], doc["access"]) for doc in listing["documents"]] == [
        ("cr-a.md", "full-context")
    ]
    assert "Texte complet de cr-a." in listing["documents"][0]["content"]
    assert [(doc["title"], doc["access"]) for doc in listing["project_documents"]] == [
        ("fiche.md", "tool_call_only")
    ]


def test_rag_and_summarize_keep_the_production_tool_schemas(model, documents_dir):
    """Stubbed tools expose the production parameters to the model."""
    model.responses = [_text("ok")]

    _run(documents_dir, EvalInputs(user_message="Résume", project_attachments=["fiche"]))

    _messages, info = model.requests[0]
    schemas = {tool.name: tool.parameters_json_schema["properties"] for tool in info.function_tools}
    assert set(schemas["document_search_rag"]) == {"query", "document_id"}
    assert set(schemas["summarize"]) == {"instructions", "document_id"}
    assert set(schemas["summarize_project"]) == {"instructions", "document_id"}


def test_rag_stub_searches_the_documents_not_inlined(model, documents_dir, attributes):
    """Without document_id, RAG skips the inlined attachments the model already has."""
    model.responses = [_call("document_search_rag", query="budget"), _text("ok")]

    _run(
        documents_dir,
        EvalInputs(user_message="Budget ?", attachments=["cr-a"], project_attachments=["fiche"]),
    )

    returned = _tool_return(model, 1).model_response_str()
    assert "Texte complet de fiche." in returned
    assert "cr-a" not in returned
    assert attributes["documents"] == [
        {"title": "cr-a.md", "access": "full-context"},
        {"title": "fiche.md", "access": "tool_call_only"},
    ]


def test_rag_stub_returns_the_documents_text(model, documents_dir, attributes):
    """document_search_rag returns the searched documents' full text, with their sources."""
    model.responses = [_call("document_search_rag", query="budget"), _text("Réponse")]

    answer = _run(documents_dir, EvalInputs(user_message="Budget ?", project_attachments=["fiche"]))

    assert answer == "Réponse"
    assert "Texte complet de fiche." in _tool_return(model, 1).model_response_str()
    assert attributes["tool_calls"] == [
        {"name": "document_search_rag", "args": {"query": "budget"}}
    ]
    assert attributes["sources"] == ["fiche.md"]


def _document_id(model, title: str) -> str:
    listing = _listing(model)
    entries = listing["documents"] + listing.get("project_documents", [])
    return next(doc["document_id"] for doc in entries if doc["title"] == title)


def test_summarize_one_document_returns_its_summary(model, documents_dir):
    """With document_id, summarize returns that document's fixed summary."""
    model.responses = [
        lambda _messages: _call(
            "summarize", document_id=_document_id(model, "cr-b.md"), instructions="en 2 lignes"
        ),
        _text("ok"),
    ]

    _run(documents_dir, EvalInputs(user_message="Résume", attachments=["cr-a", "cr-b"]))

    assert _tool_return(model, 1).model_response_str() == "Résumé de cr-b."


def test_summarize_without_id_covers_its_scope_only(model, documents_dir):
    """summarize covers the conversation's files, summarize_project the project's."""
    model.responses = [_call("summarize"), _call("summarize_project"), _text("ok")]

    _run(
        documents_dir,
        EvalInputs(
            user_message="Résume", attachments=["cr-a", "cr-b"], project_attachments=["fiche"]
        ),
    )

    conversation_summary = _tool_return(model, 1).model_response_str()
    assert "## cr-a.md\n\nRésumé de cr-a." in conversation_summary
    assert "## cr-b.md\n\nRésumé de cr-b." in conversation_summary
    assert "fiche" not in conversation_summary
    assert _tool_return(model, 2).model_response_str() == "Résumé de fiche."


def test_project_instructions_and_history_summary_reach_the_instructions(model, documents_dir):
    """Production's own setup injects the project instructions and the stored summary."""
    model.responses = [_text("ok")]

    _run(
        documents_dir,
        EvalInputs(
            user_message="Bonjour",
            project_instructions="Réponds en vers.",
            history_summary="L'utilisateur s'appelle Léa.",
        ),
    )

    instructions = _instructions(model)
    assert "Réponds en vers." in instructions
    assert f"{SUMMARY_SYSTEM_PREFIX}L'utilisateur s'appelle Léa." in instructions
    assert "Answer in french." in instructions


def test_message_history_comes_first_with_pastes_expanded(model, documents_dir):
    """The case starts from its message history; paste markers become fixture text."""
    model.responses = [_text("ok")]

    _run(
        documents_dir,
        EvalInputs(
            user_message="Et maintenant ?",
            message_history=[
                {"role": "user", "content": "Voici :\n{{paste:cr-a}}"},
                {"role": "assistant", "content": "Bien reçu."},
            ],
        ),
    )

    messages, _info = model.requests[0]
    assert [part.content for message in messages for part in message.parts] == [
        "Voici :\nTexte complet de cr-a.",
        "Bien reçu.",
        "Et maintenant ?",
    ]


def test_follow_ups_continue_the_conversation_and_score_the_last_turn(
    model, documents_dir, attributes
):
    """Every turn sees the previous ones; the last answer is scored."""
    model.responses = [_text("Premier"), _text("Second")]

    answer = _run(documents_dir, EvalInputs(user_message="Un", follow_ups=["Deux"]))

    messages, _info = model.requests[1]
    assert [part.content for message in messages for part in message.parts] == [
        "Un",
        "Premier",
        "Deux",
    ]
    assert answer == "Second"
    assert attributes["turn_texts"] == ["Premier", "Second"]
    assert attributes["turns"] == 2
    assert attributes["tool_calls"] == []


def test_without_documents_no_document_tool_is_registered(model, documents_dir):
    """A case without files runs without RAG or summarize tools, like production."""
    model.responses = [_text("ok")]

    _run(documents_dir, EvalInputs(user_message="Bonjour"))

    _messages, info = model.requests[0]
    names = {tool.name for tool in info.function_tools}
    assert not names & {"document_search_rag", "summarize", "summarize_project"}
