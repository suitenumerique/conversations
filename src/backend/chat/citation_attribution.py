"""Deterministic citation attribution for web and RAG snippets."""

from __future__ import annotations

import dataclasses
import logging
import math
import re
from collections import Counter
from typing import Iterable

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?|\n+", flags=re.UNICODE)
_REF_RE = re.compile(r"<ref id=\"((?:web|rag)_\d+_\d+)\"\s*/>")
_TAGGED_SNIPPET_RE = re.compile(r"^\[ref:((?:web|rag)_\d+_\d+)\]\s*")
_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n+", flags=re.UNICODE)


@dataclasses.dataclass(slots=True)
class CitationCandidate:
    """One snippet candidate that can back a generated sentence."""

    snippet: str
    source_url: str
    scope: str  # "web" | "rag"
    citation_id: str | None = None


@dataclasses.dataclass(slots=True)
class AttributionConfig:
    """Scoring knobs for deterministic citation attribution."""

    min_score: float
    top_k_per_sentence: int
    max_sources_per_sentence: int
    embedding_weight: float
    rouge_weight: float
    min_sentences_per_paragraph: int = 1
    debug_logging: bool = False


@dataclasses.dataclass(slots=True)
class AttributionResult:
    """Attribution output used by chat finalization."""

    text: str
    selected_urls: set[str]
    selected_citation_ids: set[str]


@dataclasses.dataclass(slots=True)
class StreamingAttributionChunk:
    """Streaming chunk produced by citation attribution."""

    text: str
    selected_citation_ids: set[str]
    selected_urls: set[str] = dataclasses.field(default_factory=set)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _cosine_similarity(text_a: str, text_b: str) -> float:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0

    freq_a = Counter(tokens_a)
    freq_b = Counter(tokens_b)
    common = set(freq_a) & set(freq_b)
    dot = sum(freq_a[token] * freq_b[token] for token in common)
    norm_a = math.sqrt(sum(value * value for value in freq_a.values()))
    norm_b = math.sqrt(sum(value * value for value in freq_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _lcs_length(tokens_a: list[str], tokens_b: list[str]) -> int:
    if not tokens_a or not tokens_b:
        return 0
    prev = [0] * (len(tokens_b) + 1)
    for token_a in tokens_a:
        curr = [0]
        for idx, token_b in enumerate(tokens_b, start=1):
            if token_a == token_b:
                curr.append(prev[idx - 1] + 1)
            else:
                curr.append(max(curr[-1], prev[idx]))
        prev = curr
    return prev[-1]


def _rouge_l_f1(text_a: str, text_b: str) -> float:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    lcs = _lcs_length(tokens_a, tokens_b)
    if lcs == 0:
        return 0.0
    precision = lcs / len(tokens_b)
    recall = lcs / len(tokens_a)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _score_sentence(sentence: str, candidate: CitationCandidate, config: AttributionConfig) -> float:
    embedding_score = _cosine_similarity(sentence, candidate.snippet)
    rouge_score = _rouge_l_f1(sentence, candidate.snippet)
    final_score = (config.embedding_weight * embedding_score) + (config.rouge_weight * rouge_score)
    if config.debug_logging:
        logger.debug(
            "Citation score scope=%s url=%s web_id=%s score=%.4f cosine=%.4f rouge_l=%.4f",
            candidate.scope,
            candidate.source_url,
            candidate.citation_id,
            final_score,
            embedding_score,
            rouge_score,
        )
    return final_score


def _iter_sentences(text: str) -> Iterable[tuple[str, tuple[int, int]]]:
    for match in _SENTENCE_RE.finditer(text):
        chunk = match.group(0)
        if chunk.strip() and chunk != "\n":
            yield chunk, match.span()


def _sort_citation_key(citation_id: str) -> tuple[int, int, int]:
    """Sort citation IDs by scope and index."""
    scope, first, second = citation_id.split("_")
    scope_rank = 0 if scope == "web" else 1
    return (scope_rank, int(first), int(second))


def _inject_refs(sentence: str, citation_ids: list[str], max_sources: int) -> str:
    """Inject citation IDs into a sentence."""
    existing_ids = _REF_RE.findall(sentence)
    sentence_without_refs = _REF_RE.sub("", sentence).rstrip()
    combined_ids = list(dict.fromkeys(existing_ids + citation_ids))
    combined_ids.sort(key=_sort_citation_key)
    if max_sources > 0:
        combined_ids = combined_ids[:max_sources]
    if not combined_ids:
        return sentence_without_refs
    refs = " ".join(f'<ref id="{citation_id}"/>' for citation_id in combined_ids)
    return f"{sentence_without_refs} {refs}"


def _normalize_paragraph_refs_to_end(paragraph: str, max_sources: int) -> str:
    """Move all refs to the last sentence that already has a citation."""
    ref_ids = _REF_RE.findall(paragraph)
    ordered_ids = list(dict.fromkeys(ref_ids))
    ordered_ids.sort(key=_sort_citation_key)
    if max_sources > 0:
        ordered_ids = ordered_ids[:max_sources]
    if not ordered_ids:
        return paragraph

    sentences = list(_iter_sentences(paragraph))
    if not sentences:
        return paragraph

    cited_sentence_indexes = [
        idx for idx, (sentence, _span) in enumerate(sentences) if _REF_RE.search(sentence)
    ]
    if not cited_sentence_indexes:
        return paragraph
    target_idx = cited_sentence_indexes[-1]

    rebuilt_parts: list[str] = []
    cursor = 0
    for idx, (sentence, (start, end)) in enumerate(sentences):
        rebuilt_parts.append(_REF_RE.sub("", paragraph[cursor:start]))
        cleaned_sentence = _REF_RE.sub("", sentence).rstrip()
        if idx == target_idx:
            cleaned_sentence = _inject_refs(
                cleaned_sentence,
                ordered_ids,
                max_sources,
            )
        rebuilt_parts.append(cleaned_sentence)
        cursor = end

    rebuilt_parts.append(_REF_RE.sub("", paragraph[cursor:]))
    return "".join(rebuilt_parts)


def attribute_citations(
    text: str,
    candidates: list[CitationCandidate],
    config: AttributionConfig,
) -> AttributionResult:
    """Assign citations sentence-by-sentence with deterministic scoring."""
    if not text.strip() or not candidates:
        return AttributionResult(
            text=text,
            selected_urls=set(),
            selected_citation_ids=set(),
        )

    selected_urls: set[str] = set()
    selected_citation_ids: set[str] = set()
    rebuilt_parts: list[str] = []
    cursor = 0

    for sentence, (start, end) in _iter_sentences(text):
        rebuilt_parts.append(text[cursor:start])
        sentence_candidates = []
        for candidate in candidates:
            score = _score_sentence(sentence, candidate, config)
            if score >= config.min_score:
                sentence_candidates.append((score, candidate))

        sentence_candidates.sort(key=lambda item: item[0], reverse=True)
        shortlisted = sentence_candidates[: config.top_k_per_sentence]
        with_citation_id = [item for item in shortlisted if item[1].citation_id]
        without_citation_id = [item for item in shortlisted if not item[1].citation_id]
        selected_sentence = with_citation_id[: config.max_sources_per_sentence]
        if len(selected_sentence) < config.max_sources_per_sentence:
            remaining_slots = config.max_sources_per_sentence - len(selected_sentence)
            selected_sentence.extend(without_citation_id[:remaining_slots])

        sentence_citation_ids: list[str] = []
        for _score, candidate in selected_sentence:
            selected_urls.add(candidate.source_url)
            if candidate.citation_id:
                sentence_citation_ids.append(candidate.citation_id)
                selected_citation_ids.add(candidate.citation_id)

        rebuilt_parts.append(
            _inject_refs(
                sentence,
                sentence_citation_ids,
                config.max_sources_per_sentence,
            )
        )
        cursor = end

    rebuilt_parts.append(text[cursor:])
    return AttributionResult(
        text="".join(rebuilt_parts),
        selected_urls=selected_urls,
        selected_citation_ids=selected_citation_ids,
    )


def attribute_citations_by_paragraph(
    text: str,
    candidates: list[CitationCandidate],
    config: AttributionConfig,
) -> AttributionResult:
    """Apply citation attribution paragraph by paragraph."""
    if not text.strip():
        return AttributionResult(text=text, selected_urls=set(), selected_citation_ids=set())

    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in _PARAGRAPH_BREAK_RE.finditer(text):
        paragraph = text[cursor : match.start()]
        segments.append((paragraph, match.group(0)))
        cursor = match.end()
    segments.append((text[cursor:], ""))

    selected_urls: set[str] = set()
    selected_citation_ids: set[str] = set()
    rebuilt_parts: list[str] = []
    for paragraph, separator in segments:
        sentence_count = sum(1 for _ in _iter_sentences(paragraph))
        if paragraph.strip() and sentence_count >= config.min_sentences_per_paragraph:
            attribution = attribute_citations(paragraph, candidates, config)
            rebuilt_parts.append(
                _normalize_paragraph_refs_to_end(
                    attribution.text,
                    config.max_sources_per_sentence,
                )
            )
            selected_urls.update(attribution.selected_urls)
            selected_citation_ids.update(attribution.selected_citation_ids)
        else:
            rebuilt_parts.append(paragraph)
        rebuilt_parts.append(separator)

    return AttributionResult(
        text="".join(rebuilt_parts),
        selected_urls=selected_urls,
        selected_citation_ids=selected_citation_ids,
    )


def extract_citation_candidates(tool_name: str, tool_content: object) -> list[CitationCandidate]:
    """Extract snippet candidates from known tool payloads."""
    is_web_dict = (
        isinstance(tool_content, dict)
        and bool(tool_content)
        and all(
            isinstance(item, dict) and "url" in item and "snippets" in item
            for item in tool_content.values()
        )
    )
    is_rag_list = (
        isinstance(tool_content, list)
        and bool(tool_content)
        and all(isinstance(item, dict) and "content" in item and "url" in item for item in tool_content)
    )

    if tool_name not in {"web_search", "document_search_rag"} and not is_web_dict and not is_rag_list:
        return []

    # Brave-style dict payload: prefer web scope for web_search, otherwise RAG.
    if is_web_dict and isinstance(tool_content, dict):
        scope = "web" if tool_name == "web_search" else "rag"
        candidates: list[CitationCandidate] = []
        for item_idx, item in enumerate(tool_content.values()):
            if not isinstance(item, dict):
                continue
            source_url = item.get("url")
            snippets = item.get("snippets") or []
            if not source_url or not isinstance(snippets, list):
                continue
            for snippet_idx, snippet in enumerate(snippets):
                if not isinstance(snippet, str) or not snippet.strip():
                    continue
                citation_id = None
                clean_snippet = snippet
                tagged_match = _TAGGED_SNIPPET_RE.match(snippet)
                if tagged_match:
                    citation_id = tagged_match.group(1)
                    clean_snippet = _TAGGED_SNIPPET_RE.sub("", snippet, count=1)
                elif scope == "rag":
                    citation_id = f"rag_{item_idx}_{snippet_idx}"
                candidates.append(
                    CitationCandidate(
                        snippet=clean_snippet.strip(),
                        source_url=source_url,
                        scope=scope,
                        citation_id=citation_id,
                    )
                )
        return candidates

    if (tool_name == "document_search_rag" or is_rag_list) and isinstance(tool_content, list):
        candidates = []
        for item_idx, item in enumerate(tool_content):
            if not isinstance(item, dict):
                continue
            snippet = item.get("content")
            source_url = item.get("url")
            if not source_url:
                continue
            normalized_snippets = snippet if isinstance(snippet, list) else [snippet]
            for snippet_idx, candidate_snippet in enumerate(normalized_snippets):
                if not isinstance(candidate_snippet, str) or not candidate_snippet.strip():
                    continue
                candidates.append(
                    CitationCandidate(
                        snippet=candidate_snippet.strip(),
                        source_url=source_url,
                        scope="rag",
                        citation_id=f"rag_{item_idx}_{snippet_idx}",
                    )
                )
        return candidates
    return []


def _remap_citation_id(citation_id: str | None, url_index: int) -> str | None:
    """Rewrite ``scope_local_snippet`` ids to ``scope_{url_index}_snippet``."""
    if not citation_id:
        return None
    parts = citation_id.split("_")
    if len(parts) != 3:
        return citation_id
    scope, _local, snippet_idx = parts
    if scope not in {"web", "rag"} or not snippet_idx.isdigit():
        return citation_id
    return f"{scope}_{url_index}_{snippet_idx}"


def _split_completed_paragraphs(buffer: str) -> tuple[list[tuple[str, str]], str]:
    """Split buffer into completed paragraphs and trailing remainder.

    Each completed item is `(paragraph_text, separator)` where separator is the
    exact matched paragraph break (e.g. "\n\n" or "\n \n").
    """
    completed: list[tuple[str, str]] = []
    cursor = 0
    for match in _PARAGRAPH_BREAK_RE.finditer(buffer):
        paragraph = buffer[cursor : match.start()]
        if paragraph:
            completed.append((paragraph, match.group(0)))
        cursor = match.end()
    return completed, buffer[cursor:]


@dataclasses.dataclass(slots=True)
class CitationStreamAttributor:
    """Stateful transformer for streaming text attribution."""

    config: AttributionConfig
    candidates: list[CitationCandidate] = dataclasses.field(default_factory=list)
    _buffer: str = ""
    _url_to_index: dict[str, int] = dataclasses.field(default_factory=dict)

    def add_candidates(self, new_candidates: list[CitationCandidate]) -> list[CitationCandidate]:
        """Append candidates, remapping citation IDs to a stable global URL index.

        Returns the remapped candidates that were added (empty if nothing new).
        """
        if not new_candidates:
            return []

        remapped: list[CitationCandidate] = []
        for candidate in new_candidates:
            if candidate.source_url not in self._url_to_index:
                self._url_to_index[candidate.source_url] = len(self._url_to_index)
            url_index = self._url_to_index[candidate.source_url]
            remapped.append(
                dataclasses.replace(
                    candidate,
                    citation_id=_remap_citation_id(candidate.citation_id, url_index),
                )
            )

        # Dedupe by citation_id (or snippet+url when id missing).
        seen: set[str] = {
            c.citation_id or f"{c.source_url}::{c.snippet}" for c in self.candidates
        }
        unique_new: list[CitationCandidate] = []
        for candidate in remapped:
            key = candidate.citation_id or f"{candidate.source_url}::{candidate.snippet}"
            if key in seen:
                continue
            seen.add(key)
            unique_new.append(candidate)

        self.candidates.extend(unique_new)
        return unique_new

    def ordered_source_urls(self) -> list[str]:
        """Return source URLs in the citation-index order used for remapping."""
        return [url for url, _idx in sorted(self._url_to_index.items(), key=lambda item: item[1])]

    def drain(self, text_delta: str) -> list[StreamingAttributionChunk]:
        if not self.candidates:
            return [StreamingAttributionChunk(text=text_delta, selected_citation_ids=set())]
        self._buffer += text_delta
        completed_paragraphs, remainder = _split_completed_paragraphs(self._buffer)
        self._buffer = remainder
        chunks: list[StreamingAttributionChunk] = []
        for paragraph, separator in completed_paragraphs:
            attribution = attribute_citations_by_paragraph(
                paragraph,
                self.candidates,
                self.config,
            )
            chunks.append(
                StreamingAttributionChunk(
                    text=f"{attribution.text}{separator}",
                    selected_citation_ids=attribution.selected_citation_ids,
                    selected_urls=attribution.selected_urls,
                )
            )
        return chunks

    def flush(self) -> StreamingAttributionChunk | None:
        if not self._buffer:
            return None
        if not self.candidates:
            chunk = StreamingAttributionChunk(text=self._buffer, selected_citation_ids=set())
            self._buffer = ""
            return chunk
        attribution = attribute_citations_by_paragraph(self._buffer, self.candidates, self.config)
        self._buffer = ""
        return StreamingAttributionChunk(
            text=attribution.text,
            selected_citation_ids=attribution.selected_citation_ids,
            selected_urls=attribution.selected_urls,
        )
