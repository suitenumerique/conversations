"""Implementation of the Find API for RAG document search."""

import logging
import uuid
from io import BytesIO
from typing import List, Optional
from urllib.parse import urljoin
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

import requests

from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_converter.markitdown import DocumentConverter
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend
from utils.oidc import with_fresh_access_token

logger = logging.getLogger(__name__)


class FindRagBackend(BaseRagBackend):  # pylint: disable=too-many-instance-attributes
    """
    This class is a placeholder for the Find API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
    - Parse documents and convert them to Markdown format:
       + Handle PDF parsing using the Albert API.
       + Use the DocumentConverter (markitdown) for other formats.
    - Store parsed documents in the Find index.
    - Perform a search operation using the Find API.
    """

    def __init__(
        self,
        collection_id: Optional[str] = None,
        read_only_collection_id: Optional[List[str]] = None,
    ):
        # Initialize any necessary parameters or configurations here
        super().__init__(collection_id, read_only_collection_id)
        self._pdf_parser_endpoint = urljoin(settings.ALBERT_API_URL, "/v1/parse-beta")
        self.api_key = settings.FIND_API_KEY
        self.search_endpoint = "api/v1.0/documents/search/"
        self.indexing_endpoint = "api/v1.0/documents/index/"

        if not self.api_key:
            raise ImproperlyConfigured("FIND_API_KEY must be set in Django settings.")

    def create_collection(self, name: str, description: Optional[str] = None) -> uuid.UUID:
        """
        init collection_id
        """
        self.collection_id = self.collection_id or uuid.uuid4()
        return self.collection_id

    def delete_collection(self) -> None:
        """
        Deletion not available
        """
        logger.warning("deletion of collections is not yet supported in FindRagBackend")

    # TODO: factor with albert api
    def parse_pdf_document(self, name: str, content_type: str, content: BytesIO) -> str:
        """
        Parse the PDF document content and return the text content.
        This method should handle the logic to convert the PDF into
        a format suitable for the Albert API.
        """
        response = requests.post(
            self._pdf_parser_endpoint,
            headers={
                "Authorization": f"Bearer {settings.ALBERT_API_KEY}",
            },
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

    # TODO: factor with albert api
    def parse_document(self, name: str, content_type: str, content: BytesIO):
        """
        Parse the document and prepare it for the search operation.
        This method should handle the logic to convert the document
        into a format suitable for the Find API.

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

    def store_document(self, name: str, content: str, **kwargs) -> None:
        """
        index document in Find

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            user_sub (str): The user subject identifier for access control.
        """
        logger.debug("index document '%s' in Find", name)
        response = requests.post(
            urljoin(settings.FIND_API_URL, self.indexing_endpoint),
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "id": str(uuid4()),
                "title": str(name) or "",
                "depth": 0,
                "path": str(name) or "",
                "numchild": 0,
                "content": content or "",
                "created_at": timezone.now().isoformat(),
                "updated_at": timezone.now().isoformat(),
                "tags": [f"collection-{self.collection_id}"],
                "size": len(content.encode("utf-8")),
                "users": [kwargs["user_sub"]] if "user_sub" in kwargs else [],
                "groups": [],
                "reach": "authenticated",
                "is_active": True,
            },
            timeout=settings.FIND_API_TIMEOUT,
        )
        response.raise_for_status()

    @with_fresh_access_token
    def search(self, query: str, results_count: int = 4, **kwargs) -> RAGWebResults:
        """
        Perform a search using the Find API.
        Uses the user's OIDC token from the request session.

        Args:
            query: The search query.
            results_count: Number of results to return.
            **kwargs: Additional arguments. Expected: 'session' containing OIDC tokens,

        Returns:
            RAGWebResults: The search results.
        """
        logger.debug("search documents in Find with query '%s'", query)

        response = requests.post(
            urljoin(settings.FIND_API_URL, self.search_endpoint),
            headers={"Authorization": f"Bearer {kwargs["session"].get("oidc_access_token")}"},
            json={
                "q": query,
                "tags": [f"collection-{collection_id}" for collection_id in self.get_all_collection_ids()],
                "k": results_count,
            },
            timeout=settings.FIND_API_TIMEOUT,
        )
        logger.debug(response.json())
        response.raise_for_status()

        return RAGWebResults(
            data=[
                RAGWebResult(
                    url=result["_source"]["title.fr"],
                    content=result["_source"]["content.fr"],
                    score=result["_score"],
                )
                for result in response.json()
            ],
            usage=RAGWebUsage(
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )
