"""Implementation of the Find API for RAG document search."""

import logging
import uuid
from typing import List, Optional
from urllib.parse import urljoin
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

import requests

from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_converter.parser import AlbertParser
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend
from utils.oidc import with_fresh_access_token

logger = logging.getLogger(__name__)


SUPPORTED_LANGUAGE_CODES = ["en", "fr", "de", "nl"]


class FindRagBackend(BaseRagBackend):
    """
    This class is a placeholder for the Find API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
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
        self.api_key = settings.FIND_API_KEY
        self.search_endpoint = "api/v1.0/documents/search/"
        self.indexing_endpoint = "api/v1.0/documents/index/"
        self.deleting_endpoint = "api/v1.0/documents/delete/"
        self.parser = AlbertParser()  # Find Rag relies on Albert parser

    def create_collection(self, name: str, description: Optional[str] = None) -> str:
        """
        init collection_id
        """
        self.collection_id = self.collection_id or str(uuid.uuid4())
        return self.collection_id

    @with_fresh_access_token
    def delete_collection(self, **kwargs) -> None:
        """
        Delete the current collection
        """
        response = requests.post(
            urljoin(settings.FIND_API_URL, self.deleting_endpoint),
            headers={"Authorization": f"Bearer {kwargs['session'].get('oidc_access_token')}"},
            json={"tags": [f"collection-{self.collection_id}"], "service": "conversations"},
            timeout=settings.FIND_API_TIMEOUT,
        )
        response.raise_for_status()

    def store_document(self, name: str, content: str, **kwargs) -> None:
        """
        index document in Find

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            user_sub (str): The user subject identifier for access control.
        """
        logger.debug("index document '%s' in Find", name)

        user_sub = kwargs.get("user_sub")
        if not user_sub:
            raise ValueError("user_sub is required to store document in FindRagBackend")

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
                "users": [user_sub],
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
            headers={"Authorization": f"Bearer {kwargs['session'].get('oidc_access_token')}"},
            json={
                "q": query or "*",
                "tags": [
                    f"collection-{collection_id}" for collection_id in self.get_all_collection_ids()
                ],
                "k": results_count,
            },
            timeout=settings.FIND_API_TIMEOUT,
        )
        response.raise_for_status()

        return RAGWebResults(
            data=[
                RAGWebResult(
                    url=get_language_value(result["_source"], "title"),
                    content=get_language_value(result["_source"], "content"),
                    score=result["_score"],
                )
                for result in response.json()
            ],
            usage=RAGWebUsage(
                prompt_tokens=0,
                completion_tokens=0,
            ),
        )


def get_language_value(source, language_field):
    """
    extract the value of the language field with the correct language_code extension.
    "title" and "content" have extensions like "title.en" or "title.fr".
    get_language_value will return the value regardless of the extension.
    """
    for language_code in SUPPORTED_LANGUAGE_CODES:
        if f"{language_field}.{language_code}" in source:
            return source[f"{language_field}.{language_code}"]
    raise ValueError(f"No '{language_field}' field with any supported language code in object")
