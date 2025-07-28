"""Chat API implementation."""

import logging

from django.conf import settings
from django.http import StreamingHttpResponse

from rest_framework import decorators, filters, mixins, permissions, status, viewsets
from rest_framework.response import Response

from core.api.viewsets import Pagination, SerializerPerActionMixin
from core.filters import remove_accents

from chat import models, serializers
from chat.clients.pydantic_ai import AIAgentService

logger = logging.getLogger(__name__)


class ChatConversationFilter(filters.BaseFilterBackend):
    """Filter conversation."""

    def filter_queryset(self, request, queryset, view):
        """Filter conversation by title."""
        if title := request.GET.get("title"):
            queryset = queryset.filter(title__unaccent__icontains=remove_accents(title))
        return queryset


class ChatViewSet(  # pylint: disable=too-many-ancestors
    SerializerPerActionMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
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
        permissions.IsAuthenticated,
    ]
    serializer_class = serializers.ChatConversationSerializer
    post_conversation_serializer_class = serializers.ChatConversationInputSerializer
    filter_backends = [filters.OrderingFilter, ChatConversationFilter]
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        """Return the queryset for the chat conversations."""
        return models.ChatConversation.objects.filter(owner=self.request.user)

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
        protocol = request.query_params.get("protocol", "data")
        if protocol not in ["text", "data"]:
            return Response(
                {"error": "Invalid protocol. Must be 'text' or 'data'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info("Received messages: %s", request.data.get("messages", []))

        if settings.ML_FLOW_TRACKING_URI:
            # Set up MLflow experiment, don't import it globally to avoid issues
            # when running management commands when MLflow is not started
            import mlflow  # pylint: disable=import-outside-toplevel

            mlflow.set_tracking_uri(settings.ML_FLOW_TRACKING_URI)
            mlflow.set_experiment(settings.ML_FLOW_EXPERIMENT_NAME)

            # Enable automatic tracing for all OpenAI API calls
            mlflow.openai.autolog()

        # Warning: the messages should be stored more securely in production
        conversation = self.get_object()
        conversation.ui_messages = request.data.get("messages", [])
        conversation.save()

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        messages = serializer.validated_data["messages"]

        logger.info("Received messages: %s", messages)
        logger.info("Using protocol: %s", protocol)

        if not messages:
            return Response({"error": "No messages provided"}, status=status.HTTP_400_BAD_REQUEST)

        ai_service = AIAgentService(conversation=conversation)
        if protocol == "data":
            streaming_content = ai_service.stream_data(messages)
        else:
            streaming_content = ai_service.stream_text(messages)

        response = StreamingHttpResponse(
            streaming_content,
            content_type="text/event-stream",
            headers={
                "x-vercel-ai-data-stream": "v1",  # This header is used for Vercel AI streaming,
            },
        )
        return response
