"""Models for chat conversations."""

from datetime import timedelta
from typing import Sequence

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from django_pydantic_field import SchemaField
from solo.models import SingletonModel

from core.file_upload.enums import AttachmentStatus
from core.models import BaseModel

from chat.ai_sdk_types import UIMessage
from chat.constants import HISTORY_SUMMARY_CLAIM_TTL_SECONDS
from chat.enums import AttachmentIndexState, CollectionIndexState, RoutingTier

User = get_user_model()


class ChatProjectIcon(models.TextChoices):
    """Project icon text choices."""

    FOLDER = "folder", "Folder icon"
    FILE = "file", "File icon"
    PERSO = "perso", "Perso icon"
    GEAR = "gear", "Gear icon"
    MEGAPHONE = "megaphone", "Megaphone icon"
    STAR = "star", "Star icon"
    BOOKMARK = "bookmark", "Bookmark icon"
    CHART = "chart", "Chart icon"
    PHOTO = "photo", "Photo icon"
    EURO = "euro", "Euro icon"
    KEY = "key", "Key icon"
    JUSTICE = "justice", "Justice icon"
    BOOK = "book", "Book icon"
    PUZZLE = "puzzle", "Puzzle icon"
    PALETTE = "palette", "Palette icon"
    TERMINAL = "terminal", "Terminal icon"
    CAR = "car", "Car icon"
    MUSIC = "music", "Music icon"
    CHECKMARK = "checkmark", "Checkmark icon"
    LA_SUITE = "la_suite", "La Suite icon"


class ChatProjectColor(models.TextChoices):
    """Project icon color choices. We keep it generic to ease frontend compatibility."""

    COLOR_1 = "color_1", "Color 1"
    COLOR_2 = "color_2", "Color 2"
    COLOR_3 = "color_3", "Color 3"
    COLOR_4 = "color_4", "Color 4"
    COLOR_5 = "color_5", "Color 5"
    COLOR_6 = "color_6", "Color 6"
    COLOR_7 = "color_7", "Color 7"
    COLOR_8 = "color_8", "Color 8"
    COLOR_9 = "color_9", "Color 9"
    COLOR_10 = "color_10", "Color 10"


class ChatProject(BaseModel):
    """Model representing a project that groups conversations together."""

    owner = models.ForeignKey(
        User,
        related_name="projects",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    title = models.CharField(
        max_length=100,
        help_text="Title of the chat project",
    )
    icon = models.CharField(max_length=20, choices=ChatProjectIcon, help_text="Project icon")
    color = models.CharField(
        max_length=20, choices=ChatProjectColor, help_text="Project icon color"
    )

    llm_instructions = models.TextField(
        blank=True,
        help_text="Custom user instructions to be sent to the llm",
    )

    collection_id = models.CharField(
        blank=True,
        null=True,
        help_text=(
            "Collection ID for the project, used for RAG document search across project files"
        ),
    )

    def __str__(self):
        return self.title


class ChatConversation(BaseModel):
    """
    Model representing a chat conversation.

    This model stores the details of a chat conversation:
    - `owner`: The user who owns the conversation.
    - `title`: An optional title for the conversation, provided by frontend,
      the 100 first characters of the first user input message.
    - `ui_messages`: A JSON field of UI messages sent by the frontend, all content is
      overridden at each new request from the frontend.
    - `pydantic_messages`: A JSON field of PydanticAI messages, used to store conversation history.
    - `messages`: A JSON field of stored messages for the conversation, sent to frontend
       when loading the conversation.
    - `agent_usage`: A JSON field of agent usage statistics for the conversation,
    """

    owner = models.ForeignKey(
        User,
        related_name="conversations",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    title = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Title of the chat conversation",
    )
    title_set_by_user_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the user manually set the title. If set, prevent automatic "
        "title generation.",
    )
    ui_messages = models.JSONField(
        default=list,
        blank=True,
        help_text="UI messages for the chat conversation, sent by frontend, not used",
    )
    pydantic_messages = models.JSONField(
        default=list,
        blank=True,
        help_text="Pydantic messages for the chat conversation, used for history",
    )
    history_summary = models.TextField(
        blank=True,
        default="",
        help_text="Latest generated conversation summary used as system context",
    )
    history_summary_checkpoint = models.PositiveIntegerField(
        default=0,
        help_text="Number of pydantic history messages already compacted into history_summary",
    )
    messages: Sequence[UIMessage] = SchemaField(
        schema=list[UIMessage],
        default=list,
        blank=True,
        help_text="Stored messages for the chat conversation, sent to frontend",
    )

    agent_usage = models.JSONField(
        default=dict,
        blank=True,
        help_text="Agent usage for the chat conversation, provided by OpenAI API",
    )

    collection_id = models.CharField(
        blank=True,
        null=True,
        help_text="Collection ID for the conversation, used for RAG document search",
    )

    index_state = models.CharField(
        max_length=20,
        choices=CollectionIndexState.choices(),
        default=CollectionIndexState.UNINDEXED,
        help_text="Current indexing state of this conversation's RAG collection",
    )

    project = models.ForeignKey(
        ChatProject,
        related_name="conversations",
        on_delete=models.SET_NULL,  # explicitly avoid Cascade here
        null=True,
        blank=True,
    )

    model_hrid = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "HRID of the LLM pinned to this conversation. Set on the first message and"
            " kept for the whole conversation so a recovered main model does not move"
            " ongoing chats. Empty string means 'not yet pinned'."
        ),
    )

    history_summary_claimed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When a worker claimed summary generation; claims expire after "
        "HISTORY_SUMMARY_CLAIM_TTL_SECONDS (dead-worker liveness bound)",
    )

    pinned_tier = models.CharField(
        max_length=20,
        choices=RoutingTier.choices(),
        null=True,
        blank=True,
        help_text=(
            "Complexity tier the user pinned on this conversation."
            " Null means Auto: the router picks the tier on every turn."
        ),
    )

    last_routing = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Routing decision of the last turn (tier, model_hrid and classifier labels),"
            " used as a hint by the router on the next turn."
        ),
    )

    class Meta:  # pylint: disable=missing-class-docstring
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "project"]),
            # Global "most recently updated first" listing, used by the admin changelist.
            models.Index(fields=["-updated_at", "-id"]),
        ]

    def __str__(self):
        return self.title or str(self.pk)

    def claim_history_summarization(self) -> bool:
        """Atomically claim summary generation; True when we now hold the claim.

        Succeeds when unclaimed or when the previous claim exceeded the TTL
        (its worker is provably dead).
        """
        now = timezone.now()
        expiry = now - timedelta(seconds=HISTORY_SUMMARY_CLAIM_TTL_SECONDS)
        updated = (
            type(self)
            .objects.filter(pk=self.pk)
            .filter(
                models.Q(history_summary_claimed_at__isnull=True)
                | models.Q(history_summary_claimed_at__lt=expiry)
            )
            .update(history_summary_claimed_at=now)
        )
        if updated:
            self.history_summary_claimed_at = now
        return bool(updated)

    def release_history_summarization_claim(self) -> None:
        """Release the claim, but only while we still hold it.

        Guards against a stale worker wiping a newer worker's live claim: if
        our claim already expired and another worker reclaimed, the timestamp
        no longer matches ours and the update is a no-op. Mirrors the guarded
        checkpoint write in `persist_history_summary`.
        """
        type(self).objects.filter(
            pk=self.pk, history_summary_claimed_at=self.history_summary_claimed_at
        ).update(history_summary_claimed_at=None)
        self.history_summary_claimed_at = None

    @property
    def history_summarization_claim_is_live(self) -> bool:
        """True while a claim exists and its worker may still be alive."""
        claimed_at = self.history_summary_claimed_at
        if claimed_at is None:
            return False
        return claimed_at > timezone.now() - timedelta(seconds=HISTORY_SUMMARY_CLAIM_TTL_SECONDS)

    def persist_history_summary(self, summary: str, checkpoint: int) -> bool:
        """Persist a generated summary only if it advances the checkpoint.

        Messages are append-only, so a larger checkpoint is always the newer
        result; late or duplicate completions are rejected.
        """
        updated = (
            type(self)
            .objects.filter(pk=self.pk, history_summary_checkpoint__lt=checkpoint)
            .update(
                history_summary=summary,
                history_summary_checkpoint=checkpoint,
                updated_at=timezone.now(),
            )
        )
        if updated:
            self.history_summary = summary
            self.history_summary_checkpoint = checkpoint
        return bool(updated)


class ChatConversationAttachment(BaseModel):
    """
    Model representing a file attachment.

    An attachment belongs to exactly one of: a conversation or a project.
    - Conversation attachments are scoped to a single chat.
    - Project attachments are shared across all conversations in that project.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        related_name="attachments",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        ChatProject,
        related_name="attachments",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    uploaded_by = models.ForeignKey(
        User,
        related_name="uploaded_attachments",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        help_text="User who uploaded the attachment",
    )
    upload_state = models.CharField(
        max_length=40,
        choices=AttachmentStatus.choices,
        default=AttachmentStatus.PENDING,
    )
    key = models.CharField(
        blank=False,
        null=False,
        help_text="File path of the attachment in the object storage",
    )
    file_name = models.CharField(
        blank=False,
        null=False,
        help_text="Original name of the attachment file",
    )
    content_type = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        help_text="MIME type of the attachment file",
    )
    size = models.PositiveBigIntegerField(null=True, blank=True)

    conversion_from = models.CharField(
        blank=True,
        null=True,
        help_text="Original file key if the Markdown from another file",
    )
    rag_document_id = models.CharField(
        blank=True,
        null=True,
        help_text=(
            "Per-document id returned by the RAG backend at indexing time, "
            "used to remove the document from its collection on attachment delete"
        ),
    )

    # `is_indexed` and `index_state` overlap: `is_indexed=True` is exactly
    # `index_state == INDEXED`. They coexist for historical reasons and split by
    # owner. Conversation attachments use the older boolean `is_indexed` (it
    # cannot express INDEXING/FAILED, which the conversation flow does not need).
    # Project attachments use `index_state`, whose intermediate/failure states
    # drive the upload UI. The project flow keeps both in sync so the 0009
    # backfill invariant (rag_document_id present => is_indexed=True) holds.
    # End state: migrate conversation callers onto `index_state` and drop this.
    is_indexed = models.BooleanField(
        default=False,
        help_text="Whether this attachment has been indexed in the RAG backend",
    )

    index_state = models.CharField(
        max_length=20,
        choices=AttachmentIndexState.choices(),
        default=AttachmentIndexState.NOT_INDEXED,
        help_text="Per-attachment RAG indexing lifecycle (set by the project indexing task)",
    )
    processing_error = models.TextField(
        blank=True,
        null=True,
        help_text="Human-readable reason the last indexing attempt failed, if any",
    )

    class Meta:  # pylint: disable=missing-class-docstring
        constraints = [
            models.CheckConstraint(
                name="attachment_owner_exactly_one",
                condition=(
                    models.Q(conversation__isnull=False, project__isnull=True)
                    | models.Q(conversation__isnull=True, project__isnull=False)
                ),
            ),
        ]


class ModelHealth(models.Model):
    """Append-only health status record fetched from an external provider."""

    class Status(models.TextChoices):  # pylint: disable=missing-class-docstring
        GREEN = "green"
        YELLOW = "yellow"
        RED = "red"

    provider = models.CharField(max_length=50)
    model_id = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:  # pylint: disable=missing-class-docstring
        indexes = [models.Index(fields=["provider", "model_id", "-updated_at"])]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.provider}/{self.model_id}: {self.status}"


# --------------------------------------------------------------------------- #
# Router tiers
# --------------------------------------------------------------------------- #

TIER_MODEL_SETTING_NAMES = {
    RoutingTier.SIMPLE: "LLM_TIER_SIMPLE_MODEL_HRID",
    RoutingTier.STANDARD: "LLM_TIER_STANDARD_MODEL_HRID",
    RoutingTier.COMPLEX: "LLM_TIER_COMPLEX_MODEL_HRID",
}


def default_tier_model_hrid(tier: str) -> str:
    """Model configured for ``tier`` in the Django settings, else the default model."""
    setting_name = TIER_MODEL_SETTING_NAMES[RoutingTier(tier)]
    return getattr(settings, setting_name, "") or settings.LLM_DEFAULT_MODEL_HRID


def _tier_field_help(what: str) -> str:
    return (
        f"{what} Blank means 'use the LLM_TIER_*_MODEL_HRID setting', which itself"
        " defaults to LLM_DEFAULT_MODEL_HRID."
    )


def _chat_models_error(hrids) -> str | None:
    """Error for the first entry of ``hrids`` that is not a chat model, if any."""
    if not isinstance(hrids, list):
        return "Expected a list of model HRIDs."
    for hrid in hrids:
        if not hrid:
            continue
        configuration = settings.LLM_CONFIGURATIONS.get(hrid)
        if configuration is None or configuration.role != "chat":
            return f"'{hrid}' is not a chat model of the LLM configuration."
    return None


class RoutingTierSettings(SingletonModel):
    """Singleton holding the model of each complexity tier and the router threshold.

    "Model" is what the tier runs; "alternatives" are the models the constraint
    walk tries when the tier model lacks a capability the turn needs (images,
    web search, context length).
    """

    simple_model_hrid = models.CharField(
        max_length=100, blank=True, default="", help_text=_tier_field_help("Tier 1 model.")
    )
    simple_alternatives = models.JSONField(
        default=list, blank=True, help_text="HRIDs of the tier 1 alternatives."
    )
    standard_model_hrid = models.CharField(
        max_length=100, blank=True, default="", help_text=_tier_field_help("Tier 2 model.")
    )
    standard_alternatives = models.JSONField(
        default=list, blank=True, help_text="HRIDs of the tier 2 alternatives."
    )
    complex_model_hrid = models.CharField(
        max_length=100, blank=True, default="", help_text=_tier_field_help("Tier 3 model.")
    )
    complex_alternatives = models.JSONField(
        default=list, blank=True, help_text="HRIDs of the tier 3 alternatives."
    )
    router_model_hrid = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Classifier model. Blank means 'use the LLM_ROUTER_MODEL_HRID setting'.",
    )
    confidence_threshold = models.FloatField(
        default=0.70,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Tiers 1 and 3 are chosen only at or above this classifier confidence.",
    )

    class Meta:  # pylint: disable=missing-class-docstring
        verbose_name = "Routing Tier Settings"

    def __str__(self):
        return "Routing tier settings"

    def model_for(self, tier: str) -> str:
        """HRID of the model running ``tier``: the admin value, else the settings."""
        tier = RoutingTier(tier)
        return getattr(self, f"{tier.value}_model_hrid") or default_tier_model_hrid(tier)

    def alternatives_for(self, tier: str) -> list[str]:
        """HRIDs of the alternatives of ``tier``, the tier model excluded."""
        tier = RoutingTier(tier)
        model_hrid = self.model_for(tier)
        alternatives = getattr(self, f"{tier.value}_alternatives") or []
        kept: list[str] = []
        for hrid in alternatives:
            if hrid and hrid != model_hrid and hrid not in kept:
                kept.append(hrid)
        return kept

    def all_models_for(self, tier: str) -> list[str]:
        """The tier model first, then its alternatives."""
        return [self.model_for(tier), *self.alternatives_for(tier)]

    def clean(self):
        """Every referenced model must be a chat model of the configuration."""
        super().clean()
        errors = {}
        for tier in RoutingTier:
            for field_name, hrids in (
                (f"{tier.value}_model_hrid", [getattr(self, f"{tier.value}_model_hrid")]),
                (f"{tier.value}_alternatives", getattr(self, f"{tier.value}_alternatives") or []),
            ):
                error = _chat_models_error(hrids)
                if error:
                    errors[field_name] = error
        if self.router_model_hrid and self.router_model_hrid not in settings.LLM_CONFIGURATIONS:
            errors["router_model_hrid"] = "This model is not in the LLM configuration."
        if errors:
            raise ValidationError(errors)
