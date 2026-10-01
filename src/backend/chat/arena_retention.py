"""Remove Arena content and user links while retaining anonymous numeric metrics."""

from django.db import models as db_models
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from chat.models import ArenaComparison, ChatConversation, User


def redact_comparisons(queryset, reason):
    """Idempotent bulk redaction, also preventing in-flight result persistence."""
    return queryset.update(
        conversation=None,
        user=None,
        input_snapshot=None,
        champion_payload=None,
        challenger_payload=None,
        champion_trace_id="",
        challenger_trace_id="",
        champion_error=db_models.Case(
            db_models.When(
                champion_error__in=["", "cancelled", "unfinished when the comparison was resolved"],
                then=db_models.F("champion_error"),
            ),
            default=db_models.Value("redacted_error"),
            output_field=db_models.TextField(),
        ),
        challenger_error=db_models.Case(
            db_models.When(
                challenger_error__in=[
                    "",
                    "cancelled",
                    "unfinished when the comparison was resolved",
                ],
                then=db_models.F("challenger_error"),
            ),
            default=db_models.Value("redacted_error"),
            output_field=db_models.TextField(),
        ),
        status=db_models.Case(
            db_models.When(status="pending", then=db_models.Value("errored")),
            default=db_models.F("status"),
        ),
        closed_reason=db_models.Case(
            db_models.When(status="pending", then=db_models.Value(reason)),
            default=db_models.F("closed_reason"),
        ),
    )


@receiver(pre_delete, sender=ChatConversation)
def redact_deleted_conversation(sender, instance, using, **kwargs):  # pylint: disable=unused-argument
    """Collector signals cover API, admin, queryset and cascade deletions."""
    # The deletion collector already owns a transaction. Follow the commit lock order.
    ChatConversation.objects.using(using).select_for_update().get(pk=instance.pk)
    redact_comparisons(
        ArenaComparison.objects.using(using).filter(conversation_id=instance.pk), "deleted"
    )


@receiver(pre_delete, sender=User)
def redact_deleted_user(sender, instance, using, **kwargs):  # pylint: disable=unused-argument
    """Also erase orphaned comparisons still associated with a deleted user."""
    redact_comparisons(ArenaComparison.objects.using(using).filter(user_id=instance.pk), "deleted")
