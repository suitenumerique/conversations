"""Django management command: run behavioral evals on ConversationAgent."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import logfire
from pydantic_evals import Dataset
from pydantic_evals.evaluators import LLMJudge
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model
from pydantic_evals.reporting import EvaluationReport

from chat.agents.base import prepare_custom_model
from chat.agents.conversation import ConversationAgent
from chat.evals import EvalInputs, EvalMetadata
from chat.evals.configs import REGISTRY
from chat.evals.configs.base import EvalConfig
from chat.evals.storage import build_run_record, dataset_result_from_report, save_run
from chat.evals.tool_output import capture_tool_output_from_run

# settings.LLM_DEFAULT_MODEL_HRID = "etalab-plateform-mistral-medium-2508"
# settings.LANGFUSE_ENABLED = False


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
            "--include-outputs",
            action="store_true",
            help="Include model outputs in saved runs (off by default).",
        )

    def handle(self, *args, **options):
        logfire.configure(send_to_logfire=False)
        logfire.instrument_pydantic_ai()

        if getattr(settings, "WARNING_MOCK_CONVERSATION_AGENT", False):
            raise CommandError(
                "WARNING_MOCK_CONVERSATION_AGENT is enabled — evals would run against "
                "the mock model, not the real LLM. Disable it before running evals."
            )

        use_llm_judge = not options["no_llm_judge"]
        self._configure_judge(use_llm_judge)

        configs = [REGISTRY[options["dataset"]]] if options["dataset"] else list(REGISTRY.values())

        self.stdout.write(f"Running evals for {configs}...\n")

        reports = [
            (config, self._run_dataset(config, options, use_llm_judge)) for config in configs
        ]
        for config, report in reports:
            self._render_report(report, options, config)

        if options["save"]:
            self._save_reports(reports, options, use_llm_judge)

    def _save_reports(self, reports, options: dict, use_llm_judge: bool) -> None:
        datasets = {
            config.name: dataset_result_from_report(
                report,
                include_outputs=options["include_outputs"],
            )
            for config, report in reports
        }
        dataset_paths = {config.name: config.dataset_path for config, _ in reports}
        params = {
            "model_hrid": settings.LLM_DEFAULT_MODEL_HRID,
            "llm_judge": use_llm_judge,
            "runs_per_case": options["runs"],
            "datasets": list(datasets.keys()),
            "case_filter": options["case"],
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
        configuration = settings.LLM_CONFIGURATIONS[settings.LLM_DEFAULT_MODEL_HRID]
        judge_model = (
            prepare_custom_model(configuration)
            if configuration.is_custom
            else configuration.model_name
        )
        set_default_judge_model(judge_model)

    def _load_dataset(self, config: EvalConfig, case_name: str | None) -> Dataset:
        custom_evaluator_types = [
            *config.dataset_evaluator_types,
            *[type(e) for e in config.extra_evaluators],
        ]
        dataset: Dataset[EvalInputs, str, EvalMetadata] = Dataset[
            EvalInputs, str, EvalMetadata
        ].from_file(
            config.dataset_path,
            custom_evaluator_types=custom_evaluator_types,
        )
        if not case_name:
            return dataset
        filtered = [c for c in dataset.cases if c.name == case_name]
        if not filtered:
            available = ", ".join(c.name for c in dataset.cases)
            raise CommandError(
                f"No case named '{case_name}' in dataset '{config.name}'. Available: {available}"
            )
        return Dataset(name=f"{config.name} ({case_name})", cases=filtered)

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

    def _run_dataset(
        self, config: EvalConfig, options: dict, use_llm_judge: bool
    ) -> EvaluationReport:
        """Run evals for a single dataset config.
        Returns True if any cases failed, else False."""
        self.stdout.write(f"\n=== Dataset: {config.name} ===\n")

        dataset = self._load_dataset(config, options["case"])
        dataset.evaluators = self._build_evaluators(config, use_llm_judge)

        if config.make_task_fn is not None:
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
                result = await _agent.run(prompt)
                if inputs.tool_output is None:
                    inputs.tool_output = capture_tool_output_from_run(result)
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
