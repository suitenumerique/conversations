"""Serializers for chat application."""

from typing import Optional
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from django_pydantic_field.rest_framework import SchemaField  # pylint: disable=no-name-in-module
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.file_upload.enums import AttachmentStatus, FileUploadMode
from core.file_upload.mime_types import resolve_markdown_content_type
from core.file_upload.utils import generate_upload_policy

from chat import models
from chat.ai_sdk_types import UIMessage
from chat.constants import IMAGE_MIME_PREFIX
from chat.enums import ArenaSide
from chat.tools.self_documentation import anonymize_arena_documentation


class ChatConversationSerializer(serializers.ModelSerializer):
    """Serializer for chat conversations."""

    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    messages = SchemaField(schema=list[UIMessage], read_only=True)
    images_skipped = serializers.SerializerMethodField(
        help_text=(
            "True when the conversation's pinned model can't read images and the"
            " conversation has at least one image — either in the parent project"
            " or anywhere in the message history. The frontend surfaces a soft"
            " banner so the user knows uploaded images are not being used by the"
            " current model."
        ),
    )
    pending_arena_comparison = serializers.SerializerMethodField(
        help_text=(
            "Blind comparison still waiting for a vote on this conversation, if any:"
            " its id and which displayed sides have finished streaming. Never carries"
            " a model name."
        ),
    )

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversation
        fields = [
            "id",
            "title",
            "created_at",
            "updated_at",
            "messages",
            "owner",
            "project",
            "images_skipped",
            "pending_arena_comparison",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "messages",
            "images_skipped",
            "pending_arena_comparison",
        ]

    @staticmethod
    def get_pending_arena_comparison(obj) -> Optional[dict]:
        """Describe the pending arena comparison without revealing any model.

        When both answers are complete (``restorable``), they are returned so the
        client can put the split view and its vote bar back on screen: a choice the
        user never made survives a reload, a navigation or a new session, and is
        only ever closed by the user picking a side.
        """
        # Local import: keeps the arena service out of the serializer import graph.
        from chat.arena import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
            get_pending_comparison,
        )

        # List/retrieve views prefetch pending comparisons to avoid an N+1.
        prefetched = getattr(obj, "pending_arena_comparisons", None)
        if prefetched is None:
            comparison = get_pending_comparison(obj)
        else:
            comparison = prefetched[0] if prefetched else None
        if comparison is None:
            return None
        restorable = comparison.is_restorable()
        payload = {
            "id": str(comparison.pk),
            "sides_finished": {
                side: comparison.side_finished(comparison.role_for_side(side))
                for side in (ArenaSide.LEFT, ArenaSide.RIGHT)
            },
            "restorable": restorable,
            "answers": None,
        }
        if restorable:
            payload["answers"] = {
                side: anonymize_arena_documentation(
                    comparison.payload_for_side(side)["output_ui_message"]
                )
                for side in (ArenaSide.LEFT, ArenaSide.RIGHT)
            }
        return payload

    def to_representation(self, instance):
        """Hide the champion answer of a comparison that is still waiting for a vote.

        The champion answer is committed to the history as soon as it finishes so
        nothing is ever lost, but while the user still has a choice to make it must
        not show up as *the* answer: it is one of the two candidates returned in
        ``pending_arena_comparison``. The user message above it stays.
        """
        representation = super().to_representation(instance)
        pending = representation.get("pending_arena_comparison")
        messages = representation.get("messages")
        if (
            pending
            and pending["restorable"]
            and messages
            and messages[-1].get("role") == "assistant"
        ):
            representation["messages"] = messages[:-1]
        return representation

    @staticmethod
    @extend_schema_field(serializers.BooleanField)
    def get_images_skipped(obj) -> bool:
        """True iff the pinned model is text-only and any image exists in the conversation."""
        if not obj.model_hrid:
            return False
        model_config = settings.LLM_CONFIGURATIONS.get(obj.model_hrid)
        if not model_config or model_config.supports_image:
            return False
        # Project side: list/retrieve views pre-compute this via an EXISTS
        # annotation to avoid an N+1; fall back to a per-row query otherwise.
        if obj.project_id is not None:
            cached = getattr(obj, "_has_project_image", None)
            has_project_image = (
                cached
                if cached is not None
                else models.ChatConversationAttachment.objects.filter(
                    project_id=obj.project_id,
                    content_type__startswith=IMAGE_MIME_PREFIX,
                    upload_state=AttachmentStatus.READY,
                ).exists()
            )
            if has_project_image:
                return True
        # History side: short-circuit on the first image found in the messages.
        # Local import: the client module pulls heavy LLM deps we don't want at
        # serializer import time.
        from chat.clients.pydantic_ai import (  # noqa: PLC0415 # pylint: disable=import-outside-toplevel
            iter_image_attachments,
        )

        return any(True for _ in iter_image_attachments(obj.messages))

    def validate_project(self, project):
        """Ensure the project belongs to the current user."""
        if project and project.owner != self.context["request"].user:
            raise serializers.ValidationError("The project must belong to the current user.")
        return project

    def update(self, instance, validated_data):
        # Project is immutable after creation — no moving or detaching
        if "project" in validated_data:
            raise serializers.ValidationError(
                {"project": "This field can only be set at creation time."}
            )
        # If title is being changed, mark it as user-set
        if "title" in validated_data and validated_data["title"] != instance.title:
            instance.title_set_by_user_at = timezone.now()
        return super().update(instance, validated_data)


class ChatConversationInputSerializer(serializers.Serializer):
    """
    Used to serialize input from Vercel AI SDK when using conversation endpoint.

    See ChatViewSet().post_conversation(...) method for more details.
    """

    messages = SchemaField(schema=list[UIMessage])

    def update(self, instance, validated_data):
        """Update method is not applicable in this context."""
        raise NotImplementedError("`update()` should not be used in this context.")

    def create(self, validated_data):
        """Create method is not applicable in this context."""
        raise NotImplementedError("`create()` should not be used in this context.")

    def validate_messages(self, messages):
        """Validate that messages is not empty."""
        if not messages:
            raise serializers.ValidationError("This list must not be empty.")
        return messages


class ChatConversationRequestSerializer(serializers.Serializer):
    """
    Used to serialize query parameters.

    See ChatViewSet().post_conversation(...) method for more details.
    """

    force_web_search = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Force web search.",
    )
    force_datagouv = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Force the DataGouv connector.",
    )
    model_hrid = serializers.CharField(
        required=False,
        default=None,
        help_text="HRID of the model to use for the conversation.",
        allow_blank=True,
        trim_whitespace=True,
    )
    arena_comparison = serializers.UUIDField(
        required=False,
        default=None,
        allow_null=True,
        help_text=(
            "Arena mode: id of the pending comparison this stream is a candidate of."
            " The model is chosen server side from the comparison and ``arena_side``."
        ),
    )
    arena_side = serializers.ChoiceField(
        choices=[ArenaSide.LEFT.value, ArenaSide.RIGHT.value],
        required=False,
        default=None,
        allow_null=True,
        help_text="Arena mode: displayed side this stream fills (left or right).",
    )

    def update(self, instance, validated_data):
        """Update method is not applicable in this context."""
        raise NotImplementedError("`update()` should not be used in this context.")

    def create(self, validated_data):
        """Create method is not applicable in this context."""
        raise NotImplementedError("`create()` should not be used in this context.")

    def validate(self, attrs):
        """Both arena parameters come together or not at all."""
        if bool(attrs.get("arena_comparison")) != bool(attrs.get("arena_side")):
            raise serializers.ValidationError(
                "arena_comparison and arena_side must be provided together."
            )
        return attrs

    def validate_model_hrid(self, value):
        """Validate the model_hrid field."""
        value = value or None  # Convert empty string to None

        if value and value not in settings.LLM_CONFIGURATIONS:
            raise serializers.ValidationError("Invalid model_hrid.")

        return value


class LLModelSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for LL models."""

    hrid = serializers.CharField(help_text="Human-readable ID of the model.")
    model_name = serializers.CharField(help_text="Name of the model.")
    human_readable_name = serializers.CharField(help_text="Human-readable name of the model.")
    icon = serializers.CharField(
        help_text="Icon representing the model.",
        allow_blank=True,
        required=False,
    )
    is_active = serializers.BooleanField(
        help_text="Indicates if the model is active and available for selection.",
        required=False,
        default=True,
    )
    supports_image = serializers.BooleanField(
        help_text="Whether the model can accept image inputs (multimodal).",
        required=False,
        default=False,
    )

    # Computed field to indicate if the model is the default model
    is_default = serializers.SerializerMethodField(
        help_text="Indicates if the model is the default model.",
    )

    @staticmethod
    @extend_schema_field(serializers.BooleanField)
    def get_is_default(obj) -> bool:
        """Check if the model is the default model."""
        return obj.hrid == settings.LLM_DEFAULT_MODEL_HRID


class ChatMessageCategoricalScoreSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for chat message scores."""

    message_id = serializers.CharField(help_text="ID of the message to score.")
    name = serializers.HiddenField(default="sentiment")
    value = serializers.ChoiceField(
        choices=["positive", "negative"],
        help_text="Sentiment of the score.",
    )


class ArenaDrawSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Input of the arena draw: what the client knows about the coming turn."""

    force_web_search = serializers.BooleanField(
        required=False, default=False, help_text="The user forced web search for this turn."
    )
    force_datagouv = serializers.BooleanField(
        required=False, default=False, help_text="The user forced data.gouv for this turn."
    )
    message = SchemaField(schema=UIMessage, required=False)
    model_hrid = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
        help_text="Model the user selected, pinned like a normal first turn would.",
    )

    def validate_message(self, message):
        """Only user input can start a comparison."""
        if message.role != "user":
            raise serializers.ValidationError("A user message is required.")
        return message

    def validate_model_hrid(self, value):
        """Same rule as ``ChatConversationRequestSerializer.validate_model_hrid``."""
        value = value or None
        if value and value not in settings.LLM_CONFIGURATIONS:
            raise serializers.ValidationError("Invalid model_hrid.")
        return value


class ArenaVoteSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Input of the arena vote: a displayed side, or null to abandon."""

    side = serializers.ChoiceField(
        choices=[ArenaSide.LEFT.value, ArenaSide.RIGHT.value],
        allow_null=True,
        help_text="Side the user preferred. Null keeps the production answer without a vote.",
    )


class ArenaAcknowledgementSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Thank-you block returned with a vote (never with an abandonment)."""

    user_votes = serializers.IntegerField(help_text="Votes of this user on recent comparisons.")
    experiment_votes = serializers.IntegerField(help_text="Votes recorded on this experiment.")
    milestone = serializers.ChoiceField(
        choices=["first_vote", "tenth_vote", "hundredth_vote"], allow_null=True
    )


class ArenaVoteResponseSerializer(ChatConversationSerializer):
    """Vote response: the conversation plus the acknowledgement block (schema only)."""

    acknowledgement = ArenaAcknowledgementSerializer(allow_null=True, read_only=True)

    class Meta(ChatConversationSerializer.Meta):  # pylint: disable=missing-class-docstring
        fields = [*ChatConversationSerializer.Meta.fields, "acknowledgement"]


class EditInDocsSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for opening a single assistant message in Docs."""

    message_id = serializers.CharField(help_text="ID of the assistant message to edit in Docs.")


class LLMConfigurationSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for LLM configuration."""

    models = LLModelSerializer(many=True)


class ChatConversationAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for chat conversation attachments."""

    url = serializers.SerializerMethodField()

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversationAttachment
        fields = [
            "id",
            "key",
            "content_type",
            "file_name",
            "size",
            "upload_state",
            "index_state",
            "url",
        ]
        read_only_fields = [
            "id",
            "key",
            "content_type",
            "file_name",
            "size",
            "upload_state",
            "index_state",
        ]

    def get_url(self, attachment) -> str | None:
        """Return the URL of the attachment."""
        if attachment.upload_state not in (
            AttachmentStatus.FILE_TOO_LARGE_TO_ANALYZE,
            AttachmentStatus.SUSPICIOUS,
            AttachmentStatus.READY,
        ):
            return None

        return f"{settings.MEDIA_BASE_URL}{settings.MEDIA_URL}{quote(attachment.key)}"


class CreateChatConversationAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for creating chat conversation attachments.

    For presigned_url mode: returns 'policy' field with presigned URL for direct S3 upload
    For backend modes: does not return 'policy' field (upload handled via backend endpoint)
    """

    policy = serializers.SerializerMethodField()
    uploaded_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    key = serializers.CharField(read_only=True)  # Key is generated server-side
    # Blank is let through here so `validate` can resolve a markdown file from its name.
    content_type = serializers.CharField(max_length=100, allow_blank=True)

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversationAttachment
        fields = ["id", "key", "content_type", "file_name", "size", "policy", "uploaded_by"]

    def get_policy(self, attachment) -> str | None:
        """Return the policy (presigned URL) only for presigned_url mode."""
        upload_mode = settings.FILE_UPLOAD_MODE

        # Only return presigned URL in presigned_url mode
        if upload_mode == FileUploadMode.PRESIGNED_URL:
            return generate_upload_policy(attachment.key)

        return None

    def validate_size(self, size: Optional[int]) -> Optional[int]:
        """Validate that the size is not greater than the maximum allowed size."""
        if not size:
            return size

        if size > settings.ATTACHMENT_MAX_SIZE:
            max_size = settings.ATTACHMENT_MAX_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                f"File size exceeds the maximum limit of {max_size:d} MB."
            )

        return size

    def validate(self, attrs):
        """Derive a markdown file's type from its name, the browser may not know it."""
        attrs = super().validate(attrs)
        content_type = resolve_markdown_content_type(attrs["file_name"], attrs["content_type"])
        if not content_type:
            raise serializers.ValidationError(
                {"content_type": ["This field may not be blank."]}, code="blank"
            )
        attrs["content_type"] = content_type
        return attrs


class ChatProjectNestedSerializer(serializers.ModelSerializer):
    """Lightweight read-only serializer for nested project info in search results."""

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatProject
        fields = ["id", "title", "icon"]
        read_only_fields = ["id", "title", "icon"]


class ChatConversationRetrieveSerializer(ChatConversationSerializer):
    """Retrieve view: nest project as {id, title, icon} instead of the bare id.

    The default list/create keep the bare project id (leaner, and asserted by
    tests), but a single conversation retrieval nests it so the client can read
    project.id/title/icon - matching the search endpoint and the frontend
    contract (e.g. the project indexing banner needs the conversation's project).
    """

    project = ChatProjectNestedSerializer(read_only=True)


class ChatConversationSearchSerializer(serializers.ModelSerializer):
    """Serializer for conversation search results with nested project info."""

    project = ChatProjectNestedSerializer(read_only=True)

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversation
        fields = ["id", "title", "created_at", "updated_at", "project"]
        read_only_fields = ["id", "title", "created_at", "updated_at", "project"]


class ChatConversationNestedSerializer(serializers.ModelSerializer):
    """Serializer for chat conversations."""

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatConversation
        fields = [
            "id",
            "title",
        ]
        read_only_fields = ["id", "title"]


class ChatProjectSerializer(serializers.ModelSerializer):
    """Serializer for projects."""

    LLM_INSTRUCTIONS_MAX_LENGTH = 4000  # prevent too large prompts, easier to handle here

    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    # Unbounded: the sidebar needs all conversations per project.
    # Projects are paginated at the view level, keeping payloads reasonable.
    conversations = ChatConversationNestedSerializer(many=True, read_only=True)
    llm_instructions = serializers.CharField(
        max_length=LLM_INSTRUCTIONS_MAX_LENGTH, required=False, allow_blank=True
    )

    class Meta:  # pylint: disable=missing-class-docstring
        model = models.ChatProject
        fields = [
            "id",
            "title",
            "created_at",
            "updated_at",
            "icon",
            "color",
            "llm_instructions",
            "owner",
            "conversations",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class ModelHealthItemSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Single model health record."""

    provider = serializers.CharField()
    model_id = serializers.CharField()
    status = serializers.ChoiceField(choices=models.ModelHealth.Status.choices)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ModelHealthResponseSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Wrapper for the model-health list response."""

    data = ModelHealthItemSerializer(many=True)


class AssistantHealthBannerSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Single health banner item."""

    level = serializers.ChoiceField(choices=["warning", "alert"])
    title = serializers.CharField()
    content = serializers.CharField()


class AssistantHealthSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Response shape for the assistant-health endpoint."""

    banners = AssistantHealthBannerSerializer(many=True)
    blocked = serializers.BooleanField()
