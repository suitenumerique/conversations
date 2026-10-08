"""Django management command: run behavioral evals on ConversationAgent."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import logfire
import yaml
from pydantic_ai import Agent
from pydantic_evals import Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.evaluators import LLMJudge
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model
from pydantic_evals.reporting import EvaluationReport

from chat.agents.base import prepare_custom_model
from chat.agents.conversation import ConversationAgent
from chat.evals import EvalInputs, EvalMetadata
from chat.evals.configs import REGISTRY
from chat.evals.configs.base import EvalConfig, split_dataset_file
from chat.evals.report_builder import build_dataset_result
from chat.evals.served_model import report_served_model
from chat.evals.storage import build_run_record, save_run
from chat.evals.target.runtime import Target, configure_target
from chat.evals.target.wire import wire_for_tag
from chat.evals.tool_output import capture_tool_output_from_run


class _EvalAgent(ConversationAgent):
    """ConversationAgent with tools disabled for isolated eval runs."""

    def get_tools(self):
        return []


class Command(BaseCommand):
    """Run behavioral evals on ConversationAgent."""

    help = "Run behavioral evals on ConversationAgent"
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset",
            choices=list(REGISTRY),
            default=None,
            help=(f"Run only this dataset (choices: {', '.join(REGISTRY)}). Runs all if omitted."),
        )
        parser.add_argument(
            "--case",
            default=None,
            help="Run only the case with this name (e.g. --case easy_docs_link)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Include full model input and response in the report",
        )
        parser.add_argument(
            "--no-llm-judge",
            action="store_true",
            help="Skip the LLM judge evaluator "
            "(useful for models that do not support structured output)",
        )
        parser.add_argument(
            "--runs",
            type=int,
            default=1,
            help="Number of times to run each case (default: 1). Use > 1 to measure consistency.",
        )
        parser.add_argument(
            "--save",
            action="store_true",
            help="Save aggregated results to chat/evals/runs/ for later comparison.",
        )
        parser.add_argument(
            "--comment",
            default=None,
            help="Note stored with a saved run (e.g. what changed in this version).",
        )
        parser.add_argument(
            "--model",
            default=None,
            help="HRID of the model to test (default: LLM_DEFAULT_MODEL_HRID). With a "
            "git ref's stack, it must match --target-model.",
        )
        parser.add_argument(
            "--target-url",
            default=None,
            help="Base URL of a git ref's stack (e.g. http://host.docker.internal:18071): "
            "datasets run there over HTTP. Use make eval-target, which starts the stack.",
        )
        parser.add_argument(
            "--target-tag", default=None, help="Git ref the target runs (e.g. v0.0.21)."
        )
        parser.add_argument(
            "--target-model", default=None, help="LLM_DEFAULT_MODEL_HRID of the target."
        )
        parser.add_argument(
            "--include-outputs",
            action="store_true",
            help="Include model outputs in saved runs (off by default).",
        )

    def handle(self, *args, **options):
        if options["runs"] < 1:
            raise CommandError("Number of runs must be at least 1")

        self._check_save_options(options)
        target = self._resolve_target(options)
        model = self._resolve_model(options, target)
        configure_target(target)

        # Span-based evaluators (HasMatchingSpan & co) read pydantic-evals'
        # span_tree, which is only populated when a real OTel SDK tracer provider
        # is installed. logfire.configure(send_to_logfire=False) sets one up
        # locally (no network, no token); Agent.instrument_all() makes pydantic-ai
        # emit the tool-call spans those evaluators inspect.
        logfire.configure(send_to_logfire=False, console=False, service_name="evals")
        Agent.instrument_all()

        if getattr(settings, "WARNING_MOCK_CONVERSATION_AGENT", False):
            raise CommandError(
                "WARNING_MOCK_CONVERSATION_AGENT is enabled — evals would run against "
                "the mock model, not the real LLM. Disable it before running evals."
            )

        use_llm_judge = not options["no_llm_judge"]
        self._configure_judge(use_llm_judge)

        configs, skipped = self._selected_configs(options, target)
        if skipped:
            self.stdout.write(
                f"Skipping datasets that only run on the working tree: {', '.join(skipped)}\n"
            )
        where = f", target: {target.tag}" if target else ""
        self.stdout.write(
            f"Running evals for: {', '.join(config.name for config in configs)} "
            f"(model: {model}{where})\n"
        )
        served = self._report_served_model(model)

        reports = [
            (config, self._run_dataset(config, options, use_llm_judge, over_http=bool(target)))
            for config in configs
        ]
        for config, report in reports:
            self._render_report(report, options, config)

        if options["save"]:
            extra_params = {"served_model": served}
            if target:
                extra_params |= {
                    "target_version": target.tag,
                    "target_model": target.model,
                    "target_url": target.url,
                    "skipped_datasets": skipped,
                }
            self._save_reports(reports, options, use_llm_judge, extra_params=extra_params)

    @staticmethod
    def _resolve_target(options: dict) -> Target | None:
        """Build the target from --target-* options; all or none must be given."""
        values = (options["target_url"], options["target_tag"], options["target_model"])
        if not any(values):
            return None
        if not all(values):
            raise CommandError(
                "A target needs all of --target-url, --target-tag and --target-model."
            )
        try:
            wire_for_tag(options["target_tag"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        return Target(*values)

    @classmethod
    def _selected_configs(
        cls, options: dict, target: Target | None
    ) -> tuple[list[EvalConfig], list[str]]:
        """Datasets to run and those skipped, honouring --dataset, --case and the target.

        A git ref's stack is only reachable over HTTP: datasets without an HTTP task
        (stubbed tools, frozen states) need this process's own code, so they are skipped.
        """
        if options["dataset"]:
            config = REGISTRY[options["dataset"]]
            if target and config.http_task is None:
                raise CommandError(
                    f"Dataset '{config.name}' only runs on the working tree (drop --target-*)."
                )
            return [config], []
        skipped = [
            config.name for config in REGISTRY.values() if target and config.http_task is None
        ]
        configs = [config for config in REGISTRY.values() if config.name not in skipped]
        case_name = options["case"]
        if case_name:
            # Filter by case name across all datasets: run only the datasets that
            # contain it, silently skipping those where the case is absent.
            configs = [config for config in configs if case_name in cls._dataset_case_names(config)]
            if not configs:
                raise CommandError(f"No case named '{case_name}' in any dataset.")
        return configs, skipped

    @staticmethod
    def _check_save_options(options: dict) -> None:
        """--save never with --case: a run missing cases can't be compared case by case."""
        if options["save"] and options["case"]:
            raise CommandError(
                "--save cannot be combined with --case: a partial run would register every "
                "omitted case as a coverage gap (= regression) when compared."
            )

    @staticmethod
    def _resolve_model(options: dict, target: Target | None = None) -> str:
        """The tested model; it becomes the default model of this process."""
        model = options["model"] or (target.model if target else settings.LLM_DEFAULT_MODEL_HRID)
        if target and model != target.model:
            raise CommandError(
                f"--model {model} differs from --target-model {target.model}: the "
                "target stack answers with the model it was started with."
            )
        if model not in settings.LLM_CONFIGURATIONS:
            raise CommandError(f"Unknown model '{model}': not in the LLM configuration.")
        # Task factories and the judge fallback read it.
        settings.LLM_DEFAULT_MODEL_HRID = model
        return model

    def _report_served_model(self, model: str) -> str | None:
        """Print the model that really answers (providers alias names); None if unknown."""
        try:
            return report_served_model(model, write=self.stdout.write)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            self.stderr.write(self.style.WARNING(f"Could not check the served model: {error}\n"))
            return None

    def _save_reports(
        self, reports, options: dict, use_llm_judge: bool, *, extra_params: dict
    ) -> None:
        judge_model_hrid = self._resolve_judge_model_hrid()
        datasets = {
            config.name: build_dataset_result(
                report,
                include_outputs=options["include_outputs"],
            )
            for config, report in reports
        }
        dataset_paths = {config.name: config.dataset_path for config, _ in reports}
        params = {
            "model_hrid": settings.LLM_DEFAULT_MODEL_HRID,
            "judge_model_hrid": judge_model_hrid if use_llm_judge else None,
            "llm_judge": use_llm_judge,
            "runs_per_case": options["runs"],
            "datasets": list(datasets.keys()),
            "case_filter": options["case"],
            **extra_params,
        }
        record = build_run_record(
            datasets=datasets,
            params=params,
            comment=options["comment"],
            dataset_paths=dataset_paths,
        )
        run_path = save_run(record)
        note = f' — "{options["comment"]}"' if options["comment"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\nSaved eval run to {run_path}{note} "
                f"(overall pass rate: {record['summary']['overall_pass_rate']:.0%}, "
                f"runs/case: {options['runs']})\n"
            )
        )

    def _configure_judge(self, use_llm_judge: bool) -> None:
        if not use_llm_judge:
            return
        judge_model_hrid = self._resolve_judge_model_hrid()
        if judge_model_hrid == settings.LLM_DEFAULT_MODEL_HRID:
            self.stderr.write(
                self.style.WARNING(
                    f"⚠  Judge model == tested model ('{judge_model_hrid}'): LLMJudge scores "
                    "are subject to self-grading bias. Set LLM_EVAL_JUDGE_MODEL_HRID to a "
                    "different model for more reliable judgments."
                )
            )
        configuration = settings.LLM_CONFIGURATIONS[judge_model_hrid]
        judge_model = (
            prepare_custom_model(configuration)
            if configuration.is_custom
            else configuration.model_name
        )
        set_default_judge_model(judge_model)

    def _resolve_judge_model_hrid(self) -> str:
        configured_judge = (settings.LLM_EVAL_JUDGE_MODEL_HRID or "").strip()
        judge_model_hrid = configured_judge or settings.LLM_DEFAULT_MODEL_HRID
        if judge_model_hrid not in settings.LLM_CONFIGURATIONS:
            raise CommandError(
                "Invalid eval judge model "
                f"'{judge_model_hrid}' (set via LLM_EVAL_JUDGE_MODEL_HRID)."
            )
        return judge_model_hrid

    @staticmethod
    def _dataset_case_names(config: EvalConfig) -> set[str]:
        """Return the case names declared in a dataset's YAML (cheap, no Dataset build)."""
        _, dataset_data = split_dataset_file(config.dataset_path)
        return {case["name"] for case in dataset_data.get("cases", []) if "name" in case}

    def _load_dataset(self, config: EvalConfig, case_name: str | None) -> Dataset:
        custom_evaluator_types = [
            *config.dataset_evaluator_types,
            *[type(e) for e in config.extra_evaluators],
        ]
        # The optional top-level `config` block (rubric, evaluator paths) is
        # ours, not pydantic_evals': strip it before parsing the dataset.
        _, dataset_data = split_dataset_file(config.dataset_path)
        dataset: Dataset[EvalInputs, str, EvalMetadata] = Dataset[
            EvalInputs, str, EvalMetadata
        ].from_text(
            yaml.safe_dump(dataset_data, sort_keys=False, allow_unicode=True),
            fmt="yaml",
            custom_evaluator_types=custom_evaluator_types,
            default_name=config.dataset_path.stem,
        )
        if not case_name:
            return dataset
        filtered = [c for c in dataset.cases if c.name == case_name]
        if not filtered:
            available = ", ".join(c.name for c in dataset.cases)
            raise CommandError(
                f"No case named '{case_name}' in dataset '{config.name}'. Available: {available}"
            )
        return Dataset(
            name=f"{config.name} ({case_name})",
            cases=filtered,
            evaluators=dataset.evaluators,
        )

    def _build_evaluators(self, config: EvalConfig, use_llm_judge: bool) -> list:
        evaluators = list(config.extra_evaluators)
        if use_llm_judge and config.llm_judge_rubric:
            evaluators.append(
                LLMJudge(
                    rubric=config.llm_judge_rubric,
                    include_input=True,
                    assertion={"include_reason": True},
                )
            )
        return evaluators

    @staticmethod
    def _without_llm_judges(dataset: Dataset) -> None:
        """Drop every LLMJudge declared in the YAML, dataset-level and per-case."""

        def keep(evaluators):
            return [evaluator for evaluator in evaluators if not isinstance(evaluator, LLMJudge)]

        dataset.evaluators = keep(dataset.evaluators)
        for case in dataset.cases:
            case.evaluators = keep(case.evaluators)

    def _run_dataset(
        self, config: EvalConfig, options: dict, use_llm_judge: bool, *, over_http: bool = False
    ) -> EvaluationReport:
        """Run evals for a single dataset config and return its evaluation report."""
        self.stdout.write(f"\n=== Dataset: {config.name} ===\n")

        dataset = self._load_dataset(config, options["case"])
        if not use_llm_judge:
            self._without_llm_judges(dataset)
        # Extend (not replace): keep dataset-level evaluators declared in the YAML.
        dataset.evaluators = [*dataset.evaluators, *self._build_evaluators(config, use_llm_judge)]

        if over_http:
            run_agent = config.http_task(settings.LLM_DEFAULT_MODEL_HRID)
        elif config.make_task_fn is not None:
            run_agent = config.make_task_fn(settings.LLM_DEFAULT_MODEL_HRID)
        else:
            agent_cls = config.agent_class or (
                ConversationAgent if config.enable_tools else _EvalAgent
            )
            agent = agent_cls(model_hrid=settings.LLM_DEFAULT_MODEL_HRID)

            async def run_agent(inputs: EvalInputs, *, _agent=agent) -> str:
                prompt = inputs.user_message
                if inputs.tool_output:
                    prompt = (
                        f"[Tool output]\n{inputs.tool_output}\n\n"
                        f"[User question]\n{inputs.user_message}"
                    )
                # message_history=[] keeps each case isolated: the eval session
                # reuses one conversation, so never replay a prior case's turns.
                result = await _agent.run(prompt, message_history=[])
                if inputs.tool_output is None:
                    # Expose runtime tool returns to evaluators (e.g. UrlRegexEvaluator)
                    # via task-run attributes. Never mutate `inputs`: the same case
                    # object is reused across --runs repeats.
                    captured = capture_tool_output_from_run(result)
                    if captured:
                        set_eval_attribute("tool_output", captured)
                return result.output

        report = dataset.evaluate_sync(
            run_agent, max_concurrency=1, repeat=options["runs"], progress=False
        )
        return report

    def _render_report(self, report: EvaluationReport, options: dict, config: EvalConfig) -> None:
        uses_tools = config.enable_tools or config.make_task_fn is not None
        self.stdout.write(
            report.render(
                include_input=options["verbose"] or uses_tools,
                include_output=options["verbose"],
                include_reasons=options["verbose"],
            )
        )

        if report.failures:
            self.stderr.write(
                f"  ⚠  {len(report.failures)} task(s) failed to execute "
                f"(infrastructure/exception errors — not model regressions)\n"
            )
