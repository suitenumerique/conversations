"""Implementation of the Find API for RAG document search."""

import logging
import uuid
from typing import List, Optional
from urllib.parse import urljoin
from uuid import uuid4

from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string

import requests

from chat.agent_rag.constants import RAGWebResult, RAGWebResults, RAGWebUsage
from chat.agent_rag.document_rag_backends.base_rag_backend import BaseRagBackend
from utils.oidc import with_fresh_access_token

logger = logging.getLogger(__name__)


SUPPORTED_LANGUAGE_CODES = ["en", "fr", "de", "nl"]


class FindFilterUnsupportedError(ValueError):
    """Raised when ``FindRagBackend.search`` is asked to apply a per-document filter.

    Find has no per-document identifier and does not index document names, so
    filtered queries cannot be honored. Raising fast (instead of returning the
    full collection silently) lets callers surface the capability gap rather
    than presenting unrelated results as if they came from the targeted
    document.
    """


class FindRagBackend(BaseRagBackend):
    """
    This class is a placeholder for the Find API implementation.
    It is designed to be used with the RAG (Retrieval-Augmented Generation) document search system.

    It provides methods to:
    - Store parsed documents in the Find index.
    - Perform a search operation using the Find API.

    Known limitations vs. ``AlbertRagBackend`` (operators selecting this backend
    via ``RAG_DOCUMENT_SEARCH_BACKEND`` should be aware):

    - ``store_document`` does not return a per-document id, so attachments
      indexed via Find have ``rag_document_id = NULL``. Per-document features
      that depend on it degrade:
      * Per-attachment delete: ``delete_document`` falls through to the base
        no-op. Chunks remain searchable in the Find index until the parent
        conversation/project is deleted and the whole collection is dropped.
      * Targeted RAG search: ``search`` raises ``FindFilterUnsupportedError``
        when ``document_id`` or ``document_name`` is provided, so callers can
        surface the gap to the user instead of silently broadening the query.
      * **RAG enable-gate**: ``AIAgentService._check_should_enable_rag`` uses
        ``rag_document_id`` as the "actually indexed" signal. Because Find
        never populates it, the gate never fires for Find-only deployments
        and the agent runs without RAG tools registered. Selecting Find is
        therefore a deliberate "no RAG tooling" choice until per-document
        ids are wired in.
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
        parser_class = import_string(settings.RAG_DOCUMENT_PARSER)
        self.parser = parser_class()

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

    def store_document(self, name: str, content: str, **kwargs) -> Optional[str]:
        """
        index document in Find

        Args:
            name (str): The name of the document.
            content (str): The content of the document in Markdown format.
            user_sub (str): The user subject identifier for access control.

        Returns:
            Optional[str]: Always None; Find does not expose a per-document
            identifier we can later use as a search filter or delete target.
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
    def search(  # pylint: disable=arguments-differ
        self,
        query: str,
        results_count: int = 4,
        document_name: Optional[str] = None,
        document_id: Optional[str] = None,
        **kwargs,
    ) -> RAGWebResults:
        """
        Perform a search using the Find API.
        Uses the user's OIDC token from the request session.

        Find does not support per-document filtering (no per-doc identifiers,
        no name-based metadata filter on the index). When ``document_name`` or
        ``document_id`` is provided, the call fails fast with
        ``FindFilterUnsupportedError`` so callers can surface the capability
        gap instead of silently presenting full-collection hits as if scoped
        to the targeted document.

        Args:
            query: The search query.
            results_count: Number of results to return.
            document_name: Must be ``None`` on Find. Otherwise raises
                ``FindFilterUnsupportedError``.
            document_id: Must be ``None`` on Find. Otherwise raises
                ``FindFilterUnsupportedError``.
            **kwargs: Additional arguments. Expected: 'session' containing OIDC tokens,

        Returns:
            RAGWebResults: The search results.

        Raises:
            FindFilterUnsupportedError: when ``document_id`` or
                ``document_name`` is not ``None``.
        """
        if document_id is not None:
            raise FindFilterUnsupportedError(
                "FindRagBackend cannot filter search by 'document_id': the Find "
                "backend exposes no per-document identifier. Either omit "
                "document_id or use a backend that supports per-document search."
            )
        if document_name is not None:
            raise FindFilterUnsupportedError(
                "FindRagBackend cannot filter search by 'document_name': the Find "
                "backend does not index document names. Either omit document_name "
                "or use a backend that supports per-document search."
            )
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
