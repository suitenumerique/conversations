"""Chat API implementation."""

import logging
import os
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.http import Http404, StreamingHttpResponse
from django.utils.decorators import method_decorator

import langfuse
import magic
import posthog
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


class ChatConversationFilter(filters.BaseFilterBackend):
    """Filter conversation."""

    def filter_queryset(self, request, queryset, view):
        """Filter conversation by title."""
        if title := request.GET.get("title"):
            queryset = queryset.filter(title__unaccent__icontains=remove_accents(title))
        return queryset


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

        Raises PermissionDenied if the user does not have permission.
        """
        if not user.is_authenticated:
            raise PermissionDenied()

        try:
            models.ChatConversation.objects.get(
                pk=url_params["pk"],
                owner=user,
            )
            # We don't need to check the ChatConversationAttachment here because
            # if the storage object exists, it means the attachment is linked
            # to the conversation, which is already verified by the above query.
        except models.ChatConversation.DoesNotExist as exc:
            raise PermissionDenied() from exc


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
    filter_backends = [filters.OrderingFilter, ChatConversationFilter]
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "updated_at"]
    queryset = models.ChatConversation.objects  # defined to be used in AttachmentMixin

    def get_queryset(self):
        """Return the queryset for the chat conversations."""
        return (
            self.queryset.filter(owner=self.request.user)
            if self.request.user.is_authenticated
            else self.queryset.none()
        )

    def get_permissions(self):
        """Return the permissions for the viewset."""
        if self.action in ["media_auth", "media_check"]:
            # Permission is checked in AttachmentMixin
            self.permission_classes = []
        return super().get_permissions()

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


class ChatConversationAttachmentViewSet(
    SerializerPerActionMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing chat conversation attachments.

    Provides endpoints to create and retrieve chat conversation attachments.
    """

    pagination_class = None  # No pagination for attachments
    permission_classes = [
        IsActivatedUser,  # see activation_codes application
        permissions.IsAuthenticated,
    ]
    serializer_class = serializers.ChatConversationAttachmentSerializer
    create_serializer_class = serializers.CreateChatConversationAttachmentSerializer
    queryset = models.ChatConversationAttachment.objects

    def get_queryset(self):
        """Return the queryset for the chat conversation attachments."""
        return (
            self.queryset.filter(
                conversation_id=self.kwargs["conversation_pk"],
                conversation__owner=self.request.user,
            )
            if self.request.user.is_authenticated
            else self.queryset.none()
        )

    def get_serializer_context(self):
        """Return the context for the serializer."""
        context = super().get_serializer_context()
        context["conversation_pk"] = self.kwargs["conversation_pk"]
        return context

    def perform_create(self, serializer):
        """Set the uploaded_by field to the current user."""
        # assert the user is the owner of the conversation
        if not models.ChatConversation.objects.filter(
            pk=self.kwargs["conversation_pk"],
            owner=self.request.user,
        ).exists():
            raise Http404
        file_name = serializer.validated_data["file_name"]
        extension = file_name.rpartition(".")[-1] if "." in file_name else None

        file_id = uuid4()
        holder_key_base = f"{self.kwargs['conversation_pk']!s}"
        ext_suffix = f".{extension}" if extension else ""
        key = f"{holder_key_base}/{AttachmentMixin.ATTACHMENTS_FOLDER:s}/{file_id!s}{ext_suffix}"

        serializer.save(
            conversation_id=self.kwargs["conversation_pk"],
            uploaded_by=self.request.user,
            upload_state=enums.AttachmentStatus.PENDING,
            key=key,
        )

    @decorators.action(detail=True, methods=["post"], url_path="upload-ended")
    def upload_ended(self, request, *args, **kwargs):
        """
        Start the analysis of an item after a successful upload.
        """

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
            safe_callback="chat.malware_detection.conversation_safe_attachment_callback",
            unknown_callback="chat.malware_detection.unknown_attachment_callback",
            unsafe_callback="chat.malware_detection.conversation_unsafe_attachment_callback",
            conversation_id=self.kwargs["conversation_pk"],
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
        """
        Handle backend file upload for backend_to_s3 mode.

        This endpoint is used when FILE_UPLOAD_MODE is set to backend_to_s3.
        The frontend sends the file directly to this endpoint,
        and the backend stores it on S3 and initiates malware detection.

        The attachment lifecycle:
        1. Frontend sends file via this endpoint
        2. Backend stores file on S3
        3. Backend detects MIME type and file size
        4. Backend initiates malware detection
        5. After detection, attachment status becomes READY or SUSPICIOUS
        """
        # pylint: disable=too-many-locals
        # Verify the user owns the conversation
        conversation_id = self.kwargs["conversation_pk"]
        if not models.ChatConversation.objects.filter(
            pk=conversation_id,
            owner=request.user,
        ).exists():
            raise Http404

        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data["file"]
        file_name = serializer.validated_data["file_name"]

        # Generate unique file ID and storage key
        file_id = uuid4()
        extension = file_name.rpartition(".")[-1] if "." in file_name else None
        ext_suffix = f".{extension}" if extension else ""
        key = f"{conversation_id}/{AttachmentMixin.ATTACHMENTS_FOLDER}/{file_id}{ext_suffix}"

        # Store file on S3
        try:
            stored_path = default_storage.save(key, file_obj)
            logger.info("File uploaded to S3: %s", stored_path)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to upload file to S3 for conversation %s", conversation_id)
            return Response(
                {"detail": "Failed to upload file to storage"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Detect MIME type
        mime_detector = magic.Magic(mime=True)
        with default_storage.open(key, "rb") as file:
            mimetype = mime_detector.from_buffer(file.read(2048))
            file_size = file.size

        # Create attachment record with ANALYZING status
        attachment = models.ChatConversationAttachment.objects.create(
            conversation_id=conversation_id,
            uploaded_by=request.user,
            upload_state=AttachmentStatus.ANALYZING,
            key=key,
            file_name=file_name,
            content_type=mimetype,
            size=file_size,
        )

        logger.info(
            "Created attachment %s for conversation %s, starting malware detection",
            attachment.pk,
            conversation_id,
        )

        # Start malware detection (will update status to READY or SUSPICIOUS via callbacks)
        malware_detection.analyse_file(
            key,
            safe_callback="chat.malware_detection.conversation_safe_attachment_callback",
            unknown_callback="chat.malware_detection.unknown_attachment_callback",
            unsafe_callback="chat.malware_detection.conversation_unsafe_attachment_callback",
            conversation_id=conversation_id,
        )

        # Track upload event
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
