"""Compare saved eval runs against each other or against a baseline."""

from django.core.management.base import BaseCommand, CommandError

from chat.evals.compare import compare_runs, compare_with_baseline, format_comparison
from chat.evals.storage import resolve_run


class Command(BaseCommand):
    """Compare two saved eval runs, or a run against a baseline."""

    help = "Compare saved eval runs and highlight regressions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--baseline",
            default=None,
            help="Compare --run against this baseline name (default: main when --run is set).",
        )
        parser.add_argument(
            "--run",
            default="latest",
            help="Run to compare (default: latest).",
        )
        parser.add_argument(
            "--against",
            default=None,
            help="Compare --run against this other run id instead of a baseline.",
        )
        parser.add_argument(
            "--fail-on-regression",
            action="store_true",
            help="Exit with code 1 when any case regresses.",
        )

    def handle(self, *args, **options):
        try:
            if options["against"]:
                before, _ = resolve_run(options["against"])
                after, _ = resolve_run(options["run"])
                comparison = compare_runs(before, after)
            else:
                baseline_name = options["baseline"] or "main"
                comparison = compare_with_baseline(
                    run_ref=options["run"],
                    baseline_name=baseline_name,
                )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(format_comparison(comparison))

        if options["fail_on_regression"] and comparison.has_regression_failures:
            parts: list[str] = []
            if comparison.regressions:
                parts.append(f"{len(comparison.regressions)} regression(s)")
            coverage_only = sum(1 for gap in comparison.coverage_gaps if not gap.before_passed)
            if coverage_only > 0:
                parts.append(f"{coverage_only} coverage gap(s)")
            raise CommandError(f"{' and '.join(parts)} detected compared to reference run.")
