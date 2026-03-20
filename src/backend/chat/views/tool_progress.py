"""Tool progress polling endpoint."""

from django.core.cache import cache

from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from activation_codes.permissions import IsActivatedUser
from chat import models


class ToolProgressView(APIView):
    """Return lightweight progress for any tool from Django cache."""

    permission_classes = [
        IsActivatedUser,  # see activation_codes application
        permissions.IsAuthenticated,
    ]

    def get(self, request, conversation_pk, tool_name):
        if not models.ChatConversation.objects.filter(pk=conversation_pk, owner=request.user).exists():
            raise PermissionDenied()

        progress = cache.get(f"tool-progress:{tool_name}:{conversation_pk}")
        if not progress:
            return Response(
                {"message": None},
                status=status.HTTP_200_OK,
            )

        # Support both legacy dicts and plain string values
        if isinstance(progress, dict):
            message = progress.get("message")
        else:
            message = str(progress)

        return Response({"message": message}, status=status.HTTP_200_OK)
