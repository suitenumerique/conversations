"""Generate the static eval runs dashboard."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from chat.evals.dashboard import generate_dashboard


class Command(BaseCommand):
    """Generate a self-contained HTML dashboard for saved eval runs."""

    help = "Generate the eval runs dashboard HTML file"

    def handle(self, *args, **options):
        output_path = generate_dashboard()
        # The command runs inside Docker where BASE_DIR is /app; show the
        # host-side path (repo checkout) so the user can open the file directly.
        # Outside that layout output_path may not be under BASE_DIR — the file is
        # already written, so fall back to the absolute path rather than crash.
        try:
            display_path = Path("src/backend") / output_path.relative_to(settings.BASE_DIR)
        except ValueError:
            display_path = output_path
        self.stdout.write(
            self.style.SUCCESS(
                f"Dashboard written to {display_path}. Open it in a browser to compare runs."
            )
        )
