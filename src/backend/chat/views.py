"""Chat API implementation."""

import logging
import os
from uuid import UUID, uuid4

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db.models import Prefetch, Q
from django.http import Http404, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string

import langfuse
import magic
import posthog
from botocore.exceptions import BotoCoreError, ClientError
from drf_spectacular.utils import extend_schema
from lasuite.malware_detection import malware_detection
from lasuite.oidc_login.decorators import refresh_oidc_access_token
from rest_framework import decorators, filters, mixins, permissions, status, viewsets
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.api.viewsets import Pagination, SerializerPerActionMixin
from core.file_upload import enums
from core.file_upload.enums import AttachmentStatus
from core.file_upload.mixins import AttachmentMixin
from core.file_upload.serializers import FileUploadSerializer
from core.filters import remove_accents

from activation_codes.permissions import IsActivatedUser
from chat import models, serializers
from chat.clients.pydantic_ai import AIAgentService
from chat.keepalive import stream_with_keepalive_async, stream_with_keepalive_sync
from chat.serializers import ChatConversationRequestSerializer

logger = logging.getLogger(__name__)


def conditional_refresh_oidc_token(func):
    """
    Conditionally apply refresh_oidc_access_token decorator.

    The decorator is only applied if OIDC_STORE_REFRESH_TOKEN is True, meaning
    we can actually refresh something. Broader settings checks are done in settings.py.
    """
    if settings.OIDC_STORE_REFRESH_TOKEN:
        return method_decorator(refresh_oidc_access_token)(func)

    return func


class TitleSearchFilter(filters.BaseFilterBackend):
    """Filter conversation by title (accent-insensitive)."""

    def filter_queryset(self, request, queryset, view):
        """Filter conversation by title."""
        if title := request.GET.get("title"):
            queryset = queryset.filter(title__unaccent__icontains=remove_accents(title))
        return queryset

    def get_schema_operation_parameters(self, view):
        """Return the schema for the ``title`` query parameter (drf-spectacular)."""
        return [
            {
                "name": "title",
                "required": False,
                "in": "query",
                "description": "Search conversations by title (accent-insensitive). "
                "When provided, the response uses a search-specific serializer "
                "with nested project info.",
                "schema": {"type": "string"},
            },
        ]


class ProjectFilter(filters.BaseFilterBackend):
    """Filter conversations by project.

    Accepts a `project` query parameter:
    - a UUID: conversations belonging to that specific project
    - "none": conversations not linked to any project
    - "any": conversations linked to any project
    """

    def filter_queryset(self, request, queryset, view):
        """Filter conversations by project."""
        project_id = request.GET.get("project")
        if project_id is None:
            return queryset
        if project_id == "none":
            return queryset.filter(project__isnull=True)
        if project_id == "any":
            return queryset.filter(project__isnull=False)
        try:
            UUID(project_id)
        except ValueError:
            return queryset.none()
        return queryset.filter(project_id=project_id)

    def get_schema_operation_parameters(self, view):
        """Return the schema for the ``project`` query parameter (drf-spectacular)."""
        return [
            {
                "name": "project",
                "required": False,
                "in": "query",
                "description": "Filter by project. Pass a UUID for a specific project, "
                '"none" for standalone conversations, or "any" for all project conversations.',
                "schema": {"type": "string"},
            },
        ]


class ChatAttachmentMixin(AttachmentMixin):  # pylint: disable=abstract-method
    """Mixin to handle attachment authorization for chat conversations."""

    @decorators.action(detail=True, methods=["post"], url_path="attachment-upload")
    def attachment_upload(self, request, *args, **kwargs):
        """Explicitly disable this action."""
        raise MethodNotAllowed("POST")

    @decorators.action(detail=True, methods=["get"], url_path="media-check")
    def media_check(self, request, *args, **kwargs):
        """Explicitly disable this action."""
        raise MethodNotAllowed("GET")

    def check_attachment_holder_permission(self, user, url_params, key):
        """
        Check if the user has permission to access the holder of the attachment.

        The holder pk in the media URL can be either a conversation or a project.
        Raises PermissionDenied if the user does not have permission.
        """
        if not user.is_authenticated:
            raise PermissionDenied()

        holder_pk = url_params["pk"]

        # Try conversation first (most common case)
        if models.ChatConversation.objects.filter(pk=holder_pk, owner=user).exists():
            return

        # Try project
        if models.ChatProject.objects.filter(pk=holder_pk, owner=user).exists():
            return

        raise PermissionDenied()


class ChatViewSet(  # pylint: disable=too-many-ancestors, abstract-method
    SerializerPerActionMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
    ChatAttachmentMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing chat conversations.

    Provides endpoints to create, retrieve, list, update, and delete chat conversations.

    The chat conversations are filtered by the authenticated user.
    The `post_conversation` action allows sending messages to the chat and receiving a
    streaming response with "data" formatted for Vercel AI SDK
    see https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol#data-stream-protocol.
    """

    pagination_class = Pagination
    permission_classes = [
        IsActivatedUser,  # see activation_codes application
        permissions.IsAuthenticated,
    ]
    serializer_class = serializers.ChatConversationSerializer
    post_conversation_serializer_class = serializers.ChatConversationInputSerializer
    filter_backends = [filters.OrderingFilter, TitleSearchFilter, ProjectFilter]
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "updated_at"]
    queryset = models.ChatConversation.objects  # defined to be used in AttachmentMixin

    @extend_schema(
        responses=serializers.ChatConversationSearchSerializer(many=True),
        description=(
            "When the `title` query parameter is provided, returns search results "
            "with nested project info (id, title, icon) and no messages. "
            "Without `title`, returns the default conversation list."
        ),
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        """Return search serializer when filtering by title on list action."""

        # Search results only include nested project info
        if self.action == "list" and self.request.query_params.get("title"):
            return serializers.ChatConversationSearchSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """Return the queryset for the chat conversations."""
        if not self.request.user.is_authenticated:
            return self.queryset.none()

        qs = self.queryset.filter(owner=self.request.user)

        # Search results use nested project info; post_conversation needs
        # project.llm_instructions — prefetch to avoid extra queries
        if self.request.query_params.get("title") or self.action == "post_conversation":
            qs = qs.select_related("project")
        return qs

    def get_permissions(self):
        """Return the permissions for the viewset."""
        if self.action in ["media_auth", "media_check"]:
            # Permission is checked in AttachmentMixin
            self.permission_classes = []
        return super().get_permissions()

    def perform_destroy(self, instance):
        """Delete a conversation and drop its RAG collection on the backend.

        Backend failures are logged but do not block the user-facing delete.
        """
        if instance.collection_id:
            try:
                backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                backend_class(collection_id=instance.collection_id).delete_collection()
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to delete RAG collection %s for conversation %s",
                    instance.collection_id,
                    instance.pk,
                )

        instance.delete()

    @conditional_refresh_oidc_token
    @decorators.action(
        methods=["post"],
        detail=True,
        url_path="conversation",
        url_name="conversation",
    )
    def post_conversation(self, request, pk):  # pylint: disable=unused-argument
        """Handle POST requests to the chat endpoint.

        Args:
            request: The HTTP request object containing:
                - messages: List of message objects with role and content
                - protocol: Optional protocol parameter ('text' or 'data', defaults to 'data')
            pk: The primary key of the chat conversation.

        Returns:
            StreamingHttpResponse: A streaming response containing the chat completion
        """
        query_params_serializer = ChatConversationRequestSerializer(data=request.query_params)
        query_params_serializer.is_valid(raise_exception=True)
        protocol = query_params_serializer.validated_data["protocol"]
        force_web_search = query_params_serializer.validated_data["force_web_search"]
        model_hrid = query_params_serializer.validated_data["model_hrid"]

        logger.info("Received messages: %s", request.data.get("messages", []))

        # Warning: the messages should be stored more securely in production
        conversation = self.get_object()
        conversation.ui_messages = request.data.get("messages", [])
        conversation.save()

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            # Log validation error, because it should not happen
            # If there is a problem, we need to fix the frontend or backend...
            logger.exception("Frontend input error: %s", exc)
            raise  # Let DRF handle the exception and return a 400 response

        messages = serializer.validated_data["messages"]

        logger.info("Received messages: %s", messages)
        logger.info("Using protocol: %s", protocol)

        if not messages:
            return Response({"error": "No messages provided"}, status=status.HTTP_400_BAD_REQUEST)

        ai_service = AIAgentService(
            conversation=conversation,
            user=self.request.user,
            session=request.session,
            model_hrid=model_hrid,
            language=(
                self.request.user.language
                or self.request.LANGUAGE_CODE  # from the LocaleMiddleware
            ),
        )

        # This environment variable allows switching between sync and async streaming modes
        # based on the server configuration. Tests run in sync mode (WSGI), while
        # production uses async mode (Uvicorn ASGI).
        is_async_mode = os.environ.get("PYTHON_SERVER_MODE", "sync") == "async"

        if is_async_mode:
            logger.debug("Using ASYNC streaming for chat conversation.")
            if protocol == "data":
                base_stream = ai_service.stream_data_async(
                    messages, force_web_search=force_web_search
                )
            else:  # Default to 'text' protocol
                base_stream = ai_service.stream_text_async(
                    messages, force_web_search=force_web_search
                )
            streaming_content = stream_with_keepalive_async(base_stream)
        else:
            logger.debug("Using SYNC streaming for chat conversation.")
            if protocol == "data":
                base_stream = ai_service.stream_data(messages, force_web_search=force_web_search)
            else:  # Default to 'text' protocol
                base_stream = ai_service.stream_text(messages, force_web_search=force_web_search)

            streaming_content = stream_with_keepalive_sync(base_stream)
        response = StreamingHttpResponse(
            streaming_content,
            content_type="text/event-stream",
            headers={
                "x-vercel-ai-data-stream": "v1",  # This header is used for Vercel AI streaming,
                "X-Accel-Buffering": "no",  # Prevent nginx buffering
            },
        )
        return response

    @decorators.action(
        methods=["post"],
        detail=True,
        url_path="stop-streaming",
        url_name="stop-streaming",
    )
    def post_stop_streaming(self, request, pk):  # pylint: disable=unused-argument
        """Handle POST requests to stop streaming the chat conversation.

        This action will put a poison pill in the redis cache to stop any ongoing streaming.
        It is used to stop the streaming when the user decides to cancel the chat.

        Note:
            We currently use uWSGI workers, which will not automatically stop the streaming
            when the request is cancelled by the client. Therefore, we need to
            explicitly stop the streaming by calling this endpoint.
            When (if) we switch to Gunicorn with Uvicorn workers, this will not be necessary
            as the Uvicorn workers will automatically stop the streaming when the request
            is cancelled. BUT, we will then need to handle the streaming cancellation when the
            user is simply offline and still waiting for a response and the conversation to
            be updated with the result. So this endpoint will still be useful to be able to
            detect the cancellation of the streaming versus the user being offline.

        Args:
            request: The HTTP request object.
            pk: The primary key of the chat conversation.

        Returns:
            Response: A response indicating that the streaming has been stopped.
        """
        conversation = self.get_object()

        AIAgentService(
            conversation=conversation,
            user=self.request.user,
            model_hrid=None,  # model_hrid is not needed to stop streaming
            language=None,  # language is not needed to stop streaming
        ).stop_streaming()

        return Response({"status": "OK"}, status=status.HTTP_200_OK)

    @decorators.action(
        methods=["post"],
        detail=True,
        url_path="score-message",
        url_name="score-message",
    )
    def post_score_message(self, request, pk):  # pylint: disable=unused-argument
        """Handle POST requests to score a message in the chat conversation.

        This sends the score to Langfuse to the trace_id, which is extracted from the message_id.
        We enforce the unique score_id to be a combination of trace_id and user_id to avoid
        multiple scores from the same user for the same message (if the user changes the score
        it will be updated in Langfuse).

        Args:
            request: The HTTP request object containing:
                - message_id: The ID of the message to score.
                - score: The score to assign to the message (e.g., 1-5).
            pk: The primary key of the chat conversation.
        Returns:
            Response: A response indicating that the message has been scored.
        """
        _conversation = self.get_object()  # only to check permissions

        serializer = serializers.ChatMessageCategoricalScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message_id = serializer.validated_data["message_id"]
        name = serializer.validated_data["name"]
        value = serializer.validated_data["value"]

        if not message_id.startswith("trace-"):
            raise ValidationError("Invalid message_id, no trace attached.")

        trace_id = message_id[len("trace-") :]
        langfuse.get_client().create_score(
            name=name,
            value=value,
            trace_id=trace_id,
            score_id=f"{trace_id}-{self.request.user.pk}",
            data_type="CATEGORICAL",
        )

        return Response({"status": "OK"}, status=status.HTTP_200_OK)


class LLMConfigurationView(APIView):
    """View for listing available LLM models."""

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    def get(self, request):
        """Handle GET requests to list available LLM models.

        For now the results are not filtered by user, but in the future we will want to
        filter the models based on user.

        Returns:
            Response: A response containing the list of available LLM models.
        """
        serializer = serializers.LLMConfigurationSerializer(
            {
                "models": settings.LLM_CONFIGURATIONS.values(),
            },
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class BaseAttachmentViewSet(
    SerializerPerActionMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Base viewset for attachment management (conversation or project scoped).

    Subclasses must define:
    - holder_field: FK field name on the attachment ("conversation" or "project")
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
        return {f"{self.holder_field}_id": self._holder_pk}

    def get_queryset(self):
        """Return attachments scoped to the holder and owned by the current user."""
        return (
            self.queryset.filter(
                **{
                    f"{self.holder_field}_id": self._holder_pk,
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
            **{f"{self.holder_field}_id": self._holder_pk},
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
            **{f"{self.holder_field}_id": self._holder_pk},
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

    def perform_destroy(self, instance):
        """Delete the attachment, its S3 object, and its RAG document.

        The RAG document is removed from the project collection so its parsed
        chunks stop appearing in search results. Backends that do not support
        per-document deletion leave rag_document_id null, in which case this
        is skipped (the chunks remain searchable until the project is deleted).
        Backend failures are logged but do not block the user-facing delete.
        """
        try:
            default_storage.delete(instance.key)
        except (BotoCoreError, ClientError, OSError):
            logger.exception("Failed to delete S3 object %s", instance.key)

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

        instance.delete()


class FileStreamView(APIView):
    """
    Stream file content for temporary access URLs.

    This view is used by LLMs to access file content when they cannot directly
    access S3. A temporary key is stored in cache and validated before serving
    the file.

    Security:
    - Temporary key expires after FILE_BACKEND_TEMPORARY_URL_EXPIRATION seconds
      (default: 180 seconds / 3 minutes)
    - No authentication required (key is single-use temporary token)
    - Key is generated using secure random tokens
    """

    permission_classes = []  # No authentication needed for temporary keys
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "file-stream"

    def get(self, request, temporary_key):
        """
        Stream file content using a temporary access key.

        Args:
            temporary_key: The temporary key generated by generate_temporary_url()

        Returns:
            StreamingHttpResponse with file content
        """
        # Retrieve the S3 key from cache using the temporary key
        cache_key = f"file_access:{temporary_key}"
        s3_key = cache.get(cache_key)

        if not s3_key:
            logger.warning("Temporary file access key not found or expired: %s", temporary_key)
            raise Http404("File access key expired or invalid")

        # Delete the key from cache to prevent reuse
        cache.delete(cache_key)

        logger.info("Serving file via temporary key: %s", s3_key)

        try:
            # Open the file from S3
            file_obj = default_storage.open(s3_key, "rb")

            # Detect MIME type for proper content-type header
            mime_detector = magic.Magic(mime=True)
            file_content = file_obj.read(2048)
            file_obj.seek(0)
            content_type = mime_detector.from_buffer(file_content)

            # Extract filename from S3 key (last part after /)
            filename = s3_key.split("/")[-1]

            # Stream the file content
            response = StreamingHttpResponse(
                file_obj,
                content_type=content_type,
            )
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response

        except Exception as exc:
            logger.exception("Failed to serve file via temporary key: %s", temporary_key)
            raise Http404("Failed to retrieve file") from exc


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

        # Prefetch conversations ordered by most recent first
        conversations_prefetch = Prefetch(
            "conversations",
            queryset=models.ChatConversation.objects.order_by("-created_at"),
        )

        return (
            self.queryset.filter(owner=self.request.user).prefetch_related(conversations_prefetch)
            if self.request.user.is_authenticated
            else self.queryset.none()
        )

    def perform_destroy(self, instance):
        """Delete a project, its conversations, and its RAG collection.

        ChatConversation.project uses on_delete=SET_NULL (to avoid accidental
        cascade), so we explicitly delete conversations here.

        The RAG collection is dropped on the backend so indexed content does not
        survive the project. Backend failures are logged but do not block the
        user-facing delete - a dangling collection is preferable to a project
        the user cannot remove.
        """
        instance.conversations.all().delete()

        if instance.collection_id:
            try:
                backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                backend_class(collection_id=instance.collection_id).delete_collection()
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to delete RAG collection %s for project %s",
                    instance.collection_id,
                    instance.pk,
                )

        instance.delete()
