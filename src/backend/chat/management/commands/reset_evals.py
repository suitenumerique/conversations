"""Delete saved eval runs, baselines, and dashboard artifacts."""

from django.core.management.base import BaseCommand

from chat.evals.storage import BASELINES_DIR, DASHBOARD_DIR, RUNS_DIR, reset_eval_artifacts


class Command(BaseCommand):
    """Reset local eval history to start fresh."""

    help = "Delete saved eval runs, baselines, and generated dashboard HTML"

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-baselines",
            action="store_true",
            help="Keep committed baseline snapshots under chat/evals/baselines/.",
        )
        parser.add_argument(
            "--keep-dashboard",
            action="store_true",
            help="Keep chat/evals/dashboard/dashboard.html.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be deleted without removing files.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self._print_dry_run(
                runs=True,
                baselines=not options["keep_baselines"],
                dashboard=not options["keep_dashboard"],
            )
            return

        deleted = reset_eval_artifacts(
            runs=True,
            baselines=not options["keep_baselines"],
            dashboard=not options["keep_dashboard"],
        )
        self._print_deleted(deleted)

    def _print_dry_run(self, *, runs: bool, baselines: bool, dashboard: bool) -> None:

        targets: list[str] = []
        if runs:
            targets.extend(
                str(path.relative_to(RUNS_DIR.parent))
                for path in sorted(RUNS_DIR.glob("*.json"))
                if path.name != "index.json"
            )
            targets.append(str((RUNS_DIR / "index.json").relative_to(RUNS_DIR.parent)))
        if baselines:
            targets.extend(
                str(path.relative_to(BASELINES_DIR.parent))
                for path in sorted(BASELINES_DIR.glob("*.json"))
            )
        if dashboard:
            dashboard_path = DASHBOARD_DIR / "dashboard.html"
            if dashboard_path.exists():
                targets.append(str(dashboard_path.relative_to(DASHBOARD_DIR.parent)))

        if not targets:
            self.stdout.write("Nothing to delete.")
            return

        self.stdout.write("Would delete:")
        for target in targets:
            self.stdout.write(f"  - {target}")

    def _print_deleted(self, deleted: dict[str, list[str]]) -> None:
        total = sum(len(items) for items in deleted.values())
        if total == 0:
            self.stdout.write(self.style.WARNING("Nothing to delete — eval storage already empty."))
            return

        for category, names in deleted.items():
            if not names:
                continue
            self.stdout.write(self.style.SUCCESS(f"{category}:"))
            for name in names:
                self.stdout.write(f"  - {name}")

        self.stdout.write(self.style.SUCCESS(f"\nEval reset complete ({total} file(s) removed)."))
