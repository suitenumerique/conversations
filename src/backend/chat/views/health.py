"""Model and assistant health views."""

from django.core.cache import cache

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from chat import models, serializers
from chat.assistant_health import compute_assistant_health_banners


class ModelHealthView(APIView):
    """Return the latest known health status for each model."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return latest status per (provider, model_id), Redis status wins over DB."""
        # Latest DB row per (provider, model_id) via DISTINCT ON (PostgreSQL).
        latest_entries = list(
            models.ModelHealth.objects.order_by("provider", "model_id", "-updated_at").distinct(
                "provider", "model_id"
            )
        )

        if not latest_entries:
            serializer = serializers.ModelHealthResponseSerializer({"data": []})
            return Response(serializer.data, status=status.HTTP_200_OK)

        keys = [f"model_health:{e.provider}:{e.model_id}" for e in latest_entries]
        cached = cache.get_many(keys)

        items = []
        for entry in latest_entries:
            key = f"model_health:{entry.provider}:{entry.model_id}"
            items.append(
                {
                    "provider": entry.provider,
                    "model_id": entry.model_id,
                    "status": cached.get(key, entry.status),
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                }
            )

        serializer = serializers.ModelHealthResponseSerializer({"data": items})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AssistantHealthView(APIView):
    """Return banners and blocked status based on live model health."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Compute and return assistant health banners."""
        data = compute_assistant_health_banners()
        serializer = serializers.AssistantHealthSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
