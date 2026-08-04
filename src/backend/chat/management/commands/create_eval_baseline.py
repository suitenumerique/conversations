"""Mark a saved eval run as the baseline reference."""

from django.core.management.base import BaseCommand, CommandError

from chat.evals.storage import resolve_run, set_baseline


class Command(BaseCommand):
    """Create or update an eval baseline from a saved run."""

    help = "Mark a saved eval run as a baseline for future comparisons"

    def add_arguments(self, parser):
        parser.add_argument(
            "--run",
            default="latest",
            help="Saved run id to promote (default: latest).",
        )
        parser.add_argument(
            "--name",
            default="main",
            help="Baseline name (default: main).",
        )
        parser.add_argument(
            "--label",
            default=None,
            help="Optional label stored with the baseline.",
        )

    def handle(self, *args, **options):
        try:
            resolve_run(options["run"])
            baseline = set_baseline(
                run_ref=options["run"],
                baseline_name=options["name"],
                label=options["label"],
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Baseline '{baseline['name']}' set to run {baseline['run_id']} "
                f"({baseline.get('git_commit')}, {baseline.get('model_hrid')})."
            )
        )
