"""LLM configuration view."""

from django.conf import settings

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from chat import serializers


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
