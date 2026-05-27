"""Management command to de-index RAG collections from inactive conversations."""

import asyncio
import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.module_loading import import_string

from chat.enums import CollectionIndexState
from chat.models import ChatConversation, ChatConversationAttachment

logger = logging.getLogger(__name__)

_PARALLEL = 10


async def _deindex_chunk(chunk, backend_cls, threshold):
    """Fire HTTP deletes in parallel; each task owns its own DB clear + restore."""

    async def _delete_one(conv):
        def _claim():
            # Conditional claim: only clear if the row still has our collection_id
            # and is still inactive, so we don't race with a concurrent re-index.
            claimed = ChatConversation.objects.filter(
                pk=conv.pk,
                collection_id=conv.collection_id,
                updated_at__lt=threshold,
            ).update(collection_id=None, index_state=CollectionIndexState.DEINDEXED)
            if claimed:
                ChatConversationAttachment.objects.filter(conversation_id=conv.pk).update(
                    is_indexed=False, rag_document_id=None
                )
            return bool(claimed)

        if not await asyncio.to_thread(_claim):
            return False  # already claimed or re-indexed by another process

        backend = backend_cls(collection_id=conv.collection_id)
        await backend.adelete_collection()
        return True

    results = await asyncio.gather(
        *[_delete_one(conv) for conv in chunk],
        return_exceptions=True,
    )

    success = errors = 0
    for conv, result in zip(chunk, results, strict=True):
        if isinstance(result, Exception):
            # Conditional restore: only write back if the row is still NULL so we
            # don't overwrite a collection_id set by a concurrent re-index.
            await asyncio.to_thread(
                ChatConversation.objects.filter(pk=conv.pk, collection_id__isnull=True).update,
                collection_id=conv.collection_id,
                index_state=CollectionIndexState.INDEXED,
            )
            logger.error("Failed to de-index collection for conversation %s: %s", conv.pk, result)
            errors += 1
        elif result:
            logger.info(
                "De-indexed collection %s for conversation %s",
                conv.collection_id,
                conv.pk,
            )
            success += 1
        # result is False: another process already handled this row, skip
    return success, errors


class Command(BaseCommand):
    """De-index RAG collections from conversations inactive longer than the threshold."""

    help = "De-index RAG collections from inactive conversations."

    def handle(self, *args, **options):
        """Run de-indexing for inactive conversations up to DEINDEX_BATCH_SIZE."""
        threshold = timezone.now() - timedelta(days=settings.RAG_COLLECTION_INACTIVITY_DAYS)
        queryset = (
            ChatConversation.objects.filter(
                collection_id__isnull=False,
                updated_at__lt=threshold,
            )
            .only("id", "collection_id")
            .iterator(chunk_size=100)
        )
        backend_cls = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
        batch_limit = settings.DEINDEX_MAX_PER_RUN
        count_success = count_error = 0
        chunk = []

        def flush():
            nonlocal count_success, count_error, chunk
            s, e = asyncio.run(_deindex_chunk(chunk, backend_cls, threshold))
            count_success += s
            count_error += e
            chunk = []

        for conversation in queryset:
            if count_success + count_error + len(chunk) >= batch_limit:
                self.stdout.write("Batch limit reached, stopping.")
                break
            chunk.append(conversation)
            if len(chunk) == _PARALLEL:
                flush()

        if chunk:
            flush()

        self.stdout.write(
            self.style.SUCCESS(f"De-indexed {count_success} collection(s). {count_error} error(s).")
        )
