"""Apply the 90-day maximum retention of Arena content and personal associations."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from chat.arena_retention import redact_comparisons
from chat.models import ArenaComparison, ChatConversation


class Command(BaseCommand):
    """Run daily; retain metrics and remove candidate content and user links."""

    help = "Erase Arena content and personal links older than 90 days; keep anonymous metrics."

    def handle(self, *args, **options):
        expired = ArenaComparison.objects.filter(drawn_at__lt=timezone.now() - timedelta(days=90))
        expired = expired.filter(
            Q(conversation__isnull=False)
            | Q(user__isnull=False)
            | Q(input_snapshot__isnull=False)
            | Q(champion_payload__isnull=False)
            | Q(challenger_payload__isnull=False)
            | ~Q(champion_trace_id="")
            | ~Q(challenger_trace_id="")
        )
        count = 0
        for comparison in expired.only("pk", "conversation_id").iterator(chunk_size=200):
            with transaction.atomic():
                # Lock in the same order as result commits before removing content.
                list(
                    ChatConversation.objects.select_for_update().filter(
                        pk=comparison.conversation_id
                    )
                )
                count += redact_comparisons(
                    ArenaComparison.objects.filter(pk=comparison.pk), "retention_expired"
                )
        self.stdout.write(self.style.SUCCESS(f"Redacted {count} Arena comparisons."))
