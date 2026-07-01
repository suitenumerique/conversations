"""Shared helpers for the chat views."""

import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.decorators import method_decorator

from botocore.exceptions import BotoCoreError, ClientError
from lasuite.oidc_login.decorators import refresh_oidc_access_token

logger = logging.getLogger(__name__)


def conditional_refresh_oidc_token(func):
    """
    Conditionally apply refresh_oidc_access_token decorator.

    The decorator is only applied if OIDC_STORE_REFRESH_TOKEN is True, meaning
    we can actually refresh something. Broader settings checks are done in settings.py.
    """
    if settings.OIDC_STORE_REFRESH_TOKEN:
        return method_decorator(refresh_oidc_access_token)(func)

    return func


def _bulk_delete_s3_blobs(keys):
    """Best-effort S3 cleanup for a set of keys.

    Used on conversation/project bulk delete paths where Django CASCADE drops
    attachment rows but never touches object storage. Each failure is logged;
    none re-raised. Caller passes a deduplicated iterable since markdown
    companions share the same S3 key as their original.
    """
    for key in keys:
        if not key:
            continue
        try:
            default_storage.delete(key)
        except BotoCoreError, ClientError, OSError:
            logger.exception("Failed to delete S3 object %s", key)
