"""Implementation of the Albert API for RAG document search."""

import json
import logging
from io import BytesIO
from typing import List, Optional
from urllib.parse import urljoin

from django.conf import settings

import httpx
import requests

from chat.agent_rag.albert_api_constants import Searches
from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_converter.markitdown import DocumentConverter
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend

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


class AlbertRagBackend(BaseRagBackend):  # pylint: disable=too-many-instance-attributes
    """
    This class is a placeholder for the Albert API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
    - Create a collection for the search operation.
    - Parse documents and convert them to Markdown format:
       + Handle PDF parsing using the Albert API.
       + Use the DocumentConverter (markitdown) for other formats.
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
        self._pdf_parser_endpoint = urljoin(self._base_url, "/v1/parse-beta")
        self._search_endpoint = urljoin(self._base_url, "/v1/search")

        self._default_collection_description = "Temporary collection for RAG document search"

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

    def delete_collection(self) -> None:
        """
        Delete the current collection
        """
        response = requests.delete(
            urljoin(f"{self._collections_endpoint}/", self.collection_id),
            headers=self._headers,
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

    async def adelete_collection(self) -> None:
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

    def parse_pdf_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """
        Parse the PDF document content and return the text content.
        This method should handle the logic to convert the PDF into
        a format suitable for the Albert API.
        """
        response = requests.post(
            self._pdf_parser_endpoint,
            headers=self._headers,
            files={
                "file": (
                    name,
                    content,
                    content_type,
                ),  # Use the name as the filename in the request
                "output_format": (None, "markdown"),  # Specify the output format as Markdown,
            },
            timeout=settings.ALBERT_API_PARSE_TIMEOUT,
        )
        response.raise_for_status()

        return "\n\n".join(
            document_page["content"] for document_page in response.json().get("data", [])
        )

    def parse_document(self, name: str, content_type: str, content: BytesIO):
        """
        Parse the document and prepare it for the search operation.
        This method should handle the logic to convert the document
        into a format suitable for the Albert API.

        Args:
            name (str): The name of the document.
            content_type (str): The MIME type of the document (e.g., "application/pdf").
            content (BytesIO): The content of the document as a BytesIO stream.

        Returns:
            str: The document content in Markdown format.
        """
        # Implement the parsing logic here
        if content_type == "application/pdf":
            # Handle PDF parsing
            markdown_content = self.parse_pdf_document(
                name=name, content_type=content_type, content=content
            )
        else:
            markdown_content = DocumentConverter().convert_raw(
                name=name, content_type=content_type, content=content
            )

        return markdown_content

    def store_document(self, name: str, content: str) -> None:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.
        
        If the document is too large (exceeds Albert's token limit), it will be automatically
        split into multiple chunks and stored as separate documents.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
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
            
            # Store each chunk as a separate document
            for i, chunk in enumerate(chunks, start=1):
                chunk_name = f"{name}_part_{i}" if len(chunks) > 1 else name
                self._store_single_document(chunk_name, chunk)
        else:
            # Document fits within limit, store as-is
            self._store_single_document(name, content)
    
    def _store_single_document(self, name: str, content: str) -> None:
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
                "file": (f"{name}.md", BytesIO(content.encode("utf-8")), "text/markdown"),
                "collection": (None, int(self.collection_id)),
                "metadata": (None, json.dumps({"document_name": name})),  # undocumented API
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        logger.debug("Stored document '%s': %s", name, response.json())
        response.raise_for_status()

    async def astore_document(self, name: str, content: str) -> None:
        """
        Store the document content in the Albert collection.
        This method should handle the logic to send the document content to the Albert API.
        
        If the document is too large (exceeds Albert's token limit), it will be automatically
        split into multiple chunks and stored as separate documents.

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
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
            
            # Store each chunk as a separate document
            for i, chunk in enumerate(chunks, start=1):
                chunk_name = f"{name}_part_{i}" if len(chunks) > 1 else name
                await self._astore_single_document(chunk_name, chunk)
        else:
            # Document fits within limit, store as-is
            await self._astore_single_document(name, content)
    
    async def _astore_single_document(self, name: str, content: str) -> None:
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
                    "file": (f"{name}.md", BytesIO(content.encode("utf-8")), "text/markdown"),
                },
                data={
                    "collection": int(self.collection_id),
                    "metadata": json.dumps({"document_name": name}),  # undocumented API
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )
            logger.debug("Stored document '%s': %s", name, response.json())
            response.raise_for_status()

    def search(self, query, results_count: int = 4) -> RAGWebResults:
        """
        Perform a search using the Albert API based on the provided query.

        Args:
            query (str): The search query.
            results_count (int): The number of results to return.

        Returns:
            RAGWebResults: The search results.
        """
        collection_ids = self.get_all_collection_ids()  # might raise RuntimeError

        response = requests.post(
            urljoin(self._base_url, self._search_endpoint),
            headers=self._headers,
            json={
                "collections": collection_ids,
                "prompt": query,
                "score_threshold": 0.6,
                "k": results_count,  # Number of chunks to return from the search
            },
            timeout=settings.ALBERT_API_TIMEOUT,
        )
        response.raise_for_status()

        searches = Searches(**response.json())

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

    async def asearch(self, query, results_count: int = 4) -> RAGWebResults:
        """
        Perform an asynchronous search using the Albert API based on the provided query.

        Args:
            query (str): The search query.
            results_count (int): The number of results to return.

        Returns:
            RAGWebResults: The search results.
        """
        collection_ids = self.get_all_collection_ids()  # might raise RuntimeError

        async with httpx.AsyncClient(timeout=settings.ALBERT_API_TIMEOUT) as client:
            response = await client.post(
                urljoin(self._base_url, self._search_endpoint),
                headers=self._headers,
                json={
                    "collections": collection_ids,
                    "prompt": query,
                    "score_threshold": 0.6,
                    "k": results_count,  # Number of chunks to return from the search
                },
                timeout=settings.ALBERT_API_TIMEOUT,
            )

            logger.debug("Search response: %s %s", response.text, response.status_code)

            response.raise_for_status()

        searches = Searches(**response.json())

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
