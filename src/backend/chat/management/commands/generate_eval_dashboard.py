"""Generate the static eval runs dashboard."""

from django.core.management.base import BaseCommand

from chat.evals.dashboard import generate_dashboard


class Command(BaseCommand):
    """Generate a self-contained HTML dashboard for saved eval runs."""

    help = "Generate the eval runs dashboard HTML file"

    def handle(self, *args, **options):
        output_path = generate_dashboard()
        self.stdout.write(
            self.style.SUCCESS(
                f"Dashboard written to {output_path}. Open it in a browser to compare runs."
            )
        )
