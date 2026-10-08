# Comparing two models

Every dataset runs through `make eval` (see `README.md`, "Running evals"). Run every command from the repository root.

## Two models on the current code

```bash
make eval MODEL=mistral-medium-3-5     EVAL_ARGS='--runs 3 --save --comment "mistral-medium-3-5"'
make eval MODEL=online-mistral-large-4 EVAL_ARGS='--runs 3 --save --comment "mistral-large-4"'
```

Each run ends with `Saved eval run to /app/chat/evals/runs/<run id>.json`. Then:

```bash
make eval-compare EVAL_ARGS="--run <Large 4 run id> --against <3.5 run id>"
```

To skip a dataset (e.g. `claude_style`), run the others one by one with `--dataset <name>` and the same `--comment` prefix; `--against` compares the datasets both runs have and lists the others as not compared.

## Before you start

1. `src/backend/conversations/configuration/llm/custom_llm_configuration.json` (local, not committed) has an entry per model, with the same settings and the same `system_prompt` so only the model differs. That includes `max_token_context` (131072 for every compared model, even Large 4: it decides which documents are inlined), `web_search` (Brave) and `supports_image`. That prompt is production's inline prompt, copied word for word ("based on Mistral Medium 2508" included), not `settings.AI_AGENT_INSTRUCTIONS`. Name models explicitly with `MODEL=`: e.g. `default-model` has no `max_token_context`, so documents are not inlined for it.
2. `env.d/development/common` has the provider keys (`MISTRAL_API_KEY`, the Albert key) and `BRAVE_API_KEY` for `web_search`.
3. The judge (`LLM_EVAL_JUDGE_MODEL_HRID`) stays the same for both runs and is not a tested model.
4. Run both sides the same day, on the same code. Don't reuse older saved runs as a baseline: they used other settings or a model that has since become an alias.
5. Give every run a unique `--comment`.

## While it runs

- Each run prints `model <hrid>: requested <name>, served by <name>`, and saves the served name in the run's params. A `WARNING: the provider serves X as Y` means the provider silently answers with another model: stop and pick another model.
- Rough durations with `--runs 3`: `multi_doc_synthesis` about an hour, `claude_style` 10 min, most other datasets a few minutes. Run a full comparison detached: `nohup make eval … > eval.log 2>&1 < /dev/null &` (without `< /dev/null`, the process stops on exit on macOS).

## Reading the results

- With `--runs 3`, one repeat is 33 points: only trust differences bigger than that on a case, or seen across several cases.
- `long_chat`'s summarized cases test the summary production wrote, which lost the turn-1 rule or fact: `fait_initial` fails for every model, and the two rule cases mostly measure imitation of the recent answers.
- Deterministic checks are reliable; `LLMJudge` agrees with hand review about 90% of the time, so read its reasons (`--verbose`, or `reasons` in the saved run) before concluding on a judge-only difference.
- Saved runs live in `src/backend/chat/evals/runs/` (gitignored); copy the ones to keep into a `results/` folder.
