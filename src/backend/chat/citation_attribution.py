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
_WEB_REF_RE = re.compile(r"<ref id=\"(web_\d+_\d+)\"\s*/>")
_TAGGED_WEB_SNIPPET_RE = re.compile(r"^\[ref:(web_\d+_\d+)\]\s*")


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
    debug_logging: bool = False


@dataclasses.dataclass(slots=True)
class AttributionResult:
    """Attribution output used by chat finalization."""

    text: str
    selected_urls: set[str]
    selected_web_citation_ids: set[str]


@dataclasses.dataclass(slots=True)
class StreamingAttributionChunk:
    """Streaming chunk produced by citation attribution."""

    text: str
    selected_web_citation_ids: set[str]


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


def _iter_sentence_pairs(text: str) -> Iterable[tuple[str, tuple[int, int]]]:
    """Yield consecutive 2-sentence chunks (last one can be single)."""
    sentences = list(_iter_sentences(text))
    idx = 0
    while idx < len(sentences):
        first_text, first_span = sentences[idx]
        if idx + 1 < len(sentences):
            second_text, second_span = sentences[idx + 1]
            yield text[first_span[0] : second_span[1]], (first_span[0], second_span[1])
            idx += 2
        else:
            yield first_text, first_span
            idx += 1


def _inject_web_refs(sentence: str, web_ids: list[str], max_sources: int) -> str:
    existing_ids = _WEB_REF_RE.findall(sentence)
    sentence_without_refs = _WEB_REF_RE.sub("", sentence).rstrip()
    combined_ids = list(dict.fromkeys(existing_ids + web_ids))
    combined_ids.sort(key=lambda citation_id: tuple(map(int, citation_id.replace("web_", "").split("_"))))
    if max_sources > 0:
        combined_ids = combined_ids[:max_sources]
    if not combined_ids:
        return sentence_without_refs
    refs = " ".join(f'<ref id="{citation_id}"/>' for citation_id in combined_ids)
    return f"{sentence_without_refs} {refs}"


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
            selected_web_citation_ids=set(),
        )

    selected_urls: set[str] = set()
    selected_web_ids: set[str] = set()
    rebuilt_parts: list[str] = []
    cursor = 0

    for sentence, (start, end) in _iter_sentence_pairs(text):
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

        sentence_web_ids: list[str] = []
        for _score, candidate in selected_sentence:
            selected_urls.add(candidate.source_url)
            if candidate.citation_id:
                sentence_web_ids.append(candidate.citation_id)
                selected_web_ids.add(candidate.citation_id)

        rebuilt_parts.append(
            _inject_web_refs(
                sentence,
                sentence_web_ids,
                config.max_sources_per_sentence,
            )
        )
        cursor = end

    rebuilt_parts.append(text[cursor:])
    return AttributionResult(
        text="".join(rebuilt_parts),
        selected_urls=selected_urls,
        selected_web_citation_ids=selected_web_ids,
    )


def extract_citation_candidates(tool_name: str, tool_content: object) -> list[CitationCandidate]:
    """Extract snippet candidates from known tool payloads."""
    inferred_web_payload = (
        isinstance(tool_content, dict)
        and bool(tool_content)
        and all(
            isinstance(item, dict) and "url" in item and "snippets" in item
            for item in tool_content.values()
        )
    )
    inferred_rag_payload = (
        isinstance(tool_content, list)
        and bool(tool_content)
        and all(isinstance(item, dict) and "content" in item and "url" in item for item in tool_content)
    )

    if (
        tool_name not in {"web_search", "document_search_rag"}
        and not inferred_web_payload
        and not inferred_rag_payload
    ):
        return []

    if (tool_name == "web_search" or inferred_web_payload) and isinstance(tool_content, dict):
        candidates: list[CitationCandidate] = []
        for item in tool_content.values():
            if not isinstance(item, dict):
                continue
            source_url = item.get("url")
            snippets = item.get("snippets") or []
            if not source_url or not isinstance(snippets, list):
                continue
            for snippet in snippets:
                if not isinstance(snippet, str) or not snippet.strip():
                    continue
                citation_id = None
                clean_snippet = snippet
                tagged_match = _TAGGED_WEB_SNIPPET_RE.match(snippet)
                if tagged_match:
                    citation_id = tagged_match.group(1)
                    clean_snippet = _TAGGED_WEB_SNIPPET_RE.sub("", snippet, count=1)
                candidates.append(
                    CitationCandidate(
                        snippet=clean_snippet.strip(),
                        source_url=source_url,
                        scope="web",
                        citation_id=citation_id,
                    )
                )
        return candidates

    if (tool_name == "document_search_rag" or inferred_rag_payload) and isinstance(tool_content, list):
        candidates = []
        for item in tool_content:
            if not isinstance(item, dict):
                continue
            snippet = item.get("content")
            source_url = item.get("url")
            if not isinstance(snippet, str) or not snippet.strip() or not source_url:
                continue
            candidates.append(
                CitationCandidate(
                    snippet=snippet.strip(),
                    source_url=source_url,
                    scope="rag",
                )
            )
        return candidates
    return []


def _split_completed_sentence_pairs(buffer: str) -> tuple[list[str], str]:
    """Split buffer into completed 2-sentence chunks and trailing remainder."""
    completed_sentences: list[str] = []
    start = 0
    for idx, char in enumerate(buffer):
        if char in ".!?":
            completed_sentences.append(buffer[start : idx + 1])
            start = idx + 1
    if len(completed_sentences) < 2:
        return [], buffer

    completed_pairs: list[str] = []
    pair_count = len(completed_sentences) // 2
    consumed_chars = 0
    sentence_cursor = 0
    for _ in range(pair_count):
        first = completed_sentences[sentence_cursor]
        second = completed_sentences[sentence_cursor + 1]
        completed_pairs.append(first + second)
        consumed_chars += len(first) + len(second)
        sentence_cursor += 2
    return completed_pairs, buffer[consumed_chars:]


@dataclasses.dataclass(slots=True)
class CitationStreamAttributor:
    """Stateful transformer for streaming text attribution."""

    config: AttributionConfig
    candidates: list[CitationCandidate] = dataclasses.field(default_factory=list)
    _buffer: str = ""

    def add_candidates(self, new_candidates: list[CitationCandidate]) -> None:
        if new_candidates:
            self.candidates.extend(new_candidates)

    def drain(self, text_delta: str) -> list[StreamingAttributionChunk]:
        if not self.candidates:
            return [StreamingAttributionChunk(text=text_delta, selected_web_citation_ids=set())]
        self._buffer += text_delta
        completed_pairs, remainder = _split_completed_sentence_pairs(self._buffer)
        self._buffer = remainder
        chunks: list[StreamingAttributionChunk] = []
        for pair in completed_pairs:
            attribution = attribute_citations(pair, self.candidates, self.config)
            chunks.append(
                StreamingAttributionChunk(
                    text=attribution.text,
                    selected_web_citation_ids=attribution.selected_web_citation_ids,
                )
            )
        return chunks

    def flush(self) -> StreamingAttributionChunk | None:
        if not self._buffer:
            return None
        if not self.candidates:
            chunk = StreamingAttributionChunk(text=self._buffer, selected_web_citation_ids=set())
            self._buffer = ""
            return chunk
        attribution = attribute_citations(self._buffer, self.candidates, self.config)
        self._buffer = ""
        return StreamingAttributionChunk(
            text=attribution.text,
            selected_web_citation_ids=attribution.selected_web_citation_ids,
        )
