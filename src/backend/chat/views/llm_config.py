"""LLM configuration view."""

from django.conf import settings

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.feature_flags.helpers import is_feature_enabled

from chat import models, serializers
from chat.enums import RoutingTier
from chat.serializers import TIER_AUTO

# Ordinal energy pictogram of each tier: the more leaves, the more energy per answer.
TIER_LEAVES = {RoutingTier.SIMPLE: 1, RoutingTier.STANDARD: 2, RoutingTier.COMPLEX: 3}


def tier_entries(tier_settings: models.RoutingTierSettings) -> list[dict]:
    """Selector entries: Auto always, then every tier whose model is configured and active."""
    entries = [{"slug": TIER_AUTO, "label_key": f"router.tier.{TIER_AUTO}", "recommended": True}]
    for tier in RoutingTier:
        configuration = settings.LLM_CONFIGURATIONS.get(tier_settings.model_for(tier))
        if configuration is None or not configuration.is_active:
            continue
        entries.append(
            {
                "slug": tier.value,
                "label_key": f"router.tier.{tier.value}",
                "leaves": TIER_LEAVES[tier],
            }
        )
    return entries


class LLMConfigurationView(APIView):
    """View for listing available LLM models, and the router tiers."""

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    @extend_schema(responses=serializers.LLMConfigurationSerializer)
    def get(self, request):
        """Handle GET requests to list available LLM models.

        For now the results are not filtered by user, but in the future we will want to
        filter the models based on user. When the ``router`` feature flag is on, utility
        models (summarization...) are not offered as a conversation model and the tier
        selector entries are added; they never carry a model name.

        Returns:
            Response: A response containing the list of available LLM models.
        """
        payload = {"models": settings.LLM_CONFIGURATIONS.values()}
        if is_feature_enabled(request.user, "router"):
            payload["models"] = [model for model in payload["models"] if model.role == "chat"]
            payload["tiers"] = tier_entries(models.RoutingTierSettings.get_solo())
        serializer = serializers.LLMConfigurationSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)
