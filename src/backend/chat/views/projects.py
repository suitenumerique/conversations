"""ViewSet for managing chat projects."""

import logging

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils.module_loading import import_string

from rest_framework import filters, permissions, viewsets

from core.api.viewsets import Pagination

from activation_codes.permissions import IsActivatedUser
from chat import models, serializers
from chat.views.filters import TitleSearchFilter
from chat.views.helpers import _bulk_delete_s3_blobs

logger = logging.getLogger(__name__)


class ChatProjectViewSet(viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """ViewSet for managing projects."""

    pagination_class = Pagination
    permission_classes = [
        IsActivatedUser,  # see activation_codes application
        permissions.IsAuthenticated,
    ]
    ordering = ["title"]
    ordering_fields = ["title", "created_at", "updated_at"]
    queryset = models.ChatProject.objects
    serializer_class = serializers.ChatProjectSerializer
    filter_backends = [filters.OrderingFilter, TitleSearchFilter]

    def get_queryset(self):
        """Return the queryset for the projects."""

        conversations_prefetch = Prefetch(  # Prefetch conversations ordered by most recent first
            "conversations",
            queryset=models.ChatConversation.objects.order_by("-created_at"),
        )
        return (
            self.queryset.filter(owner=self.request.user).prefetch_related(conversations_prefetch)
            if self.request.user.is_authenticated
            else self.queryset.none()
        )

    def perform_destroy(self, instance):
        """Delete a project, its conversations, RAG collections, and S3 blobs.

        ChatConversation.project uses on_delete=SET_NULL (to avoid accidental
        cascade), so we explicitly delete conversations here.

        The bulk QuerySet delete below bypasses ChatViewSet.perform_destroy,
        so we drop each child conversation's RAG collection here too -
        otherwise they would outlive the project. Backend failures are logged
        but do not block the user-facing delete - a dangling collection is
        preferable to a project the user cannot remove.

        S3 blobs for both project-level and child-conversation attachments are
        cleaned up before the DB cascade runs, since Django CASCADE drops
        attachment rows without touching object storage. Markdown companions
        share their key with the original, so unique keys are deduplicated.
        """
        # Same NULL-or-empty handling as ChatProjectAttachmentViewSet.get_queryset:
        # collection_id is CharField(null=True, blank=True), so both states exist.
        conversations_with_collection = instance.conversations.exclude(
            Q(collection_id__isnull=True) | Q(collection_id="")
        )
        for conv in conversations_with_collection:
            try:
                backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                backend_class(collection_id=conv.collection_id).delete_collection(
                    session=self.request.session,
                )
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to delete RAG collection %s for conversation %s",
                    conv.collection_id,
                    conv.pk,
                )

        # Collect all S3 keys (project + child conversations) before any DB
        # cascade so the queries still resolve to live rows.
        attachment_keys = set(instance.attachments.values_list("key", flat=True)) | set(
            models.ChatConversationAttachment.objects.filter(
                conversation__project=instance
            ).values_list("key", flat=True)
        )
        instance.conversations.all().delete()
        if instance.collection_id:
            try:
                backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                backend_class(collection_id=instance.collection_id).delete_collection(
                    session=self.request.session,
                )
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to delete RAG collection %s for project %s",
                    instance.collection_id,
                    instance.pk,
                )
        _bulk_delete_s3_blobs(attachment_keys)
        instance.delete()
