"""Chat conversation viewset and related endpoints."""

import logging
import os
from datetime import timedelta

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.module_loading import import_string

import langfuse
from drf_spectacular.utils import extend_schema
from rest_framework import decorators, filters, mixins, permissions, status, viewsets
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.viewsets import Pagination, SerializerPerActionMixin
from core.file_upload.enums import AttachmentStatus
from core.file_upload.mixins import AttachmentMixin

from activation_codes.permissions import IsActivatedUser
from chat import models, serializers
from chat.clients.pydantic_ai import AIAgentService
from chat.constants import IMAGE_MIME_PREFIX, SSE_MIME_TYPE
from chat.keepalive import stream_with_keepalive_async, stream_with_keepalive_sync
from chat.model_routing import resolve_effective_model_hrid
from chat.rate_limiting import ChatCooldownThrottle, get_cooldown_remaining
from chat.serializers import ChatConversationRequestSerializer
from chat.views.edit_in_docs import EditInDocsMixin
from chat.views.filters import ProjectFilter, TitleSearchFilter
from chat.views.helpers import _bulk_delete_s3_blobs, conditional_refresh_oidc_token

logger = logging.getLogger(__name__)


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

        # We don't need to check the ChatConversationAttachment here because
        # if the storage object exists, it means the attachment is linked to
        # the holder (conversation or project), which is verified by the
        # ownership queries below.

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
    EditInDocsMixin,
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
        # A single retrieval nests project (id, title, icon) so the client can
        # read the conversation's project without a second request.
        if self.action == "retrieve":
            return serializers.ChatConversationRetrieveSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """Return the queryset for the chat conversations."""
        if not self.request.user.is_authenticated:
            return self.queryset.none()

        qs = self.queryset.filter(owner=self.request.user)

        # Search results and retrieve use nested project info; post_conversation
        # needs project.llm_instructions — prefetch to avoid extra queries
        if self.request.query_params.get("title") or self.action in (
            "post_conversation",
            "retrieve",
        ):
            qs = qs.select_related("project")

        # Avoid an N+1 on the images_skipped serializer field: pre-compute
        # the existence check in a single EXISTS subquery for list/retrieve.
        if self.action in ("list", "retrieve") and not self.request.query_params.get("title"):
            qs = qs.annotate(
                _has_project_image=Exists(
                    models.ChatConversationAttachment.objects.filter(
                        project_id=OuterRef("project_id"),
                        content_type__startswith=IMAGE_MIME_PREFIX,
                        upload_state=AttachmentStatus.READY,
                    )
                )
            )
        return qs

    def get_permissions(self):
        """Return the permissions for the viewset."""
        if self.action in ["media_auth", "media_check"]:
            # Permission is checked in AttachmentMixin
            self.permission_classes = []
        return super().get_permissions()

    def get_throttles(self):
        """Enforce the model-load cooldown on the chat completion endpoint."""
        if self.action == "post_conversation":
            return [ChatCooldownThrottle()]
        return super().get_throttles()

    def perform_destroy(self, instance):
        """Delete a conversation, its RAG collection, and S3-stored attachments.

        Order: RAG collection drop -> S3 blob cleanup -> DB cascade. Each step
        is best-effort: failures are logged but never block the user-facing
        delete. The collection drop covers all per-doc Albert state in one
        call, so we do not iterate `delete_document` on each attachment here.
        S3 cleanup is needed because Django CASCADE drops attachment rows
        without touching object storage. Markdown companions share their key
        with the original, so unique keys are deduplicated upfront.
        """
        if instance.collection_id:
            try:
                backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
                backend_class(collection_id=instance.collection_id).delete_collection(
                    session=self.request.session,
                )
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "Failed to delete RAG collection %s for conversation %s",
                    instance.collection_id,
                    instance.pk,
                )

        attachment_keys = set(instance.attachments.values_list("key", flat=True))
        _bulk_delete_s3_blobs(attachment_keys)

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
        requested_model_hrid = query_params_serializer.validated_data["model_hrid"]

        raw_messages = request.data.get("messages")
        logger.info(
            "Received %d messages",
            len(raw_messages) if isinstance(raw_messages, list) else 0,
        )

        conversation = self.get_object()

        # Refuse the message while a project file is still being malware-scanned:
        # its content must not reach the model before the scan clears it. Only
        # this in-flight state blocks; terminal states (READY, SUSPICIOUS,
        # too-large, FAILED) and a not-yet-uploaded PENDING row do not, so a
        # rejected or abandoned file can't deadlock the project.
        #
        # An ANALYZING row is only counted while fresh. The scan runs off-process
        # if it exhausts its retries or the worker dies,
        # the callback never fires and the row stays
        # ANALYZING forever, permanently blocking every message in the project.
        # Past the window such a row is provably dead, so we stop blocking on it.
        # This is safe: the row never reaches READY, and only READY uploads are
        # fed to the model, so an unscanned file still can't reach it. Marking
        # the dead row terminal is separate periodic-recovery work.
        #
        # Indexing deliberately does NOT block: since indexing runs as a Celery
        # task it can take a while, and a user may well have a quick question
        # unrelated to the documents. A still-indexing file is simply not
        # searchable yet, and the frontend banner says so.
        if (
            conversation.project_id
            and models.ChatConversationAttachment.objects.filter(
                project_id=conversation.project_id,
                upload_state=AttachmentStatus.ANALYZING,
                updated_at__gte=timezone.now()
                - timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT + 60),
            ).exists()
        ):
            return Response(
                {"error": "project_files_indexing"},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            # Log validation error, because it should not happen
            # If there is a problem, we need to fix the frontend or backend...
            logger.exception("Frontend input error: %s", exc)
            raise  # Let DRF handle the exception and return a 400 response

        messages = serializer.validated_data["messages"]

        logger.info("Validated %d messages, protocol=%s", len(messages), protocol)

        if not messages:
            return Response({"error": "No messages provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Warning: the messages should be stored more securely in production
        conversation.ui_messages = request.data.get("messages", [])
        # `updated_at` is auto_now; Django skips auto_now fields when
        # update_fields is set, so list it explicitly to preserve the bump.
        update_fields = ["ui_messages", "updated_at"]

        # Pin the model the first time the conversation is exercised. Existing
        # conversations keep their pinned model so a recovered main model never
        # moves a chat already in progress. A conditional UPDATE with
        # model_hrid="" is the compare-and-set: only the first concurrent
        # request can pin, late peers re-read the winner.
        if not conversation.model_hrid:
            resolved = resolve_effective_model_hrid(requested_model_hrid)
            pinned = models.ChatConversation.objects.filter(
                pk=conversation.pk, model_hrid=""
            ).update(model_hrid=resolved)
            if pinned:
                conversation.model_hrid = resolved
            else:
                conversation.refresh_from_db(fields=["model_hrid"])

        conversation.save(update_fields=update_fields)

        ai_service = AIAgentService(
            conversation=conversation,
            user=self.request.user,
            session=request.session,
            model_hrid=conversation.model_hrid,
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
            content_type=SSE_MIME_TYPE,
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


class ChatCooldownView(APIView):
    """Return the remaining inference-load cooldown for the current user.

    Lets the frontend restore the cooldown state after a refresh, in a new tab,
    or when switching conversations, sourced from the authoritative cache value.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return the seconds the user must still wait before sending again."""
        return Response({"cooldown_seconds": get_cooldown_remaining(request.user.pk)})
