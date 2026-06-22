"""Management command to de-index RAG collections from inactive conversations."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.module_loading import import_string

import requests

from chat.enums import CollectionIndexState
from chat.models import ChatConversation, ChatConversationAttachment

logger = logging.getLogger(__name__)


def _deindex_one(conv, *, backend_cls, threshold):
    """Claim, delete collection, restore on failure.

    Returns True (success), False (skipped — already claimed), None (error).
    """
    claimed = ChatConversation.objects.filter(
        pk=conv.pk,
        collection_id=conv.collection_id,
        updated_at__lt=threshold,
    ).update(collection_id=None, index_state=CollectionIndexState.DEINDEXED)

    if not claimed:
        return None  # already claimed or re-indexed by another process

    attachment_snapshot = {
        pk: (is_indexed, rag_id)
        for pk, is_indexed, rag_id in ChatConversationAttachment.objects.filter(
            conversation_id=conv.pk
        ).values_list("pk", "is_indexed", "rag_document_id")
    }
    ChatConversationAttachment.objects.filter(conversation_id=conv.pk).update(
        is_indexed=False, rag_document_id=None
    )

    try:
        backend_cls(collection_id=conv.collection_id).delete_collection()
    except Exception as exc:  # pylint: disable=broad-except
        if isinstance(exc, requests.HTTPError):
            response = exc.response
            if response is not None and response.status_code == 404:
                # Collection already gone on the backend — the earlier
                # .update() calls already cleared our state, so treat it as
                # a successful de-index.
                logger.info(
                    "Collection %s for conversation %s already deleted (404), "
                    "treating as de-indexed",
                    conv.collection_id,
                    conv.pk,
                )
                return True
        # Conditional restore: only write back if the row is still NULL so we
        # don't overwrite a collection_id set by a concurrent re-index.
        ChatConversation.objects.filter(pk=conv.pk, collection_id__isnull=True).update(
            collection_id=conv.collection_id,
            index_state=conv.index_state,
        )
        for pk, (prev_is_indexed, rag_id) in attachment_snapshot.items():
            ChatConversationAttachment.objects.filter(pk=pk, rag_document_id__isnull=True).update(
                is_indexed=prev_is_indexed, rag_document_id=rag_id
            )
        logger.exception("Failed to de-index collection for conversation %s", conv.pk)
        return False

    logger.info("De-indexed collection %s for conversation %s", conv.collection_id, conv.pk)
    return True


class Command(BaseCommand):
    """De-index RAG collections from conversations inactive longer than the threshold."""

    help = "De-index RAG collections from inactive conversations."

    def handle(self, *args, **options):
        threshold = timezone.now() - timedelta(days=settings.RAG_COLLECTION_INACTIVITY_DAYS)
        conversations = list(
            ChatConversation.objects.filter(
                collection_id__isnull=False,
                updated_at__lt=threshold,
            )
            .exclude(collection_id="")
            .order_by("updated_at")
            .only("id", "collection_id", "index_state")[: settings.DEINDEX_MAX_PER_RUN]
        )
        backend_cls = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)

        deindex = partial(_deindex_one, backend_cls=backend_cls, threshold=threshold)
        with ThreadPoolExecutor(max_workers=settings.DEINDEX_PARALLEL_REQUESTS) as executor:
            results = list(executor.map(deindex, conversations))

        count_success = sum(1 for r in results if r is True)
        count_error = sum(1 for r in results if r is False)
        self.stdout.write(
            self.style.SUCCESS(f"De-indexed {count_success} collection(s). {count_error} error(s).")
        )
