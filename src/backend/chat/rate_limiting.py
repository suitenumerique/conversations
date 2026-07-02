"""Per-user token-rate tracking and model-health-aware cooldown heuristic.

To mitigate concurrent load on the inference infrastructure we track each
user's total token usage (input + output) over a trailing window. When the
model they are using is known to be degraded (yellow or red health) and they
have spent more than a threshold over that window, the client is asked to
wait a cooldown period before the next request. See ``compute_cooldown_seconds``.
"""

import logging
import math
import time

from django.core.cache import cache

from rest_framework.throttling import BaseThrottle

from core.models import ChatCooldownSettings

from chat.llm_configuration import LLModel
from chat.model_health import get_model_health
from chat.models import ModelHealth

logger = logging.getLogger(__name__)

# A user's token usage is summed over a trailing window (configurable via the
# ChatCooldownSettings singleton, default 20 minutes), split into one-minute
# buckets so old usage decays minute-by-minute rather than all at once. The
# 60s bucket granularity is plenty precise for a load-shedding heuristic.
_BUCKET_SECONDS = 60


def _bucket_count(window_seconds: int) -> int:
    return window_seconds // _BUCKET_SECONDS


def _bucket_ttl(window_seconds: int) -> int:
    # Buckets outlive the window by one extra bucket so a read never races a
    # just-expired key at the edge of the window.
    return window_seconds + _BUCKET_SECONDS


def _bucket_key(user_id, bucket: int) -> str:
    return f"token_usage:{user_id}:{bucket}"


def record_token_usage(user_id, tokens: int, window_seconds: int) -> None:
    """Add ``tokens`` to the current minute bucket for ``user_id``."""
    if tokens <= 0:
        return
    bucket = int(time.time()) // _BUCKET_SECONDS
    key = _bucket_key(user_id, bucket)
    # ``add`` is a no-op if the bucket already exists, so concurrent requests in
    # the same minute share one counter; ``incr`` is then always safe.
    cache.add(key, 0, timeout=_bucket_ttl(window_seconds))
    try:
        cache.incr(key, tokens)
    except ValueError:
        # The bucket expired between ``add`` and ``incr`` (extremely unlikely);
        # recreate it rather than dropping the usage.
        cache.set(key, tokens, timeout=_bucket_ttl(window_seconds))


def get_tokens_last_window(user_id, window_seconds: int) -> int:
    """Return the user's total tokens recorded over the trailing window."""
    current = int(time.time()) // _BUCKET_SECONDS
    keys = [
        _bucket_key(user_id, current - offset) for offset in range(_bucket_count(window_seconds))
    ]
    return sum(cache.get_many(keys).values())


def _health_lookup_target(model_config: LLModel) -> tuple[str, str] | None:
    """Return ``(provider, model_id)`` for the model-health cache lookup.

    Matches the keys written by the ``fetch_model_health`` command:
    ``(provider.hrid, model_name)``. Returns None when the model has no
    resolved provider (e.g. the dev default), in which case health is unknown.
    """
    if model_config.provider is None:
        return None
    return model_config.provider.hrid, model_config.model_name


def compute_cooldown_seconds(
    model_config: LLModel, tokens_in_window: int, cooldown_settings: ChatCooldownSettings
) -> int:
    """Cooldown (in seconds) the client should wait before its next request.

    Zero unless the model is known to be degraded (yellow or red): a green,
    unknown, or unreported health status incurs no cooldown, and neither does
    usage still under the token threshold. Otherwise (known-degraded, over
    threshold) the wait is ``overage * factor + floor``, where ``factor`` is
    per-model (smaller for models with more GPUs) and ``floor`` is the minimum
    cooldown once the threshold is crossed.
    """
    target = _health_lookup_target(model_config)
    if target is None:
        return 0
    # Cooldown applies only when the model is known to be degraded (yellow or
    # red). Unknown/unreported health is treated as healthy and does not throttle.
    if get_model_health(*target) not in [ModelHealth.Status.RED, ModelHealth.Status.YELLOW]:
        return 0

    overage = tokens_in_window - cooldown_settings.token_threshold
    if overage <= 0:
        return 0

    factor = (
        model_config.cooldown_factor
        if model_config.cooldown_factor is not None
        else cooldown_settings.default_factor
    )
    return round(overage * factor + cooldown_settings.min_seconds)


def record_and_compute_cooldown(user_id, model_config: LLModel, request_tokens: int) -> int:
    """Record this request's token usage and return (and persist) the cooldown.

    Composes the rate-limiting primitives end to end: add the request's tokens
    to the sliding window, compute the resulting cooldown for the model, and
    persist it so ``ChatCooldownThrottle`` can enforce it server-side. Runs
    synchronously (Django cache + model-health lookup); call via
    ``sync_to_async`` from the streaming path.
    """
    cooldown_settings = ChatCooldownSettings.get_solo()
    window_seconds = cooldown_settings.window_seconds
    record_token_usage(user_id, request_tokens, window_seconds)
    tokens_in_window = get_tokens_last_window(user_id, window_seconds)
    cooldown_seconds = compute_cooldown_seconds(model_config, tokens_in_window, cooldown_settings)
    set_cooldown(user_id, cooldown_seconds)
    return cooldown_seconds


def _cooldown_key(user_id) -> str:
    return f"chat_cooldown:{user_id}"


def set_cooldown(user_id, seconds: int) -> None:
    """Record that ``user_id`` must wait ``seconds`` before the next request.

    Stores the epoch second at which the cooldown ends, with a matching TTL so
    the key disappears on its own when the cooldown is over.
    """
    if seconds <= 0:
        return
    cache.set(_cooldown_key(user_id), time.time() + seconds, timeout=seconds)


def get_cooldown_remaining(user_id) -> int:
    """Return whole seconds left on ``user_id``'s cooldown (0 if none)."""
    until = cache.get(_cooldown_key(user_id))
    if not until:
        return 0
    return max(0, math.ceil(until - time.time()))


class ChatCooldownThrottle(BaseThrottle):
    """Reject chat requests while the user is within a model-load cooldown.

    The cooldown is computed at the end of each response (see
    ``compute_cooldown_seconds``) and persisted via ``set_cooldown``. This is
    the server-side backstop to the client-side wait: a request arriving before
    the cooldown elapses is throttled with a 429 and a ``Retry-After`` header.
    """

    def __init__(self):
        self._wait_seconds = 0

    def allow_request(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return True
        self._wait_seconds = get_cooldown_remaining(user.pk)
        return self._wait_seconds <= 0

    def wait(self):
        return self._wait_seconds or None
