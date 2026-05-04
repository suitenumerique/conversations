"""Unit tests for deterministic citation attribution."""

from chat.citation_attribution import (
    AttributionConfig,
    CitationCandidate,
    attribute_citations,
)
from chat.clients.pydantic_ai import _extract_citation_candidates


def test_attribute_citations_injects_web_refs():
    """Web snippets above threshold inject deterministic ref tags."""
    config = AttributionConfig(
        min_score=0.2,
        top_k_per_sentence=3,
        max_sources_per_sentence=1,
        embedding_weight=0.7,
        rouge_weight=0.3,
    )
    candidates = [
        CitationCandidate(
            snippet="Paris is the capital of France.",
            source_url="https://example.com/france",
            scope="web",
            citation_id="web_0_0",
        )
    ]
    result = attribute_citations("Paris is the capital of France.", candidates, config)
    assert '<ref id="web_0_0"/>' in result.text
    assert result.selected_web_citation_ids == {"web_0_0"}
    assert result.selected_urls == {"https://example.com/france"}


def test_attribute_citations_respects_threshold():
    """No citation is selected when score is below configured threshold."""
    config = AttributionConfig(
        min_score=0.99,
        top_k_per_sentence=3,
        max_sources_per_sentence=1,
        embedding_weight=0.7,
        rouge_weight=0.3,
    )
    candidates = [
        CitationCandidate(
            snippet="Paris is the capital of France.",
            source_url="https://example.com/france",
            scope="web",
            citation_id="web_0_0",
        )
    ]
    result = attribute_citations("This sentence is unrelated.", candidates, config)
    assert result.text == "This sentence is unrelated."
    assert not result.selected_web_citation_ids
    assert not result.selected_urls


def test_extract_citation_candidates_from_web_payload():
    """Tool payload parser extracts web snippet refs and text."""
    content = {
        "0": {
            "url": "https://example.com/a",
            "title": "A",
            "snippets": ["[ref:web_0_0] first snippet", "[ref:web_0_1] second snippet"],
        }
    }
    candidates = _extract_citation_candidates("web_search", content)
    assert len(candidates) == 2
    assert {candidate.citation_id for candidate in candidates} == {"web_0_0", "web_0_1"}
    assert candidates[0].snippet == "first snippet"
