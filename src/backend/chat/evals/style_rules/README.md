# Style rules in project instructions: `claude_style` and `kiwi`

Do project instructions that set a writing style hold, over several turns and once a document is attached? Two datasets, run on the current code (`HEAD`, commit `1ff84e4`) with `mistral-medium-3-5` via Albert, 5 repeats per case, judge `albert-openai-gpt-oss-120b`.

- `claude_style` (`datasets/claude_style.yaml`): "write like Claude" project instructions (prose by default, lists or headings only for genuinely multiple content, no bold, no opening flattery, no closing recap), with a context sheet (`fiche-contexte-dnie`, fictional) as project document. Question: does the model drift back into bullets or bold, and how fast?
- `kiwi` (`datasets/kiwi.yaml`): style instructions forbidding lists, headings and bold, plus a witness rule: write `kiwi` alone on a line after each solution. Question: does an attachment (a transcript to summarize) make the model drop rules at random? `kiwi_sans_pj` is the no-attachment control.

Each rule is its own report column: `sans_puces`, `sans_titres`, `sans_gras`, `sans_flatterie` / `sans_formule_creuse` (`TurnsWithoutMatch`: share of turns that respect the rule, 1.0 = all; the reason lists the failing turns), `Regex` (correction mentions Nébula Cloud) and `LLMJudge`. In `kiwi`, the judges only check what a regex cannot: `kiwi_par_solution` scores the share of solutions followed by their own `kiwi` line (0–1, the reason gives the counts), `sans_recap` the closing recap; `kiwi_present` checks that at least one `kiwi` line exists. The results below predate this split (one `Regex` and one all-rules `LLMJudge` column).

## No model comparison

Mistral Medium 2508 (Medium 3.1) cannot be evaluated any more: Mistral retired it on 2026-08-31, and both Albert (`albert-mistral-medium-2508`) and Mistral's API (`online-mistral-medium-2508`) now answer requests for `mistral-medium-2508` with Mistral Medium 3.5, without error. `make eval` now prints the model that actually answers and warns on such aliases.

## Results (HEAD × mistral-medium-3-5)

Score = average over the 5 repeats. Raw runs: `results/kiwi_HEAD_3-5.json`, `results/claude_style_HEAD_3-5.json`.

### `kiwi`

| case | no bullets | no headings | no bold | `kiwi` line | no flattery | judge |
|---|---|---|---|---|---|---|
| `kiwi_sans_pj` (control) | 100% | 100% | 100% | 100% | 100% | 80% |
| `kiwi_pj_transcript` | 100% | 100% | **0%** | 100% | 100% | 0% |
| `kiwi_pj_projet` (same transcript as project document) | 100% | 100% | **0%** | 100% | 100% | 0% |
| `kiwi_pj_long_cr` (35 KB minutes) | **20%** | 80% | **0%** | 100% | 100% | 0% |
| `kiwi_pj_2_tours` (summary, then a question) | 80% | 100% | 80% | 100% | 100% | 80% |

This run used the earlier pass/fail version of the per-turn check; for these single-turn cases it gives the same values. In `kiwi_pj_2_tours` a repeat counts as failing as soon as one turn breaks the rule.

### `claude_style` (earlier version of the dataset)

These results come from the first version of the dataset (pass/fail per rule, judge on the whole rubric including formatting), since rebuilt; rerun the current version before comparing.

| case | no bullets | no headings | no bold | judge |
|---|---|---|---|---|
| 6-turn conversation | **0%**, first failure at turn 1 in every repeat | 100% | **0%**, turn 1 | 0% |
| one-turn explanation | **0%** | 20% | **0%** | 0% |
| contradiction (user wrong) | 100% | – | 80% | 0% |
| opinion, procedure | – | – | **0%** | 0% |

## Findings

1. An attachment switches bold on. Without one, the `kiwi` formatting rules hold in every repeat; with the transcript attached (to the message or to the project) no answer is bold-free. A long document brings bullets back too.
2. The `kiwi` rule is never dropped, but it is applied once rather than after each solution: the judge reports "2 solutions, 1 kiwi" in most failing answers.
3. With the `claude_style` instructions the formatting rules are not applied at all, from the first turn: there is no drift to measure. Rules given as a one-liner ("N'utilise pas de gras") or conditionally (lists "only if the content is genuinely multiple") are ignored; rules stated with explicit examples (no "Excellente question", no "n'hésitez pas") always hold.
4. Lead to investigate: the local model configuration's system prompt says "You must use Markdown to format your answers except when asked otherwise", and project instructions are appended after it without precedence.

## Caveats

- The context sheet is itself a bulleted document. The rebuilt `claude_style` runs the 6-turn conversation with and without it, and without the instructions, to separate the two effects.
- "One `kiwi` per solution" is judged (`kiwi_par_solution`), not counted by a regex.
- Judge calls that returned an invalid response (2 in `claude_style`) leave that repeat without a verdict.
- 5 repeats per case: a 20-point difference is one repeat.

## Reproduce

```bash
make eval MODEL=mistral-medium-3-5 EVAL_ARGS='--dataset kiwi --runs 5 --verbose --save --comment "kiwi local x mistral-medium-3-5"'
make eval MODEL=mistral-medium-3-5 EVAL_ARGS='--dataset claude_style --runs 5 --verbose --save --comment "claude_style local x mistral-medium-3-5"'

# Compare saved runs of a dataset (e.g. two models, or before and after a fix), rule by rule,
# then each rule and all rules averaged over the cases:
python3 src/backend/chat/evals/style_rules/compare_rules.py "kiwi local x mistral-medium-3-5" "kiwi <other run comment>"
```

`analyze_summarize_traces.py` compares Langfuse exports of the `summarize` path before and after a change (Markdown density of the summaries, how often the final answer just relays them), printing only counts and rates. Its `--sample` option prints raw trace content for local debugging: never share that output.

The results above were measured over HTTP, with an earlier runner, on a stack built from `HEAD`. `make eval` now runs the datasets in-process, with stubbed document tools (fixed summaries): rerun both sides before comparing with these results.
