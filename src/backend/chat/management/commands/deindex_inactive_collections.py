"""Management command to de-index RAG collections from inactive conversations."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.module_loading import import_string

from chat.models import ChatConversation

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """De-index RAG collections from conversations inactive longer than the threshold."""

    help = "De-index RAG collections from inactive conversations."

    def handle(self, *args, **options):
        """Run de-indexing for all inactive conversations."""
        threshold = timezone.now() - timedelta(days=settings.RAG_COLLECTION_INACTIVITY_DAYS)
        conversations = ChatConversation.objects.filter(
            collection_id__isnull=False,
            updated_at__lt=threshold,
        )

        backend_cls = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        count_success = 0
        count_error = 0

        for conversation in conversations:
            old_collection_id = conversation.collection_id
            try:
                # Clear DB first so a crash during delete_collection doesn't leave a stale pointer.
                ChatConversation.objects.filter(pk=conversation.pk).update(collection_id=None)
                backend = backend_cls(collection_id=old_collection_id)
                backend.delete_collection()
                count_success += 1
                logger.info(
                    "De-indexed collection %s for conversation %s",
                    old_collection_id,
                    conversation.pk,
                )
            except Exception:  # pylint: disable=broad-except
                # Restore so the next run can retry.
                ChatConversation.objects.filter(pk=conversation.pk).update(
                    collection_id=old_collection_id
                )
                count_error += 1
                logger.exception(
                    "Failed to de-index collection for conversation %s", conversation.pk
                )

        self.stdout.write(
            self.style.SUCCESS(f"De-indexed {count_success} collection(s). {count_error} error(s).")
        )
