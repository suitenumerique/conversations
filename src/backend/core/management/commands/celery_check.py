"""Management command to check that Celery is wired up correctly."""

from django.conf import settings
from django.core.management.base import BaseCommand

from core.tasks import debug_add


class Command(BaseCommand):
    """Enqueue the debug_add task to verify the worker and broker are reachable."""

    help = "Enqueue a trivial Celery task to verify the worker and broker are reachable"

    def handle(self, *args, **options):
        """Send debug_add to the worker.

        Calling .delay() already round-trips to the broker, so a returned task id means
        the broker is reachable. The result is only fetched when a result backend is
        configured (e.g. in eager test mode); otherwise check the worker logs for the
        "debug_add(2, 3) = 5" line.
        """
        async_result = debug_add.delay(2, 3)
        self.stdout.write(f"Task sent to the broker: id={async_result.id}")

        if not getattr(settings, "CELERY_RESULT_BACKEND", None):
            self.stdout.write(
                self.style.SUCCESS(
                    "Broker reachable. No result backend configured, so check the celery "
                    "worker logs for: 'debug_add(2, 3) = 5'"
                )
            )
            return

        result = async_result.get(timeout=10)
        if result == 5:
            self.stdout.write(self.style.SUCCESS(f"Celery works! debug_add(2, 3) = {result}"))
        else:
            self.stderr.write(self.style.ERROR(f"Unexpected result: {result}"))
