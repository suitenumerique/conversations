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
│   └── self_documentation.py# Config for the self_documentation dataset
├── datasets/
│   ├── url_hallucination.yaml
│   └── self_documentation.yaml
├── evaluators/
│   ├── __init__.py
│   └── url_regex.py         # UrlRegexEvaluator — deterministic URL check
└── __init__.py              # EvalInputs, EvalMetadata Pydantic models
```

## Existing datasets

| Dataset | What it tests | Evaluators |
|---|---|---|
| `url_hallucination` | The agent never invents `http(s)://` URLs; only uses URLs from tool output | `UrlRegexEvaluator` (regex) + `LLMJudge` (semantic) |
| `self_documentation` | The `self_documentation` tool is called when and only when the user asks about the assistant itself | `HasMatchingSpan` per case (span-based) |

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
```

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
            name_equals: "running tool"
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
      - HasMatchingSpan:
          query:
            not_:
              name_equals: "running tool"
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

## `make_task_fn` — custom task functions

By default the eval runner calls `agent.run(user_message)` and returns the text output. Use `make_task_fn` when you need a custom agent class — for example, `self_documentation` uses a stub agent that registers a no-DB version of the tool alongside its instruction:

```python
def make_my_task_fn(model_hrid: str):
    agent = MyCustomAgent(model_hrid=model_hrid)

    async def run_agent(inputs: EvalInputs) -> str:
        result = await agent.run(inputs.user_message)
        return result.output

    return run_agent
```

Pass it as `make_task_fn=make_my_task_fn` in the `EvalConfig`.
