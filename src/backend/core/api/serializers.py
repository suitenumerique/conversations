"""Client serializers for the conversations core app."""

from rest_framework import serializers

from core import models

from chat.connectors.turn import offered_connectors


class UserSerializer(serializers.ModelSerializer):
    """Serialize users."""

    allowed_connectors = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        help_text="Slugs of the MCP connectors the user switched on.",
    )

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

    def validate_allowed_connectors(self, slugs):
        """Accept the connectors offered to this user, and those they already had.

        Offered means declared and in the user's cohort. A slug the user already
        had is kept even when it is no longer offered, so a connector taken
        offline for a while keeps its users' consent. Duplicates are dropped and
        the order kept.
        """
        offered = {definition.slug for definition in offered_connectors(self.instance)}
        already = set(self.instance.allowed_connectors or []) if self.instance else set()
        if refused := sorted({slug for slug in slugs if slug not in offered | already}):
            raise serializers.ValidationError(
                f"These connectors are not offered to this user: {', '.join(refused)}."
            )
        return list(dict.fromkeys(slugs))
