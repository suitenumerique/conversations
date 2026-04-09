"""The "Edit in Docs" action: open an assistant message in a La Suite Docs document.

Conversations calls Docs as an OAuth 2.0 resource server, presenting the user's
stored OIDC access token. The action lives in its own mixin so the main viewset
stays readable.
"""

import logging
import re
from urllib.parse import urljoin

from django.conf import settings

import requests as http_requests
from rest_framework import decorators, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from chat import serializers
from chat.docs_client import DocsClient
from chat.views.helpers import conditional_refresh_oidc_token

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 60

_HEADER_RE = re.compile(r"^#{1,6}\s+(.*)")
# Leading whitespace, blockquote (>), bullet (-, *) and ordered-list (1.) markers.
_LEADING_MARKERS_RE = re.compile(r"^[\s>*\-]*(?:\d+\.\s+)?")


def _truncate_title(text):
    """Trim a title to TITLE_MAX_LENGTH characters on a word boundary."""
    text = text.strip()
    if len(text) <= TITLE_MAX_LENGTH:
        return text
    truncated = text[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0].rstrip()
    return f"{truncated or text[:TITLE_MAX_LENGTH].rstrip()}…"


def _build_doc_title(content):
    """Derive a document title from the assistant's markdown.

    1. the first markdown header (``#`` … ``######``) in document order;
    2. else the first non-empty line, stripped of leading markdown markers;
    3. else a generic default.

    The result is truncated to TITLE_MAX_LENGTH on a word boundary.
    """
    lines = content.splitlines()

    for line in lines:
        match = _HEADER_RE.match(line.strip())
        if match and match.group(1).strip():
            return _truncate_title(match.group(1))

    for line in lines:
        if not line.strip():
            continue
        cleaned = _LEADING_MARKERS_RE.sub("", line.strip()).strip("* ").strip()
        if cleaned:
            return _truncate_title(cleaned)

    return "Assistant response"


def _docs_http_error_response(exc):
    """Map an HTTP error returned by Docs to a meaningful client response.

    Docs rejects the call with a status; flattening all of them to 503 hides
    whether the user must re-authenticate, lacks access, or hit a transient error.
    """
    response = exc.response
    docs_status = response.status_code if response is not None else None

    if docs_status == status.HTTP_401_UNAUTHORIZED:
        # Access token rejected (expired / inactive on introspection). The front
        # can use the code to prompt a fresh login.
        logger.warning("Docs rejected the access token during edit-in-docs (401)")
        return Response(
            {
                "detail": "Your Docs session has expired. Please sign in again.",
                "code": "docs_authentication_expired",
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if docs_status == status.HTTP_403_FORBIDDEN:
        # Token valid but the user is not allowed on the Docs side — re-auth won't help.
        logger.warning("Docs denied access during edit-in-docs (403)")
        return Response(
            {"detail": "You are not allowed to create documents in Docs."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if docs_status is not None and 400 <= docs_status < 500:
        # Docs refused the request itself (e.g. conversion failed, file too big).
        # An integration fault, not user-retryable. Log only the status code for
        # for diagnosis without dumping potentially echoed user content into the logs.
        logger.error(
            "Docs rejected the edit-in-docs request (%s).",
            docs_status,
        )
        return Response(
            {"detail": "Could not create the document in Docs."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # 5xx (or unknown) — transient Docs error.
    logger.error("Docs returned a server error during edit-in-docs (%s)", docs_status)
    return Response(
        {"detail": "Docs service is currently unavailable. Please try again later."},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class EditInDocsMixin:
    """Adds the ``edit-in-docs`` action to a conversation viewset."""

    @conditional_refresh_oidc_token
    @decorators.action(
        methods=["post"], detail=True, url_path="edit-in-docs", url_name="edit-in-docs"
    )
    def edit_in_docs(self, request, pk):  # pylint: disable=unused-argument
        """Open a single assistant message in a new Docs document.

        Finds the assistant message by ID within the conversation's message array,
        extracts its markdown text content, and creates a document in Docs so the
        user can keep iterating on it in a real editor.

        Args:
            request: The HTTP request containing message_id in the body.
            pk: The primary key of the chat conversation.

        Returns:
            201 with docId and docUrl on success.
            400 if message_id is missing or the message is not found.
            401/403 if Docs rejects the access token or denies access.
            502 if Docs rejects the request, 503 if Docs is unreachable.
        """
        conversation = self.get_object()

        serializer = serializers.EditInDocsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message_id = serializer.validated_data["message_id"]

        # Find the assistant message by ID in the conversation's message array
        message = next(
            (m for m in conversation.messages if m.id == message_id and m.role == "assistant"),
            None,
        )
        if message is None:
            raise ValidationError({"message_id": "Assistant message not found."})

        # Content is already markdown — just join the text parts. Older/hydrated
        # messages may carry their text in the deprecated `content` field with no
        # populated text parts, so fall back to it (mirrors the frontend gate).
        content = "\n\n".join(part.text for part in message.parts if part.type == "text")
        if not content:
            content = message.content

        if not content:
            raise ValidationError({"message_id": "Message has no text content."})

        title = _build_doc_title(content)

        docs_client = DocsClient()
        try:
            doc_data = docs_client.create_document(
                title=title,
                content=content,
                session=request.session,  # for OIDC token
            )
        except http_requests.exceptions.HTTPError as exc:
            # Docs answered with a 4xx/5xx — map it to a meaningful client status
            # instead of masking everything as 503.
            return _docs_http_error_response(exc)
        except http_requests.exceptions.RequestException as exc:
            # Transport failure (connection refused, timeout, DNS) — Docs unreachable.
            logger.exception("Docs service unreachable during edit-in-docs: %s", exc)
            return Response(
                {"detail": "Docs service is currently unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "docId": doc_data["id"],
                "docUrl": urljoin(settings.DOCS_BASE_URL, f"docs/{doc_data['id']}/"),
            },
            status=status.HTTP_201_CREATED,
        )
