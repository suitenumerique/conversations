"""Management command to fetch model health status from external providers."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

import requests

from core.models import ModelHealthSettings

from chat.models import ModelHealth

logger = logging.getLogger(__name__)

PROVIDERS = {
    "albert": {
        "url": lambda: settings.ALBERT_HEALTH_URL,
        "api_key": lambda: settings.ALBERT_API_KEY,
        "timeout": lambda: settings.ALBERT_HEALTH_TIMEOUT,
    }
}


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
            logger.error(
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

    def handle(self, *args, **options):
        provider = options["provider"]

        # Ensure singleton exists before locking (idempotent, safe outside transaction)
        ModelHealthSettings.get_solo()

        with transaction.atomic():
            cfg = ModelHealthSettings.objects.select_for_update().get()
            if cfg.last_run_at is not None:
                elapsed = (timezone.now() - cfg.last_run_at).total_seconds() / 60
                if elapsed < cfg.poll_interval_minutes:
                    self.stdout.write(
                        f"Skipping: last run {elapsed:.1f}min ago "
                        f"(interval={cfg.poll_interval_minutes}min)"
                    )
                    return
            # Persist before the HTTP call so concurrent pods see the lock is taken
            cfg.last_run_at = timezone.now()
            cfg.save(update_fields=["last_run_at"])

        url = PROVIDERS[provider]["url"]()
        timeout = PROVIDERS[provider]["timeout"]()
        api_key = PROVIDERS[provider]["api_key"]()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch model health for provider %s: %s", provider, exc)
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

            cache.set(f"model_health:{provider}:{model_id}", status, timeout=None)

        gone_ids = known_model_ids - seen_model_ids
        if gone_ids:
            cache.delete_many([f"model_health:{provider}:{mid}" for mid in gone_ids])

        self.stdout.write(
            self.style.SUCCESS(f"Fetched health for {len(data)} models from {provider}")
        )
