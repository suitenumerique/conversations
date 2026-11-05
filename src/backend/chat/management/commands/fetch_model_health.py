"""Management command to fetch model health status from external providers."""

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

import httpx
import structlog

from core.models import ModelHealthSettings

from chat.model_health import model_health_cache_key, set_model_health
from chat.models import ModelHealth

logger = structlog.get_logger(__name__)

PROVIDERS = {
    "albert": {
        "url": lambda: settings.ALBERT_HEALTH_URL,
        "api_key": lambda: settings.ALBERT_API_KEY,
        "timeout": lambda: settings.ALBERT_HEALTH_TIMEOUT,
    }
}

# Legacy provider statuses mapped to their current enum value, in case a provider
# still emits the old "orange" label after the rename to "yellow".
STATUS_ALIASES = {"orange": ModelHealth.Status.YELLOW.value}


class Command(BaseCommand):
    """Fetch model health status from an external provider, store in DB and cache."""

    help = "Fetch model health status from an external provider, store in DB and cache."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            required=True,
            choices=list(PROVIDERS.keys()),
            help="Provider to fetch health data for.",
        )

    def _parse_response(self, response, provider):
        """Parse and validate the JSON response; return the data list or raise CommandError."""
        try:
            payload = response.json()
        except ValueError:
            logger.exception(
                "model_health_invalid_json", provider=provider, status_code=response.status_code
            )
            raise CommandError("Invalid JSON response from provider") from None

        if not isinstance(payload, dict):
            logger.error(
                "model_health_unexpected_shape",
                provider=provider,
                payload_type=type(payload).__name__,
            )
            raise CommandError("Unexpected response shape from provider")

        data = payload.get("data", [])
        if not isinstance(data, list):
            logger.error("model_health_data_not_a_list", provider=provider)
            raise CommandError("'data' field is not a list")

        return data

    def handle(self, *args, **options):  # pylint: disable=too-many-locals
        provider = options["provider"]

        cfg = ModelHealthSettings.get_solo()
        lock_key = f"model_health:poll_lock:{provider}"
        ttl = cfg.poll_interval_minutes * 60
        acquired = cache.add(lock_key, 1, timeout=ttl)
        if not acquired:
            self.stdout.write(f"Skipping: lock key present (TTL ≈ {ttl}s)")
            return

        try:
            url = PROVIDERS[provider]["url"]()
            timeout = PROVIDERS[provider]["timeout"]()
            api_key = PROVIDERS[provider]["api_key"]()
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

            try:
                response = httpx.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.exception(
                    "model_health_fetch_failed", provider=provider, error_type=type(exc).__name__
                )
                raise CommandError(str(exc)) from exc

            data = self._parse_response(response, provider)

            known_model_ids = set(
                ModelHealth.objects.filter(provider=provider)
                .values_list("model_id", flat=True)
                .distinct()
            )

            seen_model_ids = set()
            for item in data:
                model_id = item.get("id")
                if not model_id:
                    logger.warning("model_health_item_without_id", provider=provider)
                    continue
                seen_model_ids.add(model_id)
                status = item.get("status")
                status = STATUS_ALIASES.get(status, status)

                if status not in ModelHealth.Status.values:
                    logger.warning("model_health_unknown_status", status=status, model_id=model_id)
                    continue

                latest = (
                    ModelHealth.objects.filter(provider=provider, model_id=model_id)
                    .order_by("-updated_at")
                    .first()
                )

                if latest is not None and latest.status == status:
                    latest.save()
                else:
                    ModelHealth.objects.create(provider=provider, model_id=model_id, status=status)

                set_model_health(provider, model_id, status)

            gone_ids = known_model_ids - seen_model_ids
            if gone_ids:
                cache.delete_many([model_health_cache_key(provider, mid) for mid in gone_ids])

            self.stdout.write(
                self.style.SUCCESS(f"Fetched health for {len(data)} models from {provider}")
            )
        except CommandError:
            cache.delete(lock_key)
            raise
