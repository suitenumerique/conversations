"""Management command to fetch model health status from external providers."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

import requests

from core.models import ModelHealthSettings

from chat.model_health import model_health_cache_key, set_model_health
from chat.models import ModelHealth

logger = logging.getLogger(__name__)

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
                "Invalid JSON from provider %s (HTTP %s): %s",
                provider,
                response.status_code,
                response.text[:200],
            )
            raise CommandError("Invalid JSON response from provider") from None

        if not isinstance(payload, dict):
            logger.error(
                "Unexpected response shape from provider %s: expected dict, got %s",
                provider,
                type(payload).__name__,
            )
            raise CommandError("Unexpected response shape from provider")

        data = payload.get("data", [])
        if not isinstance(data, list):
            logger.error("'data' field is not a list in provider %s response", provider)
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
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.exception("Failed to fetch model health for provider %s: %s", provider, exc)
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
                    logger.warning("Skipping malformed item (missing 'id'): %r", item)
                    continue
                seen_model_ids.add(model_id)
                status = item.get("status")
                status = STATUS_ALIASES.get(status, status)

                if status not in ModelHealth.Status.values:
                    logger.warning("Unknown status %r for model %s, skipping", status, model_id)
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
