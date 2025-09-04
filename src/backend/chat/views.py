"""Chat API implementation."""

import logging

from django.conf import settings
from django.http import StreamingHttpResponse

from rest_framework import decorators, filters, mixins, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.viewsets import Pagination, SerializerPerActionMixin
from core.filters import remove_accents

from chat import models, serializers
from chat.clients.pydantic_ai import AIAgentService
from chat.serializers import ChatConversationRequestSerializer

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
        query_params_serializer = ChatConversationRequestSerializer(data=request.query_params)
        query_params_serializer.is_valid(raise_exception=True)
        protocol = query_params_serializer.validated_data["protocol"]
        force_web_search = query_params_serializer.validated_data["force_web_search"]
        model_hrid = query_params_serializer.validated_data["model_hrid"]

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
        serializer.is_valid(raise_exception=True)
        messages = serializer.validated_data["messages"]

        logger.info("Received messages: %s", messages)
        logger.info("Using protocol: %s", protocol)

        if not messages:
            return Response({"error": "No messages provided"}, status=status.HTTP_400_BAD_REQUEST)

        ai_service = AIAgentService(
            conversation=conversation,
            user=self.request.user,
            model_hrid=model_hrid,
            language=(
                self.request.user.language
                or self.request.LANGUAGE_CODE  # from the LocaleMiddleware
            ),
        )
        if protocol == "data":
            streaming_content = ai_service.stream_data(messages, force_web_search=force_web_search)
        else:  # Default to 'text' protocol
            streaming_content = ai_service.stream_text(messages, force_web_search=force_web_search)

        response = StreamingHttpResponse(
            streaming_content,
            content_type="text/event-stream",
            headers={
                "x-vercel-ai-data-stream": "v1",  # This header is used for Vercel AI streaming,
            },
        )
        return response

    @decorators.action(
        methods=["post"],
        detail=True,
        url_path="stop-streaming",
        url_name="stop-streaming",
    )
    def post_stop_steaming(self, request, pk):  # pylint: disable=unused-argument
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
