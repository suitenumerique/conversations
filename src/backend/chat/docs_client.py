"""Implementation of the La Suite Docs External API."""

from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import PermissionDenied

import requests


class DocsClient:
    """
    Client for interacting with the La Suite Docs External API.
    It provides methods to:
        - Create a new document in Docs
        - ... more methods can be added here as needed.
    """

    def __init__(self):
        """Initialize the DocsClient with necessary configuration.
        The API URL and timeout are set based on Django settings."""
        self.timeout = settings.DOCS_API_TIMEOUT
        self.api_url = urljoin(settings.DOCS_BASE_URL, "external_api/v1.0/")

    def get_access_token(self, session):
        """Retrieve the OIDC access token from the user's session."""
        access_token = session.get("oidc_access_token")
        if not access_token:
            raise PermissionDenied("User is not authenticated with OIDC.")
        return access_token

    def create_document(self, title: str, content: str, session, **kwargs) -> dict:
        """
        POST /external_api/v1.0/documents/ with markdown file upload (multipart).
        """
        access_token = self.get_access_token(session)
        file = BytesIO(content.encode("utf-8"))
        file.name = f"{title}.md"
        response = requests.post(
            urljoin(self.api_url, "documents/"),
            headers={"Authorization": f"Bearer {access_token}"},
            files={"file": (file.name, file, "text/markdown")},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
