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

from core.file_upload.enums import AttachmentStatus
from core.models import BaseModel

from chat.ai_sdk_types import UIMessage
from chat.constants import HISTORY_SUMMARY_CLAIM_TTL_SECONDS
from chat.enums import (
    ArenaComparisonStatus,
    ArenaRole,
    ArenaSide,
    ArenaVoteOutcome,
    AttachmentIndexState,
    CollectionIndexState,
)

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
    arena_version = models.PositiveIntegerField(default=0)

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


def default_champion_hrid():
    """Default the champion to the production model."""
    return settings.LLM_DEFAULT_MODEL_HRID


class ArenaExperiment(BaseModel):
    """
    A blind A/B experiment pitting the production model (champion) against challengers.

    At most one experiment is active at a time. Every arena turn draws one challenger
    and streams both answers side by side; the user's pick is recorded in an
    ``ArenaComparison`` and committed to the conversation. The conversation itself
    stays pinned to the champion whichever side wins.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(
        default=False,
        help_text="Only one experiment can be active at a time.",
    )
    champion_model_hrid = models.CharField(
        max_length=100,
        default=default_champion_hrid,
        help_text="HRID of the production model every challenger is compared against.",
    )
    sampling_rate = models.FloatField(
        default=0.1,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Share of eligible turns that become arena turns (0 to 1).",
    )
    daily_cap_per_user = models.PositiveIntegerField(
        default=1,
        help_text="Maximum arena turns a single user sees per day.",
    )
    min_votes_for_conclusion = models.PositiveIntegerField(
        default=100,
        help_text=(
            "Below this number of votes a challenger row is labeled 'indicative' on the "
            "results page. A label, not a gate."
        ),
    )

    class Meta:  # pylint: disable=missing-class-docstring
        ordering = ["-created_at"]
        permissions = [("view_arena_results", "Can view arena results")]

    def __str__(self):
        return self.name

    def clean(self):
        """Enforce a single active experiment and a configured champion."""
        super().clean()
        if self.champion_model_hrid not in settings.LLM_CONFIGURATIONS:
            raise ValidationError(
                {"champion_model_hrid": "This model is not in the LLM configuration."}
            )
        if self.is_active:
            others = ArenaExperiment.objects.filter(is_active=True).exclude(pk=self.pk)
            if others.exists():
                raise ValidationError(
                    {"is_active": "Another experiment is already active. Deactivate it first."}
                )

    @property
    def champion_tools(self) -> list[str]:
        """Tool list configured on the champion, used to validate challengers."""
        return list(settings.LLM_CONFIGURATIONS[self.champion_model_hrid].tools)


class ArenaChallenger(BaseModel):
    """A model compared against the champion inside an experiment."""

    experiment = models.ForeignKey(
        ArenaExperiment, related_name="challengers", on_delete=models.CASCADE
    )
    model_hrid = models.CharField(max_length=100)

    class Meta:  # pylint: disable=missing-class-docstring
        constraints = [
            models.UniqueConstraint(
                fields=["experiment", "model_hrid"], name="arena_challenger_unique_per_experiment"
            )
        ]

    def __str__(self):
        return self.model_hrid

    def clean(self):
        """A challenger must be a configured, active model with the champion's tool list.

        Same tools on both sides keeps the comparison about the model, not the
        configuration.
        """
        super().clean()
        configuration = settings.LLM_CONFIGURATIONS.get(self.model_hrid)
        if configuration is None or not configuration.is_active:
            raise ValidationError(
                {"model_hrid": "This model is not an active model of the LLM configuration."}
            )
        if self.experiment_id is None:
            return
        if self.model_hrid == self.experiment.champion_model_hrid:
            raise ValidationError({"model_hrid": "The champion cannot be its own challenger."})
        if sorted(configuration.tools) != sorted(self.experiment.champion_tools):
            raise ValidationError(
                {
                    "model_hrid": (
                        "This model does not have the same tool list as the champion "
                        f"({', '.join(self.experiment.champion_tools) or 'no tools'})."
                    )
                }
            )


class ArenaComparison(BaseModel):
    """
    One blind comparison: the champion and a challenger answered the same user turn.

    Per-role metrics are flat ``champion_*`` / ``challenger_*`` columns so the results
    page can aggregate them in SQL. The two payloads hold the candidate answers until
    the winner is committed to the conversation; the loser payload is kept for analysis.
    """

    # PROTECT: the comparisons are the experiment's data. Deactivate an experiment
    # instead of deleting it; deleting one with comparisons is refused by the admin.
    experiment = models.ForeignKey(
        ArenaExperiment, related_name="comparisons", on_delete=models.PROTECT
    )
    conversation = models.ForeignKey(
        ChatConversation,
        related_name="arena_comparisons",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User, related_name="arena_comparisons", on_delete=models.SET_NULL, null=True, blank=True
    )
    turn = models.PositiveIntegerField(
        default=0, help_text="Index of the user message in the conversation."
    )
    tools_stripped = models.BooleanField(
        default=False, help_text="Side-effect tools were removed from both models."
    )

    champion_model_hrid = models.CharField(max_length=100)
    challenger_model_hrid = models.CharField(max_length=100)
    champion_side = models.CharField(max_length=5, choices=ArenaSide.choices())

    status = models.CharField(
        max_length=10,
        choices=ArenaComparisonStatus.choices(),
        default=ArenaComparisonStatus.PENDING,
    )
    winner = models.CharField(
        max_length=10, choices=ArenaVoteOutcome.choices(), blank=True, default=""
    )
    drawn_at = models.DateTimeField(default=timezone.now)
    voted_at = models.DateTimeField(null=True, blank=True)
    time_to_vote_ms = models.PositiveIntegerField(null=True, blank=True)
    conversation_version = models.PositiveIntegerField(default=0)
    input_snapshot = models.JSONField(null=True, blank=True)
    closed_reason = models.CharField(max_length=30, blank=True, default="")
    champion_started_at = models.DateTimeField(null=True, blank=True)
    challenger_started_at = models.DateTimeField(null=True, blank=True)

    champion_prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    champion_completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    champion_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    champion_first_token_ms = models.PositiveIntegerField(null=True, blank=True)
    champion_co2_impact = models.FloatField(null=True, blank=True)
    champion_trace_id = models.CharField(max_length=100, blank=True, default="")
    champion_finished_at = models.DateTimeField(null=True, blank=True)
    champion_error = models.TextField(blank=True, default="")
    champion_payload = models.JSONField(null=True, blank=True)
    champion_committed = models.BooleanField(
        default=False,
        help_text=(
            "The champion answer is already in the conversation history. It is written as"
            " soon as the champion finishes so nothing is lost if the user never votes; a"
            " vote for the challenger swaps it."
        ),
    )

    challenger_prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    challenger_completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    challenger_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    challenger_first_token_ms = models.PositiveIntegerField(null=True, blank=True)
    challenger_co2_impact = models.FloatField(null=True, blank=True)
    challenger_trace_id = models.CharField(max_length=100, blank=True, default="")
    challenger_finished_at = models.DateTimeField(null=True, blank=True)
    challenger_error = models.TextField(blank=True, default="")
    challenger_payload = models.JSONField(null=True, blank=True)

    class Meta:  # pylint: disable=missing-class-docstring
        ordering = ["-drawn_at"]
        indexes = [
            models.Index(fields=["experiment", "status"]),
            models.Index(fields=["user", "drawn_at"]),
        ]

    def __str__(self):
        return f"{self.champion_model_hrid} vs {self.challenger_model_hrid} [{self.status}]"

    @property
    def challenger_side(self) -> str:
        """Side the challenger was displayed on."""
        return ArenaSide.RIGHT if self.champion_side == ArenaSide.LEFT else ArenaSide.LEFT

    def role_for_side(self, side: str) -> str:
        """Map a displayed side back to the model role that produced it."""
        return ArenaRole.CHAMPION if side == self.champion_side else ArenaRole.CHALLENGER

    def model_hrid_for_side(self, side: str) -> str:
        """HRID of the model displayed on ``side``."""
        if self.role_for_side(side) == ArenaRole.CHAMPION:
            return self.champion_model_hrid
        return self.challenger_model_hrid

    def side_finished(self, role: str) -> bool:
        """Whether the given role finished streaming (successfully or not)."""
        return getattr(self, f"{role}_finished_at") is not None

    def side_succeeded(self, role: str) -> bool:
        """Whether the given role finished with a payload and no error."""
        return self.side_finished(role) and not getattr(self, f"{role}_error")

    def payload_for_side(self, side: str) -> dict | None:
        """Stored answer of the model displayed on ``side``, if it produced one."""
        return getattr(self, f"{self.role_for_side(side)}_payload")

    def is_restorable(self) -> bool:
        """Whether both answers are complete, so the choice can be shown again.

        A comparison the user left without voting stays pending and is rebuilt
        from these payloads on the next visit. One that never got both answers
        (a stream cut short) has nothing to compare and is resolved instead.
        """
        return all(
            self.side_succeeded(role) and getattr(self, f"{role}_payload")
            for role in (ArenaRole.CHAMPION, ArenaRole.CHALLENGER)
        )
