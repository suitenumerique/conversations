"""Implementation of the Albert API for RAG document search."""

import json
import logging
from io import BytesIO
from typing import List, Optional
from urllib.parse import urljoin

from django.conf import settings
from django.utils.module_loading import import_string

import httpx
import requests

from chat.agent_rag.albert_api_constants import Searches
from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend
from chat.constants import MARKDOWN_MIME_TYPE

logger = logging.getLogger(__name__)

# Albert API token limit for document vectorization
# We use a conservative chunk size to stay well under the limit
ALBERT_MAX_TOKENS = 8192
ALBERT_CHUNK_SIZE_TOKENS = 5000  # More conservative chunk size with larger safety margin
# Approximate tokens: ~3 characters per token (more conservative estimate for Markdown/Excel)
# Markdown and Excel content often have more tokens per character due to formatting
ALBERT_CHUNK_SIZE_CHARS = ALBERT_CHUNK_SIZE_TOKENS * 3


def _estimate_tokens(content: str) -> int:
    """
    Estimate the number of tokens in a text string.
    
    Uses a conservative approximation: ~3 characters per token.
    This is more conservative than 4 chars/token to account for:
    - Markdown formatting (headers, lists, tables)
    - Excel content with special characters
    - Whitespace and punctuation
    
    Args:
        content (str): The text content to estimate.
        
    Returns:
        int: Estimated number of tokens.
    """
    return len(content) // 3


def _chunk_content(content: str, max_chars: int = ALBERT_CHUNK_SIZE_CHARS) -> List[str]:
    """
    Split content into chunks that fit within Albert's token limit.
    
    Attempts to split at paragraph boundaries (double newlines) when possible,
    otherwise splits at line boundaries, and finally at character boundaries.
    Validates that each chunk is under the token limit after splitting.
    
    Args:
        content (str): The content to chunk.
        max_chars (int): Maximum characters per chunk (default: ALBERT_CHUNK_SIZE_CHARS).
        
    Returns:
        list[str]: List of content chunks, each under the token limit.
    """
    # First check if content fits in one chunk
    estimated_tokens = _estimate_tokens(content)
    if estimated_tokens <= ALBERT_CHUNK_SIZE_TOKENS:
        return [content]
    
    chunks = []
    remaining = content
    
    while len(remaining) > 0:
        # Check if remaining content fits in one chunk
        remaining_tokens = _estimate_tokens(remaining)
        if remaining_tokens <= ALBERT_CHUNK_SIZE_TOKENS:
            if remaining.strip():
                chunks.append(remaining.strip())
            break
        
        # Need to split - find the best split point
        # Start with max_chars but may need to reduce if token estimate is too high
        search_limit = max_chars
        
        # Try to find a split point that keeps us under token limit
        # Reduce search limit if needed to ensure token limit is respected
        while search_limit > 100:  # Minimum chunk size
            # Try to split at paragraph boundary (double newline)
            split_pos = remaining.rfind("\n\n", 0, search_limit)
            if split_pos == -1:
                # Try to split at single newline
                split_pos = remaining.rfind("\n", 0, search_limit)
            if split_pos == -1:
                # Force split at character boundary
                split_pos = search_limit
            
            # Validate that this chunk is under token limit
            chunk_candidate = remaining[:split_pos].strip()
            if chunk_candidate:
                chunk_tokens = _estimate_tokens(chunk_candidate)
                if chunk_tokens <= ALBERT_CHUNK_SIZE_TOKENS:
                    chunks.append(chunk_candidate)
                    remaining = remaining[split_pos:].lstrip()
                    break
            
            # Chunk too large, reduce search limit and try again
            search_limit = int(search_limit * 0.8)  # Reduce by 20%
        else:
            # Fallback: force split at a safe size
            # This should rarely happen, but ensures we don't get stuck
            safe_size = min(max_chars, len(remaining))
            chunk = remaining[:safe_size].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[safe_size:].lstrip()
    
    # Validate all chunks are under limit and split further if needed
    validated_chunks = []
    for chunk_item in chunks:
        chunk_tokens = _estimate_tokens(chunk_item)
        if chunk_tokens > ALBERT_MAX_TOKENS:
            logger.warning(
                "Chunk still exceeds token limit (%d tokens, max: %d), forcing split further",
                chunk_tokens,
                ALBERT_MAX_TOKENS,
            )
            # Force split this chunk further using a more conservative size
            # Use a size that ensures we stay well under the token limit
            # Target: ~5000 tokens max per chunk (conservative)
            max_safe_chars = ALBERT_CHUNK_SIZE_TOKENS * 3  # 6000 * 3 = 18000 chars for ~5000 tokens
            remaining_chunk = chunk_item
            while len(remaining_chunk) > 0:
                remaining_tokens = _estimate_tokens(remaining_chunk)
                if remaining_tokens <= ALBERT_CHUNK_SIZE_TOKENS:
                    if remaining_chunk.strip():
                        validated_chunks.append(remaining_chunk.strip())
                    break
                
                # Find a safe split point
                split_pos = min(max_safe_chars, len(remaining_chunk))
                # Try to split at a line boundary if possible
                line_split = remaining_chunk.rfind("\n", 0, split_pos)
                if line_split > max_safe_chars * 0.5:  # Only use if it's not too small
                    split_pos = line_split
                
                sub_chunk = remaining_chunk[:split_pos].strip()
                if sub_chunk:
                    sub_tokens = _estimate_tokens(sub_chunk)
                    # Double-check this sub-chunk is safe
                    if sub_tokens > ALBERT_MAX_TOKENS:
                        # Still too large, use even smaller size
                        logger.warning(
                            "Sub-chunk still too large (%d tokens), using smaller split",
                            sub_tokens,
                        )
                        split_pos = ALBERT_CHUNK_SIZE_TOKENS * 2  # 12000 chars for ~3000 tokens
                        sub_chunk = remaining_chunk[:split_pos].strip()
                    validated_chunks.append(sub_chunk)
                remaining_chunk = remaining_chunk[split_pos:].lstrip()
        else:
            validated_chunks.append(chunk_item)
    
    # Final validation - ensure NO chunk exceeds the limit
    final_chunks = []
    for chunk in validated_chunks:
        chunk_tokens = _estimate_tokens(chunk)
        if chunk_tokens > ALBERT_MAX_TOKENS:
            logger.error(
                "CRITICAL: Chunk still exceeds limit after all splitting attempts: %d tokens",
                chunk_tokens,
            )
            # Emergency split: use very conservative size
            emergency_size = ALBERT_CHUNK_SIZE_TOKENS * 2  # 12000 chars
            remaining = chunk
            while len(remaining) > 0:
                emergency_chunk = remaining[:emergency_size].strip()
                if emergency_chunk:
                    final_chunks.append(emergency_chunk)
                remaining = remaining[emergency_size:].lstrip()
        else:
            final_chunks.append(chunk)
    
    return final_chunks


class AlbertMissingDocumentIdError(RuntimeError):
    """Raised when an Albert document-store response lacks the expected ``id``.

    Albert's contract is to return the new document id on success. A 2xx with
    no ``id`` would leave us with chunks indexed upstream but no handle to
    filter or delete them, so the failure is surfaced loudly instead of
    persisting a half-indexed attachment.
    """


class AlbertRagBackend(BaseRagBackend):  # pylint: disable=too-many-instance-attributes
    """
    This class is a placeholder for the Albert API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
    - Create a collection for the search operation.
    - Store parsed documents in the Albert collection.
    - Perform a search operation using the Albert API.
    """

    def __init__(
        self,
        collection_id: Optional[str] = None,
        read_only_collection_id: Optional[List[str]] = None,
    ):
        # Initialize any necessary parameters or configurations here
        super().__init__(collection_id, read_only_collection_id)
        self._base_url = settings.ALBERT_API_URL
        self._headers = {
            "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
        }
        self._collections_endpoint = urljoin(self._base_url, "/v1/collections")
        self._documents_endpoint = urljoin(self._base_url, "/v1/documents")
        self._search_endpoint = urljoin(self._base_url, "/v1/search")
        self._default_collection_description = "Temporary collection for RAG document search"
        parser_class = import_string(settings.RAG_DOCUMENT_PARSER)
        self.parser = parser_class()

    @staticmethod
    def cast_collection_id(collection_id):
        """Albert API expects int Ids."""
        return int(collection_id)

    def create_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        response = requests.post(
            self._collections_endpoint,
            headers=self._headers,
            json={
                "name": name,
                "description": description or self._default_collection_description,
                "visibility": "private",
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()
        self.collection_id = str(response.json()["id"])
        return self.collection_id

    async def acreate_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        Create a temporary collection for the search operation.
        This method should handle the logic to create or retrieve an existing collection.
        """
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                self._collections_endpoint,
                headers=self._headers,
                json={
                    "name": name,
                    "description": description or self._default_collection_description,
                    "visibility": "private",
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            response.raise_for_status()

        self.collection_id = str(response.json()["id"])
        return self.collection_id

    def delete_collection(self, **kwargs) -> None:
        """
        Delete the current collection
        """
        response = requests.delete(
            urljoin(f"{self._collections_endpoint}/", self.collection_id),
            headers=self._headers,
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

    def delete_document(self, document_id: str, **kwargs) -> None:
        """Remove a single document from Albert via DELETE /v1/documents/{id}."""
        response = requests.delete(
            urljoin(f"{self._documents_endpoint}/", str(document_id)),
            headers=self._headers,
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

    async def adelete_collection(self, **kwargs) -> None:
        """
        Asynchronously delete the current collection
        """
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.delete(
                urljoin(f"{self._collections_endpoint}/", self.collection_id),
                headers=self._headers,
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            response.raise_for_status()

    def store_document(self, name: str, content: str, **kwargs) -> Optional[str]:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.
        
        If the document is too large (exceeds Albert's token limit), it will be automatically
        split into multiple chunks and stored as separate documents.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            **kwargs: Additional arguments.

        Returns:
            Optional[str]: The Albert document id, used later as a `document_ids`
            filter on `/v1/search` and as the target of `delete_document`.
        """
        # Check if content needs to be chunked
        estimated_tokens = _estimate_tokens(content)
        
        if estimated_tokens > ALBERT_MAX_TOKENS:
            logger.info(
                "Document '%s' is too large (%d estimated tokens, limit: %d). "
                "Splitting into chunks.",
                name,
                estimated_tokens,
                ALBERT_MAX_TOKENS,
            )
            chunks = _chunk_content(content)
            logger.info("Split document '%s' into %d chunks", name, len(chunks))
            
            # Store each chunk as a separate document; return the first id for
            # attachment tracking (subsequent parts remain searchable in collection).
            document_id = None
            for i, chunk in enumerate(chunks, start=1):
                chunk_name = f"{name}_part_{i}" if len(chunks) > 1 else name
                chunk_id = self._store_single_document(chunk_name, chunk)
                if document_id is None:
                    document_id = chunk_id
            return document_id

        # Document fits within limit, store as-is
        return self._store_single_document(name, content)

    def _store_single_document(self, name: str, content: str) -> str:
        """
        Store a single document chunk in the Albert collection.
        
        Internal method that performs the actual API call to store one document.
        
        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
        """
        response = requests.post(
            urljoin(self._base_url, self._documents_endpoint),
            headers=self._headers,
            files={
                "file": (f"{name}.md", BytesIO(content.encode("utf-8")), MARKDOWN_MIME_TYPE),
                "collection_id": (None, int(self.collection_id)),
                "metadata": (None, json.dumps({"document_name": name})),  # undocumented API
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        logger.debug(response.text)
        response.raise_for_status()
        body = response.json()
        document_id = body.get("id")
        if document_id is None:
            raise AlbertMissingDocumentIdError(
                f"Albert document-store response is missing an 'id': {body!r}"
            )
        return str(document_id)

    async def astore_document(self, name: str, content: str, **kwargs) -> Optional[str]:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.
        
        If the document is too large (exceeds Albert's token limit), it will be automatically
        split into multiple chunks and stored as separate documents.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            **kwargs: Additional arguments.

        Returns:
            Optional[str]: See `store_document`.
        """
        # Check if content needs to be chunked
        estimated_tokens = _estimate_tokens(content)
        
        if estimated_tokens > ALBERT_MAX_TOKENS:
            logger.info(
                "Document '%s' is too large (%d estimated tokens, limit: %d). "
                "Splitting into chunks.",
                name,
                estimated_tokens,
                ALBERT_MAX_TOKENS,
            )
            chunks = _chunk_content(content)
            logger.info("Split document '%s' into %d chunks", name, len(chunks))
            
            # Validate chunks before storing
            for i, chunk in enumerate(chunks, start=1):
                chunk_tokens = _estimate_tokens(chunk)
                logger.debug(
                    "Chunk %d/%d: %d chars, ~%d tokens",
                    i,
                    len(chunks),
                    len(chunk),
                    chunk_tokens,
                )
                if chunk_tokens > ALBERT_MAX_TOKENS:
                    logger.error(
                        "Chunk %d/%d still exceeds token limit: %d tokens (max: %d)",
                        i,
                        len(chunks),
                        chunk_tokens,
                        ALBERT_MAX_TOKENS,
                    )
            
            # Store each chunk as a separate document; return the first id for
            # attachment tracking (subsequent parts remain searchable in collection).
            document_id = None
            for i, chunk in enumerate(chunks, start=1):
                chunk_name = f"{name}_part_{i}" if len(chunks) > 1 else name
                chunk_id = await self._astore_single_document(chunk_name, chunk)
                if document_id is None:
                    document_id = chunk_id
            return document_id

        # Document fits within limit, store as-is
        return await self._astore_single_document(name, content)

    async def _astore_single_document(self, name: str, content: str) -> str:
        """
        Store a single document chunk in the Albert collection.
        
        Internal method that performs the actual API call to store one document.
        
        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
        """
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                urljoin(self._base_url, self._documents_endpoint),
                headers=self._headers,
                files={
                    "file": (f"{name}.md", BytesIO(content.encode("utf-8")), MARKDOWN_MIME_TYPE),
                },
                data={
                    "collection_id": int(self.collection_id),
                    "metadata": json.dumps({"document_name": name}),  # undocumented API
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            logger.debug(response.text)
            response.raise_for_status()
            body = response.json()
        document_id = body.get("id")
        if document_id is None:
            raise AlbertMissingDocumentIdError(
                f"Albert document-store response is missing an 'id': {body!r}"
            )
        return str(document_id)

    def _build_search_payload(
        self,
        query: str,
        results_count: int,
        document_name: Optional[str],
        document_id: Optional[str],
    ) -> dict:
        """Assemble the /v1/search request body shared by sync and async paths.

        When `document_id` is provided, it is preferred over `document_name`:
        Albert's `document_ids` filter is collection-aware and unambiguous,
        whereas `metadata_filters: document_name` matches by name across every
        collection in `collection_ids` (which fails when conversation and project
        each carry a doc with the same filename).
        """
        payload: dict = {
            "collection_ids": self.get_all_collection_ids(),  # might raise RuntimeError
            "query": query,
            "score_threshold": 0.6,
            "limit": results_count,
        }
        if document_id:
            payload["document_ids"] = [int(document_id)]
        elif document_name:
            payload["metadata_filters"] = {
                "key": "document_name",
                "value": document_name,
                "type": "eq",
            }
        return payload

    @staticmethod
    def _parse_search_response(
        json_body: dict, document_name: Optional[str], document_id: Optional[str]
    ) -> RAGWebResults:
        """Map an Albert /v1/search response into our RAGWebResults shape."""
        searches = Searches(**json_body)

        if not searches.data and (document_name or document_id):
            logger.info(
                "RAG search with document_name=%r document_id=%r returned no results.",
                document_name,
                document_id,
            )

        return RAGWebResults(
            data=[
                RAGWebResult(
                    url=result.chunk.metadata["document_name"],
                    content=result.chunk.content,
                    score=result.score,
                )
                for result in searches.data
            ],
            usage=RAGWebUsage(
                prompt_tokens=searches.usage.prompt_tokens,
                completion_tokens=searches.usage.completion_tokens,
            ),
        )

    def search(
        self,
        query: str,
        results_count: int = 4,
        document_name: Optional[str] = None,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> RAGWebResults:
        """Perform a search using the Albert API based on the provided query."""
        payload = self._build_search_payload(query, results_count, document_name, document_id)
        response = requests.post(
            urljoin(self._base_url, self._search_endpoint),
            headers=self._headers,
            json=payload,
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()
        return self._parse_search_response(response.json(), document_name, document_id)

    async def asearch(
        self,
        query: str,
        results_count: int = 4,
        document_name: Optional[str] = None,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> RAGWebResults:
        """Perform an asynchronous search using the Albert API based on the provided query."""
        payload = self._build_search_payload(query, results_count, document_name, document_id)
        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                urljoin(self._base_url, self._search_endpoint),
                headers=self._headers,
                json=payload,
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            logger.debug("Search response: %s %s", response.text, response.status_code)
            response.raise_for_status()
        return self._parse_search_response(response.json(), document_name, document_id)
