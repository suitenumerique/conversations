# Behavioral Evals

Evals are behavioral tests that verify the Agent acts correctly in specific situations. They are not unit tests of Python logic — they test **LLM behaviour**: does the model call the right tool? Does it respect a system instruction? Does it avoid a known bad pattern?

A failing eval means the model (or a change to its configuration, instructions, or tools) has regressed on a documented behaviour. Think of evals as executable specifications for how the agent should behave.

## Structure

```text
chat/evals/
├── configs/
│   ├── __init__.py          # REGISTRY — maps dataset name → EvalConfig
│   ├── base.py              # EvalConfig dataclass
│   ├── url_hallucination.py # Config for the URL hallucination dataset
│   ├── faithfulness_rag.py  # Config for the RAG faithfulness dataset
│   ├── incertitude.py       # Config for the uncertainty dataset
│   ├── tool_selection.py    # Config for the tool selection dataset
│   └── conversation.py      # Configs for the conversation datasets (in_process.py)
├── datasets/
│   ├── url_hallucination.yaml
│   ├── faithfulness_rag.yaml
│   ├── incertitude.yaml
│   ├── tool_selection.yaml
│   ├── chat_instructions.yaml, web_search.yaml, multi_doc_synthesis.yaml,
│   │   project_instructions.yaml, long_chat.yaml, kiwi.yaml, claude_style.yaml
│   └── multi_doc_synthesis/ # fixture documents (<name>.md) and their fixed summaries (<name>.summary.md)
├── evaluators/
│   ├── __init__.py          # CUSTOM_EVALUATOR_TYPES — every evaluator a YAML may name
│   ├── url_regex.py         # UrlRegexEvaluator, UrlCount — URL checks
│   ├── span.py              # HasNoMatchingSpan — "tool was NOT called" check
│   ├── text_checks.py       # Regex, Language, FactRecall, MaxWords, TurnsWithoutMatch, …
│   └── tools_used.py        # ToolsUsed (label), ToolCalled, ToolNotCalled, SourcesCount
├── runs/
│   ├── index.json           # catalogue of saved runs
│   └── <timestamp>_<git>.json
├── baselines/
│   ├── main.json            # baseline metadata (committed)
│   └── main_run.json        # full baseline run snapshot (committed)
├── dashboard/
│   ├── template.html        # dashboard source (HTML/CSS/JS)
│   └── dashboard.html       # generated comparison UI (gitignored)
├── compare.py               # diff two saved runs
├── storage.py               # save/load runs and baselines
├── report_builder.py        # aggregate pydantic_evals reports (incl. --runs avg)
├── dashboard.py             # generate the self-contained HTML dashboard
├── production_agent.py      # production-shaped agent wiring with stubbable tools
├── in_process.py            # runs a case like a production conversation (documents, projects, history)
├── tool_stub_responses.py   # per-case simulated tool payloads (contextvar staging)
├── tool_output.py           # capture runtime tool returns from an agent run
└── __init__.py              # EvalInputs, EvalMetadata Pydantic models

Management commands (under `chat/management/commands/`):

- `run_evals` — run datasets (`make eval`)
- `create_eval_baseline` — promote a run (`make eval-baseline`)
- `compare_evals` — CLI diff (`make eval-compare`)
- `generate_eval_dashboard` — build HTML (`make eval-dashboard`)
- `reset_evals` — wipe local artifacts (`make eval-reset`)
```

## Existing datasets

| Dataset | What it tests | Evaluators |
|---|---|---|
| `url_hallucination` | The agent never invents `http(s)://` URLs; only uses URLs from tool output or user message | `UrlRegexEvaluator` (regex) + `LLMJudge` (semantic) |
| `faithfulness_rag` | Answers are grounded in the retrieved chunks and add no facts beyond them | `HasMatchingSpan` (RAG tool ran) + `HasNoMatchingSpan` (no web search) + `LLMJudge` (faithfulness) |
| `incertitude` | On high-stakes French service-public questions whose answer depends on the user's personal situation, the agent asks to clarify / defers to the competent body instead of guessing a figure, eligibility, or outcome | `LLMJudge` (uncertainty) |
| `tool_selection` | The agent calls the right tool (`web_search`, `self_documentation`, `document_search_rag`, `summarize`) or none, including adversarial French phrasing | `HasMatchingSpan` / `HasNoMatchingSpan` per case |
| `chat_instructions` | Writing, rewording and format instructions in a conversation without documents, single and multi-turn | Deterministic checks per case (`Regex`, `MaxWords`, `Language`, …) + `LLMJudge` when not checkable mechanically |
| `web_search` | With smart web search on: deciding to search, citing sources, respecting the format (no facts graded: the web changes) | `ToolCalled` / `ToolNotCalled`, `SourcesCount`, `UrlCount`, `UrlRegexEvaluator` |
| `multi_doc_synthesis` | Synthesis instructions on attached meeting minutes, short set (all inlined) and long set (partly tool-call only) | `FactRecall`, format checks + `LLMJudge` per case |
| `project_instructions` | Project instructions and project files (always tool-call only) | `FactRecall`, `Language`, format checks |
| `long_chat` | A rule or fact given before the history was summarized, from the state production leaves after summarizing | `Language`, `Regex`, `FactRecall` |
| `kiwi` | A test rule in project instructions ("kiwi" after each solution), with and without an attachment to summarize | `Regex`, `TurnsWithoutMatch` per style rule + `LLMJudge` |
| `claude_style` | Style rules from project instructions, with a context sheet as project file, over a 6-turn conversation | `TurnsWithoutMatch` (share of compliant turns) + `LLMJudge` |

`ToolsUsed` only labels a case with the tools its scored turn called; it never passes or fails it.

RAG/summarize cases set `inputs.requires_documents: true`, which injects a fake document listing (same JSON shape as production) so those tools are visible to the model. Optional `inputs.tool_output` JSON can stage per-case simulated tool payloads (`web_search`, `document_search_rag`, `summarize`) for multi-tool flows — see `evals/tool_stub_responses.py`. Use `--runs 3` on medium/hard cases to measure robustness on ambiguous phrasing.

## Running evals

All evals run inside Docker via `make eval`.

```bash
# Run all datasets
make eval

# Run a single dataset
make eval EVAL_ARGS="--dataset url_hallucination"
make eval EVAL_ARGS="--dataset tool_selection"

# Run a single test case by name (not combinable with --save)
make eval EVAL_ARGS="--dataset url_hallucination --case easy_docs_link"

# Run each case N times (default: 1)
make eval EVAL_ARGS="--dataset tool_selection --runs 3"

# Show full model input and response in the report
make eval EVAL_ARGS="--dataset url_hallucination --verbose"

# Skip the LLM judge (use when the model endpoint does not support structured output)
make eval EVAL_ARGS="--no-llm-judge"

# Save results to the repo for later comparison (with a note on what changed)
make eval EVAL_ARGS='--save --comment "Prompt anti-hallucination URL"'

# Run each case 3 times and save averaged scores / repeat pass rates
make eval EVAL_ARGS="--runs 3 --save"
```

`--save` refuses to run with `--case`: a partial run compared against the baseline
would report every other case as a coverage gap (= regression).

`--save` **is** allowed with `--dataset`: the saved run then only contains that
dataset. Comparing it against the full baseline reports every other dataset as
coverage gaps (= regressions with `--fail-on-regression`), so use such runs for
run-vs-run diffs (`--against`) rather than baseline comparison.

For a long run in the background, redirect stdin, or the process stops on exit on macOS:
`nohup make eval EVAL_ARGS="--runs 3 --save" > eval.log 2>&1 < /dev/null &`.

Model selection:
- tested model = `LLM_DEFAULT_MODEL_HRID`
- judge model = `LLM_EVAL_JUDGE_MODEL_HRID` (falls back to `LLM_DEFAULT_MODEL_HRID` if empty;
  a warning is printed when judge == tested model, since self-grading is biased)

### Saving runs, baselines, and comparison

Saved runs are JSON files under `chat/evals/runs/`. They store git metadata, model parameters, an optional **`--comment`**, dataset hashes, per-case **average scores**, and **repeat pass rates** when `--runs > 1`. The `overall_pass_rate` is weighted by case count (total cases passed / total cases), so small datasets don't weigh as much as large ones.

```bash
# 1. Run evals and save the result
make eval EVAL_ARGS='--save --runs 3 --comment "baseline mistral-medium juin 2026"'

# 2. Promote a saved run to the team baseline (commits baselines/main.json + baselines/main_run.json)
make eval-baseline
make eval-baseline EVAL_ARGS='--run 2026-06-17T14-30-00Z_a3f9c2b --name main --label "juin 2026"'

# 3. Compare the latest run against the baseline
make eval-compare
make eval-compare EVAL_ARGS="--run latest --fail-on-regression"
make eval-compare EVAL_ARGS="--baseline main --run latest"   # explicit baseline name

# 4. Compare two explicit runs
make eval-compare EVAL_ARGS="--run RUN_B --against RUN_A"

# 5. Generate / refresh the HTML dashboard
make eval-dashboard
# open src/backend/chat/evals/dashboard/dashboard.html in a browser

# 6. Wipe saved runs, baselines, and dashboard to start fresh
make eval-reset
make eval-reset EVAL_ARGS="--keep-baselines"   # runs + dashboard only
make eval-reset EVAL_ARGS="--keep-dashboard"   # keep generated dashboard.html
make eval-reset EVAL_ARGS="--dry-run"          # preview without deleting
```

`compare_evals` treats a case present in the reference run but missing from the
candidate as a **coverage gap** (counts as a regression with `--fail-on-regression`).
The HTML dashboard uses the same rules.

The dashboard is a self-contained HTML file: pick runs A/B, see a per-dataset pass
rate summary (including total), filter by dataset/case/changes only, and drill
into per-case deltas. It embeds the latest 20 saved runs plus any baseline runs
(see `DASHBOARD_MAX_RUNS` in `dashboard.py`). Dataset and case descriptions come
from YAML header comments and `metadata.description`.

When `--runs N` is used:

- each case is executed `N` times;
- `avg_scores` stores the mean evaluator score across repeats;
- `pass_rate` stores the fraction of repeats that passed;
- `passed` is `true` only if **all** repeats passed (strict, useful for baselines).
- a case with no exploitable evaluator score is treated as **failed** (not silently passed).

By default, saved runs do **not** include model outputs. Use `--include-outputs` only for local debugging.

Saved runs under `chat/evals/runs/` are **gitignored** (local experiments). Only baseline snapshots under `chat/evals/baselines/` are committed (`main.json` metadata + `main_run.json` full record).

### Debugging

```bash
# Start eval with debugpy waiting on port 5678 (blocks until VS Code attaches)
make eval-debug EVAL_ARGS="--dataset url_hallucination --case easy_docs_link"
```

Then in VS Code: **F5 → "Eval: Attach to Docker debugpy (port 5678)"**.

## Adding a new dataset

Add a dataset whenever you want to lock in a new agent behaviour: a tool that must (or must not) be called, an instruction that must be respected, an edge-case pattern. Think of it as writing a spec in executable form — if the behaviour regresses, the eval catches it.

### Step 1 — Create `datasets/<name>.yaml`

The YAML holds the declarative config **and** the cases. An optional top-level
`config` block carries the LLM judge rubric and dataset-level evaluators
(referenced by dotted path — an `Evaluator` instance is used as-is, a class is
instantiated without arguments):

```yaml
config:
  llm_judge_rubric: |          # omit to skip LLMJudge
    You are evaluating whether ...
  extra_evaluators:
    - chat.evals.evaluators.UrlRegexEvaluator        # class → instantiated
    - chat.evals.configs.my_config.MY_SPAN_CHECK     # instance → used as-is
```

Each case needs `inputs` (at minimum `user_message`), optional `metadata`, and either dataset-level or per-case `evaluators`.

**Standard shape** (text-output eval, e.g. url_hallucination):

```yaml
cases:
  - name: easy_no_url
    inputs:
      user_message: "Where is the Django docs?"
      tool_output: null          # optional — injected as context before the question
    metadata:
      difficulty: easy           # easy | medium | hard
      category: no_context       # free-form string, used for filtering/reporting
      description: optional      # shown as a tooltip in the HTML dashboard
```

**Span-based shape** (tool-call eval, e.g. tool_selection): use per-case `HasMatchingSpan` / `HasNoMatchingSpan` evaluators. pydantic_ai emits a `"running tool"` span with attribute `gen_ai.tool.name` for every tool call.

```yaml
cases:
  - name: about_capabilities
    inputs:
      user_message: "What can you do?"
    metadata:
      difficulty: easy
      category: about_self
    evaluators:
      - HasMatchingSpan:
          query:
            has_attributes:
              gen_ai.tool.name: "my_tool"
          evaluation_name: called_my_tool

  - name: capital_of_france
    inputs:
      user_message: "What is the capital of France?"
    metadata:
      difficulty: easy
      category: about_other
    evaluators:
      - HasNoMatchingSpan:
          query:
            has_attributes:
              gen_ai.tool.name: "my_tool"
          evaluation_name: did_not_call_my_tool
```

### Step 2 — Create `configs/<name>.py`

The Python config only wires the executable parts (rubric and evaluators come
from the YAML `config` block):

```python
from pathlib import Path
from chat.evals.configs.base import EvalConfig

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "<name>.yaml"

MY_CONFIG = EvalConfig(
    name="<name>",
    dataset_path=_DATASET_PATH,
    enable_tools=False,  # True = ConversationAgent with real tools
    make_task_fn=None,  # see below if you need a custom agent
    dataset_evaluator_types=[],  # span evaluator types used in per-case YAML
)
```

Per-case evaluators declared in the YAML are **merged** with the dataset-level
ones (`config.extra_evaluators` + optional `LLMJudge`), not replaced.

### Step 3 — Register in `configs/__init__.py`

```python
from .faithfulness_rag import FAITHFULNESS_RAG
from .incertitude import INCERTITUDE
from .my_config import MY_CONFIG
from .tool_selection import TOOL_SELECTION
from .url_hallucination import URL_HALLUCINATION

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "faithfulness_rag": FAITHFULNESS_RAG,
    "incertitude": INCERTITUDE,
    "tool_selection": TOOL_SELECTION,
    "<name>": MY_CONFIG,  # add here
}
```

### Conversation datasets

The seven datasets in `configs/conversation.py` run each case the way production
runs a conversation turn (`in_process.py`), with the tested model and no HTTP:

- **Agent**: a fresh `AIAgentService` per case, built like production (prompt,
  tools, language `fr-fr`). Its unsaved conversation carries the case's project
  and history summary, so production's own setup injects the project
  instructions and the summary.
- **Documents**: `attachments` and `project_attachments` name fixtures in
  `datasets/multi_doc_synthesis/`. The document listing is production's
  (`build_documents_listing`): attachments are inlined while they fit the
  model's `max_token_context` budget, project files are always tool-call only.
- **Stubbed tools**: `document_search_rag` returns the full text of the
  documents not inlined (or of the one `document_id` names), more than a real
  top-k search would; `summarize` / `summarize_project` return the fixed
  `<name>.summary.md` of each document in scope, whatever `instructions` the
  model passes. Web search is the real tool when the dataset turns smart search
  on (`web_search` only), and absent otherwise, as by default in production.
- **Turns**: `user_message`, then each `follow_ups` entry, in the same
  conversation; only the last answer is scored. Evaluators can read the
  `tool_calls`, `sources` and `tool_output` of the scored turn and every turn's
  answer (`turn_texts`). The run records each document's `access` (`documents`):
  which ones are inlined depends on the tested model's `max_token_context`.

Inputs these datasets use:

```yaml
inputs:
  user_message: "Résume ces comptes rendus."
  follow_ups: ["Ajoute les échéances."]        # later turns
  attachments: [court-cr-01, court-cr-02]      # fixture names, without .md
  project_instructions: "Réponds en anglais."  # the case runs in a project
  project_attachments: [fiche-contexte-dnie]
  history_summary: "…"                         # stored summary of earlier turns
  message_history:                             # messages kept after the summary
    - {role: user, content: "Voici :\n\n{{paste:long-cr-01}}"}  # fixture text pasted
    - {role: assistant, content: "…"}
```

Every attached fixture needs a `<name>.summary.md` (a test checks it). To add a
conversation dataset, write its YAML and add one line to `configs/conversation.py`
and `configs/__init__.py`.

`long_chat` freezes conversations after production summarized their history: its
`history_summary` values were generated once with `generate_history_summary`
(the summarization model) and copied verbatim, and `message_history` holds the
turns `build_active_history` keeps. Production's summaries dropped the turn-1
rule or fact in all three cases, so `fait_initial` cannot pass until the
summarizer keeps it.

## Custom evaluators

Subclass `pydantic_evals.evaluators.Evaluator`, implement `evaluate(ctx) -> EvaluationReason`, then export from `evaluators/__init__.py`:

```python
# evaluators/my_check.py
from dataclasses import dataclass
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.evaluators.evaluator import EvaluationReason


@dataclass(repr=False)
class MyEvaluator(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        passed = ...  # inspect ctx.output, ctx.inputs, ctx.expected_output
        return EvaluationReason(value=passed, reason="explanation if failed")
```

## Custom agents and task functions

Two `EvalConfig` hooks let you control how the agent is built and invoked:

- **`agent_class`** — instantiate a custom `ConversationAgent` subclass instead of the default. The runner still builds the prompt (injecting `tool_output` as context) and calls `agent.run(prompt)`. Useful to register a stub tool alongside its instruction without replacing the run logic.
- **`make_task_fn`** — fully replace the default run logic. When set, `agent_class`, `enable_tools`, and `tool_output` prompt injection are all ignored; your factory owns how the agent is invoked.

Use `make_task_fn` when the model must *call a tool* to obtain per-case context (so a span check can confirm the tool ran) rather than receiving that context pre-injected in the prompt. `faithfulness_rag` and `tool_selection` do this via `tool_stub_responses.py`: each case's `tool_output` is staged in a context variable so stub tools return the right payload when the model calls them. The chunks stay visible to the LLM judge via the case inputs (`include_input=True`).

```python
def make_my_task_fn(model_hrid: str):
    agent = MyCustomAgent(model_hrid=model_hrid)

    async def run_agent(inputs: EvalInputs) -> str:
        result = await agent.run(inputs.user_message)
        return result.output

    return run_agent
```

Pass it as `make_task_fn=make_my_task_fn` in the `EvalConfig`.
