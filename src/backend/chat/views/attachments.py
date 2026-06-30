"""Attachment viewsets scoped to chat conversations and projects."""

import logging
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import Http404
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

import magic
import posthog
from lasuite.malware_detection import malware_detection
from rest_framework import decorators, mixins, permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.api.viewsets import SerializerPerActionMixin
from core.file_upload import enums
from core.file_upload.enums import AttachmentStatus
from core.file_upload.mixins import AttachmentMixin
from core.file_upload.serializers import FileUploadSerializer

from activation_codes.permissions import IsActivatedUser
from chat import models, serializers
from chat.constants import IMAGE_MIME_PREFIX
from chat.views.helpers import _bulk_delete_s3_blobs

logger = logging.getLogger(__name__)


class BaseAttachmentViewSet(
    SerializerPerActionMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Base viewset for attachment management (conversation or project scoped).

    Subclasses must define:
    - holder_field: FK field name on the attachment ("conversation" or "project")
    - holder_id_field: FK pk filter name ("conversation_id" or "project_id")
    - holder_pk_kwarg: URL kwarg name ("conversation_pk" or "project_pk")
    - holder_model: the Django model owning the attachments
    - malware_callbacks: dict with safe/unknown/unsafe dotted callback paths
    """

    pagination_class = None
    permission_classes = [
        IsActivatedUser,
        permissions.IsAuthenticated,
    ]
    serializer_class = serializers.ChatConversationAttachmentSerializer
    create_serializer_class = serializers.CreateChatConversationAttachmentSerializer
    queryset = models.ChatConversationAttachment.objects

    # -- subclass configuration --
    holder_field: str
    holder_id_field: str  # "conversation_id" or "project_id"
    holder_pk_kwarg: str
    holder_model: type
    malware_callbacks: dict  # {"safe": "...", "unknown": "...", "unsafe": "..."}

    @property
    def _holder_pk(self):
        return self.kwargs[self.holder_pk_kwarg]

    def _check_holder_ownership(self):
        """Assert the current user owns the holder, or raise 404."""
        if not self.holder_model.objects.filter(
            pk=self._holder_pk,
            owner=self.request.user,
        ).exists():
            raise Http404

    def _malware_kwargs(self):
        """Extra kwargs forwarded to malware_detection.analyse_file callbacks."""
        return {self.holder_id_field: self._holder_pk}

    def get_queryset(self):
        """Return attachments scoped to the holder and owned by the current user."""
        return (
            self.queryset.filter(
                **{
                    self.holder_id_field: self._holder_pk,
                    f"{self.holder_field}__owner": self.request.user,
                }
            )
            if self.request.user.is_authenticated
            else self.queryset.none()
        )

    def get_serializer_context(self):
        """Pass the holder pk to the serializer context."""
        context = super().get_serializer_context()
        context[self.holder_pk_kwarg] = self._holder_pk
        return context

    def perform_create(self, serializer):
        """Create a PENDING attachment record for the holder."""
        self._check_holder_ownership()

        file_name = serializer.validated_data["file_name"]
        extension = file_name.rpartition(".")[-1] if "." in file_name else None

        file_id = uuid4()
        ext_suffix = f".{extension}" if extension else ""
        key = f"{self._holder_pk!s}/{AttachmentMixin.ATTACHMENTS_FOLDER:s}/{file_id!s}{ext_suffix}"

        serializer.save(
            **{self.holder_id_field: self._holder_pk},
            uploaded_by=self.request.user,
            upload_state=enums.AttachmentStatus.PENDING,
            key=key,
        )

    @decorators.action(detail=True, methods=["post"], url_path="upload-ended")
    def upload_ended(self, request, *args, **kwargs):
        """Start malware analysis after a successful upload."""
        attachment = self.get_object()

        if attachment.upload_state != AttachmentStatus.PENDING:
            raise ValidationError(
                {"attachment": "This action is only available for items in PENDING state."},
                code="upload-state-not-pending",
            )

        mime_detector = magic.Magic(mime=True)
        with default_storage.open(attachment.key, "rb") as file:
            mimetype = mime_detector.from_buffer(file.read(2048))
            size = file.size

        attachment.upload_state = AttachmentStatus.ANALYZING
        attachment.content_type = mimetype
        attachment.size = size
        attachment.save(update_fields=["upload_state", "content_type", "size"])

        malware_detection.analyse_file(
            attachment.key,
            safe_callback=self.malware_callbacks["safe"],
            unknown_callback=self.malware_callbacks["unknown"],
            unsafe_callback=self.malware_callbacks["unsafe"],
            **self._malware_kwargs(),
        )

        serializer = self.get_serializer(attachment)

        if settings.POSTHOG_KEY:
            posthog.capture(
                "item_uploaded",
                distinct_id=str(request.user.pk),  # same as set by the frontend
                properties={
                    "id": attachment.pk,
                    "file_name": attachment.file_name,
                    "size": attachment.size,
                    "mimetype": attachment.content_type,
                },
            )

        return Response(serializer.data, status=status.HTTP_200_OK)

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="backend-upload",
        url_name="backend-upload",
    )
    def backend_upload_attachment(self, request, *args, **kwargs):
        """Handle backend file upload for backend_to_s3 mode."""
        # pylint: disable=too-many-locals
        self._check_holder_ownership()

        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data["file"]
        file_name = serializer.validated_data["file_name"]

        file_id = uuid4()
        extension = file_name.rpartition(".")[-1] if "." in file_name else None
        ext_suffix = f".{extension}" if extension else ""
        key = f"{self._holder_pk!s}/{AttachmentMixin.ATTACHMENTS_FOLDER}/{file_id!s}{ext_suffix}"

        try:
            stored_path = default_storage.save(key, file_obj)
            logger.info("File uploaded to S3: %s", stored_path)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Failed to upload file to S3 for %s %s", self.holder_field, self._holder_pk
            )
            return Response(
                {"detail": "Failed to upload file to storage"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        mime_detector = magic.Magic(mime=True)
        with default_storage.open(key, "rb") as file:
            mimetype = mime_detector.from_buffer(file.read(2048))
            file_size = file.size

        attachment = models.ChatConversationAttachment.objects.create(
            **{self.holder_id_field: self._holder_pk},
            uploaded_by=request.user,
            upload_state=AttachmentStatus.ANALYZING,
            key=key,
            file_name=file_name,
            content_type=mimetype,
            size=file_size,
        )

        logger.info(
            "Created attachment %s for %s %s, starting malware detection",
            attachment.pk,
            self.holder_field,
            self._holder_pk,
        )

        malware_detection.analyse_file(
            key,
            safe_callback=self.malware_callbacks["safe"],
            unknown_callback=self.malware_callbacks["unknown"],
            unsafe_callback=self.malware_callbacks["unsafe"],
            **self._malware_kwargs(),
        )

        if settings.POSTHOG_KEY:
            posthog.capture(
                "item_uploaded_backend",
                distinct_id=str(request.user.pk),
                properties={
                    "id": attachment.pk,
                    "file_name": attachment.file_name,
                    "size": attachment.size,
                    "mimetype": attachment.content_type,
                    "mode": settings.FILE_UPLOAD_MODE,
                },
            )

        serializer = self.get_serializer(attachment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatConversationAttachmentViewSet(BaseAttachmentViewSet):
    """Attachment viewset scoped to a conversation."""

    holder_field = "conversation"
    holder_id_field = "conversation_id"
    holder_pk_kwarg = "conversation_pk"
    holder_model = models.ChatConversation
    malware_callbacks = {
        "safe": "chat.malware_detection.conversation_safe_attachment_callback",
        "unknown": "chat.malware_detection.unknown_attachment_callback",
        "unsafe": "chat.malware_detection.conversation_unsafe_attachment_callback",
    }


class ChatProjectAttachmentViewSet(  # pylint: disable=too-many-ancestors
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    BaseAttachmentViewSet,
):
    """Attachment viewset scoped to a project."""

    holder_field = "project"
    holder_id_field = "project_id"
    holder_pk_kwarg = "project_pk"
    holder_model = models.ChatProject
    malware_callbacks = {
        "safe": "chat.malware_detection.project_safe_attachment_callback",
        "unknown": "chat.malware_detection.project_unknown_attachment_callback",
        "unsafe": "chat.malware_detection.project_unsafe_attachment_callback",
    }

    def get_queryset(self):
        """Exclude markdown conversion attachments from listing."""
        return (
            super().get_queryset().filter(Q(conversion_from__isnull=True) | Q(conversion_from=""))
        )

    def _enforce_caps(self, content_type: str | None) -> None:
        """Reject the upload if the project is at the per-type cap.

        Counts ignore hidden markdown companion rows (`conversion_from` set) -
        those are bookkeeping artifacts, not user-uploaded files. The cap a
        request hits is selected by the *claimed* MIME type: lying to bypass
        the image cap would land a non-image stored as `image/*`, which then
        fails the malware scan or LLM-side handling. The cap is anti-overgrowth,
        not security.
        """
        is_image = bool(content_type and content_type.startswith(IMAGE_MIME_PREFIX))
        base_qs = models.ChatConversationAttachment.objects.filter(
            project_id=self._holder_pk
        ).filter(Q(conversion_from__isnull=True) | Q(conversion_from=""))

        if is_image:
            cap = settings.PROJECT_IMAGES_MAX_COUNT
            count = base_qs.filter(content_type__startswith=IMAGE_MIME_PREFIX).count()
            if count >= cap:
                raise ValidationError(
                    {
                        "content_type": [
                            _(
                                "This project already has the maximum of %(cap)d images. "
                                "Remove one before uploading another."
                            )
                            % {"cap": cap}
                        ]
                    }
                )
            return

        cap = settings.PROJECT_FILES_MAX_COUNT
        count = base_qs.exclude(content_type__startswith=IMAGE_MIME_PREFIX).count()
        if count >= cap:
            raise ValidationError(
                {
                    "content_type": [
                        _(
                            "This project already has the maximum of %(cap)d files. "
                            "Remove one before uploading another."
                        )
                        % {"cap": cap}
                    ]
                }
            )

    def perform_create(self, serializer):
        """Override to enforce per-project file/image caps before record creation."""
        self._enforce_caps(serializer.validated_data.get("content_type"))
        super().perform_create(serializer)

    @decorators.action(
        detail=False,
        methods=["post"],
        url_path="backend-upload",
        url_name="backend-upload",
    )
    def backend_upload_attachment(self, request, *args, **kwargs):
        """Enforce caps before the (potentially expensive) S3 upload."""
        self._check_holder_ownership()
        # Peek at the multipart file's claimed type before the base view runs S3.
        file_obj = request.data.get("file")
        claimed_type = getattr(file_obj, "content_type", None) if file_obj else None
        self._enforce_caps(claimed_type)
        return super().backend_upload_attachment(request, *args, **kwargs)

    def perform_destroy(self, instance):
        """Delete the attachment, its companion markdown row, S3 blob, and RAG document.

        Order: RAG document → S3 (original + companion blobs) → companion DB
        row → original DB row. Each step is best-effort: failures are logged
        but never block the user-facing delete, so a brief Albert / S3 hiccup
        can never strand a DB row the user cannot remove. Trade-off accepted:
        orphaned RAG / S3 storage on partial failure.

        Companion handling: non-text uploads carry a hidden `text/markdown`
        attachment row produced at index time (`conversion_from = original.key`,
        distinct S3 key suffixed with `.md`). Both blobs are deleted via
        `_bulk_delete_s3_blobs` (set semantics deduplicate any historical rows
        that still share a key with the original); the companion DB row is
        then dropped explicitly so it doesn't outlive the original. Text-only
        uploads have no companion - the bulk filter below is a no-op for them.
        """
        if instance.rag_document_id and instance.project and instance.project.collection_id:
            try:
                backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                backend = backend_class(collection_id=instance.project.collection_id)
                backend.delete_document(instance.rag_document_id)
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to delete RAG document %s from collection %s",
                    instance.rag_document_id,
                    instance.project.collection_id,
                )

        # Companion blobs live at their own S3 keys (since the indexing-time
        # distinct-key change), so collect them up-front and bulk-delete with
        # the original. Set semantics dedup any historical rows that still
        # reuse the original's key.
        companion_qs = models.ChatConversationAttachment.objects.filter(
            project_id=instance.project_id,
            conversion_from=instance.key,
        )
        keys_to_delete = {instance.key} | set(companion_qs.values_list("key", flat=True))
        _bulk_delete_s3_blobs(keys_to_delete)

        try:
            companion_qs.delete()
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Failed to delete markdown companion for attachment %s (key=%s)",
                instance.pk,
                instance.key,
            )
        instance.delete()
