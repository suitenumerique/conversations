"""Tests for production-shaped eval tool stub payloads."""

import json

from pydantic_ai.messages import ToolReturn

from chat.evals.tool_stub_responses import (
    DEFAULT_RAG_CHUNKS,
    ToolStubResponses,
    get_current_tool_stubs,
    parse_tool_stub_responses,
    reset_current_tool_stubs,
    set_current_tool_stubs,
)


def test_parse_empty_uses_defaults():
    """Test that the default RAG chunks are used when no tool stub responses are provided."""
    stubs = parse_tool_stub_responses(None)
    assert stubs.document_search_rag_return().return_value == json.dumps(
        {"chunks": DEFAULT_RAG_CHUNKS}, ensure_ascii=False
    )


def test_parse_json_multi_tool():
    """Test that the tool stub responses are parsed correctly when provided as JSON."""
    raw = json.dumps(
        {
            "document_search_rag": "[1] Passage sur les risques.",
            "summarize": "Résumé en 3 points.",
            "web_search": {"0": {"url": "https://a.test", "title": "T", "snippets": ["S"]}},
        }
    )
    stubs = parse_tool_stub_responses(raw)
    assert "risques" in stubs.document_search_rag_return().return_value
    assert stubs.summarize_return().return_value == "Résumé en 3 points."
    web = stubs.web_search_return()
    assert isinstance(web, ToolReturn)
    assert web.return_value["0"]["url"] == "https://a.test"


def test_parse_plain_text_as_rag_chunks():
    """Test that the tool stub responses are parsed correctly when provided as plain text."""
    stubs = parse_tool_stub_responses("[1] Un passage.")
    assert stubs.document_search_rag == "[1] Un passage."


def test_context_var_staging():
    """Test that the tool stub responses are set correctly when provided as a context variable."""
    stubs = ToolStubResponses(summarize="Custom summary")
    token = set_current_tool_stubs(stubs)
    try:
        assert get_current_tool_stubs().summarize_return().return_value == "Custom summary"
    finally:
        reset_current_tool_stubs(token)


def test_default_web_search_shape():
    """Test that the default web search shape is used when no tool stub responses are provided."""
    stubs = parse_tool_stub_responses(None)
    payload = stubs.web_search_return().return_value
    assert "0" in payload
    assert "url" in payload["0"]
    assert "snippets" in payload["0"]
