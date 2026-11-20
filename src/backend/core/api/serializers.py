"""Client serializers for the conversations core app."""

from rest_framework import serializers

from core import models

from chat.connectors.registry import connector_definitions


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    class Meta:
        model = models.User
        fields = [
            "id",
            "allow_conversation_analytics",
            "allowed_connectors",
            "allow_smart_web_search",
            "email",
            "full_name",
            "short_name",
            "language",
            "sub",
        ]
        read_only_fields = ["id", "email", "full_name", "short_name", "sub"]

    def validate_allowed_connectors(self, value):
        """A list of offered connector slugs, without duplicates.

        A slug the deployment no longer offers may stay if the user already had
        it, so a connector taken offline for a while keeps its users' consent;
        a new one must be offered.
        """
        if not isinstance(value, list) or not all(isinstance(slug, str) for slug in value):
            raise serializers.ValidationError("Expected a list of connector slugs.")
        already = set(self.instance.allowed_connectors or []) if self.instance else set()
        offered = connector_definitions()
        unknown = sorted({slug for slug in value if slug not in offered and slug not in already})
        if unknown:
            raise serializers.ValidationError(f"Unknown connectors: {', '.join(unknown)}.")
        # A connector that authenticates each user is switched on by linking
        # the account (see chat.views.connectors), never by this field alone.
        unlinked = sorted(
            slug
            for slug in set(value) - already
            if (definition := offered.get(slug)) is not None
            and definition.auth.needs_linking
            and not (
                self.instance
                and self.instance.connector_credentials.filter(connector_id=slug).exists()
            )
        )
        if unlinked:
            raise serializers.ValidationError(
                f"Link your account before switching on: {', '.join(unlinked)}."
            )
        return list(dict.fromkeys(value))
