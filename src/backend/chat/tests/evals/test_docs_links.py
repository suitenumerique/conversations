"""Tests for the docs_links eval wiring."""

# pylint: disable=protected-access

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from chat.docs_client import DocsFetchFailure
from chat.docs_snapshots import docs_failure_note, docs_read_note
from chat.document_context_builder import TOOL_CALL_ONLY_CONTENT
from chat.evals import EvalDocsLink, EvalInputs
from chat.evals.configs import REGISTRY
from chat.evals.configs import docs_links as docs_links_config
from chat.evals.configs.docs_links import (
    DOCS_BASE_URL,
    build_docs_links_case,
    docs_link_document_id,
)
from chat.evals.production_agent import reset_eval_session_cache
from chat.llm_configuration import LLModel, LLMProvider, LLMSettings

pytestmark = pytest.mark.django_db

LISTING_PREFIX = "List of documents attached to this conversation:\n"

SMALL_DOC = EvalDocsLink(outcome="read", title="Note", content="Pilote : Odile Varennes.")
LARGE_DOC = EvalDocsLink(
    outcome="read", title="Rapport", content="[1] Opération Lanterne.", access="tool_call_only"
)


@pytest.fixture(autouse=True)
def reset_eval_session_cache_fixture():
    """Reset the eval session cache before and after each test."""
    reset_eval_session_cache()
    yield
    reset_eval_session_cache()


@pytest.fixture(autouse=True, name="ai_settings")
def ai_settings_fixture(settings):
    """Set up the AI and Docs settings for the tests."""
    settings.LLM_CONFIGURATIONS = {
        "default-model": LLModel(
            hrid="default-model",
            model_name="provider/model",
            human_readable_name="Provider Model",
            is_active=True,
            icon=None,
            system_prompt="You are an assistant.",
            tools=[],
            provider=LLMProvider(
                hrid="provider",
                base_url="https://example.com",
                api_key="key",
                kind="openai",
            ),
            settings=LLMSettings(max_tokens=1024),
        )
    }
    settings.LLM_DEFAULT_MODEL_HRID = "default-model"
    settings.DOCS_BASE_URL = DOCS_BASE_URL
    return settings


def _listing(instructions: str) -> dict:
    listing_text = instructions.split(LISTING_PREFIX, 1)[1].split("\n\n[Internal context]", 1)[0]
    return json.loads(listing_text)


def test_docs_links_registered():
    """The docs_links dataset is registered."""
    assert REGISTRY["docs_links"].name == "docs_links"
    assert REGISTRY["docs_links"].llm_judge_rubric


def test_build_case_fills_links_and_uses_production_notes():
    """Links are substituted and each gets the production note."""
    inputs = EvalInputs(
        user_message="Compare {link0} et {link1}",
        docs_links=[SMALL_DOC, EvalDocsLink(outcome="forbidden")],
    )

    user_message, instructions = build_docs_links_case(inputs)

    first_url = f"{DOCS_BASE_URL}docs/{docs_link_document_id(0)}/"
    second_url = f"{DOCS_BASE_URL}docs/{docs_link_document_id(1)}/"
    assert user_message == f"Compare {first_url} et {second_url}"
    assert docs_read_note(docs_link_document_id(0), "Note.md") in instructions
    assert docs_failure_note(docs_link_document_id(1), DocsFetchFailure.FORBIDDEN) in instructions


def test_build_case_lists_read_documents_by_access():
    """Read links are listed: small ones inlined, large ones through tools."""
    inputs = EvalInputs(user_message="{link0} {link1}", docs_links=[SMALL_DOC, LARGE_DOC])

    _, instructions = build_docs_links_case(inputs)

    documents = {doc["title"]: doc for doc in _listing(instructions)["documents"]}
    assert documents["Note.md"]["access"] == "full-context"
    assert documents["Note.md"]["content"] == "Pilote : Odile Varennes."
    assert documents["Rapport.md"]["access"] == "tool_call_only"
    assert documents["Rapport.md"]["content"] == TOOL_CALL_ONLY_CONTENT


def test_build_case_failures_only_has_no_listing():
    """Without a read link, only the failure notes are given."""
    inputs = EvalInputs(user_message="{link0}", docs_links=[EvalDocsLink(outcome="not_found")])

    _, instructions = build_docs_links_case(inputs)

    assert LISTING_PREFIX not in instructions
    assert instructions == docs_failure_note(docs_link_document_id(0), DocsFetchFailure.NOT_FOUND)


def test_build_case_labels_a_single_read_document_as_first():
    """Position labels count from 1, as in production."""
    inputs = EvalInputs(user_message="{link0}", docs_links=[SMALL_DOC])

    _, instructions = build_docs_links_case(inputs)

    assert _listing(instructions)["documents"][0]["info"] == "first_uploaded_document"


def test_build_case_labels_two_read_documents_first_and_last():
    """With two read documents, both are labelled (the listing shows the latest first)."""
    inputs = EvalInputs(user_message="{link0} {link1}", docs_links=[SMALL_DOC, LARGE_DOC])

    _, instructions = build_docs_links_case(inputs)

    infos = {doc["title"]: doc["info"] for doc in _listing(instructions)["documents"]}
    assert infos == {"Note.md": "first_uploaded_document", "Rapport.md": "last_uploaded_document"}


def _run_with_function_model(monkeypatch, inputs: EvalInputs, model_function) -> str:
    """Run the docs_links task function with a FunctionModel on every agent."""
    services = []
    build_service = docs_links_config._build_service

    def recording_build_service(*args, **kwargs):
        service = build_service(*args, **kwargs)
        services.append(service)
        return service

    monkeypatch.setattr(docs_links_config, "_build_service", recording_build_service)
    run_agent = docs_links_config.make_docs_links_task_fn("default-model")
    model = FunctionModel(model_function)
    with services[0].conversation_agent.override(model=model):
        with services[1].conversation_agent.override(model=model):
            return asyncio.run(run_agent(inputs))


def test_task_fn_gives_the_case_context_to_the_model(monkeypatch):
    """The model receives the user message with the URL and the Docs notes."""
    seen = {}

    def model_function(messages, _info):
        seen["instructions"] = messages[-1].instructions
        seen["prompt"] = messages[-1].parts[-1].content
        return ModelResponse(parts=[TextPart("ok")])

    inputs = EvalInputs(user_message="Résume {link0}", docs_links=[SMALL_DOC])
    output = _run_with_function_model(monkeypatch, inputs, model_function)

    assert output == "ok"
    assert seen["prompt"] == f"Résume {DOCS_BASE_URL}docs/{docs_link_document_id(0)}/"
    assert docs_read_note(docs_link_document_id(0), "Note.md") in seen["instructions"]
    assert "Odile Varennes" in seen["instructions"]


def test_task_fn_rag_stub_returns_the_document(monkeypatch):
    """The stub RAG tool returns the content of the read document."""
    seen = {}

    def model_function(messages, _info):
        tool_returns = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
        if tool_returns:
            seen["rag"] = tool_returns[0].content
            return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(parts=[ToolCallPart("document_search_rag", {"_query": "Lanterne"})])

    inputs = EvalInputs(user_message="Qui ? {link0}", docs_links=[LARGE_DOC])
    _run_with_function_model(monkeypatch, inputs, model_function)

    assert "[1] Opération Lanterne." in seen["rag"]
