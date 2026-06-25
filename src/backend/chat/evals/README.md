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
│   ├── self_documentation.py# Config for the self_documentation dataset
│   ├── faithfulness_rag.py  # Config for the RAG faithfulness dataset
│   └── incertitude.py       # Config for the uncertainty dataset
├── datasets/
│   ├── url_hallucination.yaml
│   ├── self_documentation.yaml
│   ├── faithfulness_rag.yaml
│   └── incertitude.yaml
├── evaluators/
│   ├── __init__.py
│   └── url_regex.py         # UrlRegexEvaluator — deterministic URL check
├── runs/
│   ├── index.json           # catalogue of saved runs
│   └── <timestamp>_<git>.json
├── baselines/
│   └── main.json            # pointer to the reference run
├── dashboard/
│   ├── template.html        # dashboard source (HTML/CSS/JS)
│   └── dashboard.html       # generated comparison UI
├── compare.py               # diff two saved runs
├── storage.py               # save/load runs and baselines
├── report_builder.py        # aggregate pydantic_evals reports (incl. --runs avg)
└── __init__.py              # EvalInputs, EvalMetadata Pydantic models
```

## Existing datasets

| Dataset | What it tests | Evaluators |
|---|---|---|
| `url_hallucination` | The agent never invents `http(s)://` URLs; only uses URLs from tool output | `UrlRegexEvaluator` (regex) + `LLMJudge` (semantic) |
| `self_documentation` | The `self_documentation` tool is called when and only when the user asks about the assistant itself | `HasMatchingSpan` per case (span-based) |
| `faithfulness_rag` | Answers are grounded in the retrieved chunks and add no facts beyond them | `HasMatchingSpan` (RAG tool ran) + `LLMJudge` (faithfulness) |
| `incertitude` | On high-stakes French service-public questions whose answer depends on the user's personal situation, the agent asks to clarify / defers to the competent body instead of guessing a figure, eligibility, or outcome | `LLMJudge` (uncertainty) |

## Running evals

All evals run inside Docker via `make eval`.

```bash
# Run all datasets
make eval

# Run a single dataset
make eval EVAL_ARGS="--dataset url_hallucination"
make eval EVAL_ARGS="--dataset self_documentation"

# Run a single test case by name
make eval EVAL_ARGS="--dataset url_hallucination --case easy_docs_link"

# Run each case N times (default: 1)
make eval EVAL_ARGS="--dataset self_documentation --runs 3"

# Show full model input and response in the report
make eval EVAL_ARGS="--dataset url_hallucination --verbose"

# Skip the LLM judge (use when the model endpoint does not support structured output)
make eval EVAL_ARGS="--no-llm-judge"

# Save results to the repo for later comparison (with a note on what changed)
make eval EVAL_ARGS='--save --comment "Prompt anti-hallucination URL"'

# Run each case 3 times and save averaged scores / repeat pass rates
make eval EVAL_ARGS="--dataset self_documentation --runs 3 --save"
```

### Saving runs, baselines, and comparison

Saved runs are JSON files under `chat/evals/runs/`. They store git metadata, model parameters, an optional **`--comment`**, dataset hashes, per-case **average scores**, and **repeat pass rates** when `--runs > 1`.

```bash
# 1. Run evals and save the result
make eval EVAL_ARGS="--save --runs 3 --comment baseline mistral-medium juin 2026"

# 2. Promote a saved run to the team baseline (commits baselines/main.json)
make eval-baseline
make eval-baseline EVAL_ARGS="--run 2026-06-17T14-30-00Z_a3f9c2b --label main juin 2026"

# 3. Compare the latest run against the baseline
make eval-compare
make eval-compare EVAL_ARGS="--run latest --fail-on-regression"

# 4. Compare two explicit runs
make eval-compare EVAL_ARGS="--run RUN_A --against RUN_B"

# 5. Generate / refresh the HTML dashboard
make eval-dashboard
# open src/backend/chat/evals/dashboard/dashboard.html in a browser
```

When `--runs N` is used:

- each case is executed `N` times;
- `avg_scores` stores the mean evaluator score across repeats;
- `pass_rate` stores the fraction of repeats that passed;
- `passed` is `true` only if **all** repeats passed (strict, useful for baselines).

By default, saved runs do **not** include model outputs. Use `--include-outputs` only for local debugging.

Local-only runs can be written as `runs/local_*.json` — they are gitignored.

### Debugging

```bash
# Start eval with debugpy waiting on port 5678 (blocks until VS Code attaches)
make eval-debug EVAL_ARGS="--dataset url_hallucination --case easy_docs_link"
```

Then in VS Code: **F5 → "Eval: Attach to Docker debugpy (port 5678)"**.

## Adding a new dataset

Add a dataset whenever you want to lock in a new agent behaviour: a tool that must (or must not) be called, an instruction that must be respected, an edge-case pattern. Think of it as writing a spec in executable form — if the behaviour regresses, the eval catches it.

### Step 1 — Create `datasets/<name>.yaml`

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
```

**Span-based shape** (tool-call eval, e.g. self_documentation): use per-case `HasMatchingSpan` evaluators. pydantic_ai emits a `"running tool"` span with attribute `gen_ai.tool.name` for every tool call.

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

```python
from pathlib import Path
from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import UrlRegexEvaluator  # or your custom evaluator

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "<name>.yaml"

MY_CONFIG = EvalConfig(
    name="<name>",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric="...",      # None to skip LLMJudge
    extra_evaluators=[UrlRegexEvaluator()],
    enable_tools=False,          # True = ConversationAgent with real tools
    make_task_fn=None,           # see below if you need a custom agent
)
```

### Step 3 — Register in `configs/__init__.py`

```python
from .my_config import MY_CONFIG

REGISTRY: dict[str, EvalConfig] = {
    "url_hallucination": URL_HALLUCINATION,
    "self_documentation": SELF_DOCUMENTATION,
    "<name>": MY_CONFIG,          # add here
}
```

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

- **`agent_class`** — instantiate a custom `ConversationAgent` subclass instead of the default. The runner still builds the prompt (injecting `tool_output` as context) and calls `agent.run(prompt)`. Used by `self_documentation`, which registers a no-DB stub tool alongside its instruction.
- **`make_task_fn`** — fully replace the default run logic. When set, `agent_class`, `enable_tools`, and `tool_output` prompt injection are all ignored; your factory owns how the agent is invoked.

Use `make_task_fn` when the model must *call a tool* to obtain per-case context (so a span check can confirm the tool ran) rather than receiving that context pre-injected in the prompt. `faithfulness_rag` does this: it stages each case's `tool_output` (the retrieved chunks) in a context variable so the stub `document_search_rag` tool returns them when the model calls it, while the chunks stay visible to the LLM judge via the case inputs.

```python
def make_my_task_fn(model_hrid: str):
    agent = MyCustomAgent(model_hrid=model_hrid)

    async def run_agent(inputs: EvalInputs) -> str:
        result = await agent.run(inputs.user_message)
        return result.output

    return run_agent
```

Pass it as `make_task_fn=make_my_task_fn` in the `EvalConfig`.
