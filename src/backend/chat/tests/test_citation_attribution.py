"""Unit tests for deterministic citation attribution."""

from chat.citation_attribution import (
    AttributionConfig,
    CitationCandidate,
    CitationStreamAttributor,
    attribute_citations,
    attribute_citations_by_paragraph,
    extract_citation_candidates,
)


def _config(**overrides):
    base = dict(
        min_score=0.2,
        top_k_per_sentence=3,
        max_sources_per_sentence=1,
        embedding_weight=0.7,
        rouge_weight=0.3,
    )
    base.update(overrides)
    return AttributionConfig(**base)


def test_attribute_citations_injects_web_refs():
    """Web snippets above threshold inject deterministic ref tags."""
    candidates = [
        CitationCandidate(
            snippet="Paris is the capital of France.",
            source_url="https://example.com/france",
            scope="web",
            citation_id="web_0_0",
        )
    ]
    result = attribute_citations("Paris is the capital of France.", candidates, _config())
    assert '<ref id="web_0_0"/>' in result.text
    assert result.selected_citation_ids == {"web_0_0"}
    assert result.selected_urls == {"https://example.com/france"}


def test_attribute_citations_respects_threshold():
    """No citation is selected when score is below configured threshold."""
    candidates = [
        CitationCandidate(
            snippet="Paris is the capital of France.",
            source_url="https://example.com/france",
            scope="web",
            citation_id="web_0_0",
        )
    ]
    result = attribute_citations(
        "This sentence is unrelated.",
        candidates,
        _config(min_score=0.99),
    )
    assert result.text == "This sentence is unrelated."
    assert not result.selected_citation_ids
    assert not result.selected_urls


def test_attribute_citations_by_paragraph_respects_min_sentences():
    """Paragraphs below min sentence count should not receive citations."""
    candidates = [
        CitationCandidate(
            snippet="Paris is the capital of France.",
            source_url="https://example.com/france",
            scope="web",
            citation_id="web_0_0",
        )
    ]
    result = attribute_citations_by_paragraph(
        "Paris is the capital of France.",
        candidates,
        _config(min_sentences_per_paragraph=2),
    )
    assert '<ref id="web_0_0"/>' not in result.text
    assert not result.selected_citation_ids


def test_extract_citation_candidates_from_web_payload():
    """Tool payload parser extracts web snippet refs and text."""
    content = {
        "0": {
            "url": "https://example.com/a",
            "title": "A",
            "snippets": ["[ref:web_0_0] first snippet", "[ref:web_0_1] second snippet"],
        }
    }
    candidates = extract_citation_candidates("web_search", content)
    assert len(candidates) == 2
    assert {candidate.citation_id for candidate in candidates} == {"web_0_0", "web_0_1"}
    assert candidates[0].snippet == "first snippet"


def test_add_candidates_remaps_ids_across_searches():
    """Second web search continues global URL indices so frontend mapping stays stable."""
    attributor = CitationStreamAttributor(config=_config())
    first = extract_citation_candidates(
        "web_search",
        {
            "0": {
                "url": "https://example.com/a",
                "snippets": ["[ref:web_0_0] alpha"],
            }
        },
    )
    second = extract_citation_candidates(
        "web_search",
        {
            "0": {
                "url": "https://example.com/b",
                "snippets": ["[ref:web_0_0] beta"],
            }
        },
    )
    remapped_first = attributor.add_candidates(first)
    remapped_second = attributor.add_candidates(second)
    assert remapped_first[0].citation_id == "web_0_0"
    assert remapped_second[0].citation_id == "web_1_0"
    assert attributor.ordered_source_urls() == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_multi_search_attribution_keeps_url_alignment():
    """Refs from a second search must not resolve to the first search's URL."""
    attributor = CitationStreamAttributor(config=_config())
    attributor.add_candidates(
        extract_citation_candidates(
            "web_search",
            {
                "0": {
                    "url": "https://weather.example/paris",
                    "snippets": ["[ref:web_0_0] Paris weather is rainy today."],
                }
            },
        )
    )
    attributor.add_candidates(
        extract_citation_candidates(
            "web_search",
            {
                "0": {
                    "url": "https://cuisine.example/baguette",
                    "snippets": ["[ref:web_0_0] Baguette is a French bread."],
                }
            },
        )
    )
    result = attribute_citations_by_paragraph(
        "Baguette is a French bread.",
        attributor.candidates,
        _config(),
    )
    assert result.selected_citation_ids == {"web_1_0"}
    assert result.selected_urls == {"https://cuisine.example/baguette"}
    assert '<ref id="web_0_0"/>' not in result.text
    assert '<ref id="web_1_0"/>' in result.text


def test_stream_attributor_drains_on_paragraph_break():
    """Streaming attribution emits completed paragraphs and keeps the remainder."""
    attributor = CitationStreamAttributor(config=_config())
    attributor.add_candidates(
        [
            CitationCandidate(
                snippet="Paris is the capital of France.",
                source_url="https://example.com/france",
                scope="web",
                citation_id="web_0_0",
            )
        ]
    )
    assert attributor.drain("Paris is the capital of France.") == []
    chunks = attributor.drain("\n\nNext paragraph")
    assert len(chunks) == 1
    assert '<ref id="web_0_0"/>' in chunks[0].text
    trailing = attributor.flush()
    assert trailing is not None
    assert trailing.text.startswith("Next paragraph")
