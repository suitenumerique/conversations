# History Processor (Sliding Window)

When a conversation grows long enough to exceed the model's context window, the backend automatically trims the oldest turns before each agent call. The full history is always preserved in the database — only the slice sent to the model is reduced.

## How it works

Before each agent call, `apply_sliding_window` checks whether the estimated token count of the history exceeds the conversation budget. If it does, it removes the oldest complete turns one by one until the history fits, then passes the trimmed slice to the model.

A **turn** is the unit of trimming: a user message plus all the model responses and tool call/return pairs that follow it, up to the next user message. Turns are never split — either the whole turn is kept or the whole turn is dropped.

The last turn is always kept, even if it alone exceeds the budget. This guarantees the current user message is never lost.

```text
Full history:   [turn 1] [turn 2] [turn 3] [turn 4]  ← exceeds budget
After trim:                        [turn 3] [turn 4]  ← fits within budget
Database:       [turn 1] [turn 2] [turn 3] [turn 4]  ← untouched
```

When trimming occurs, the backend emits a `context_trimmed` SSE event and the frontend displays a notice (session-only — resets on page reload):

> *Some older messages are no longer in the model's context.*

## Configuration

Trimming is enabled by setting `max_token_context` on a model in the LLM configuration file:

```json
{
  "hrid": "default-model",
  "max_token_context": 128000,
  ...
}
```

If `max_token_context` is absent or `null` on the model configuration, it falls back to the `DEFAULT_MAX_TOKEN_CONTEXT` setting (default 8192). Set `DEFAULT_MAX_TOKEN_CONTEXT=0` in settings to disable trimming for models without an explicit context limit.

### Misconfiguration warning

If the computed conversation budget is 0 (e.g. `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS` exceeds the available tokens, or `DOCUMENT_CONTEXT_BUDGET_RATIO` is 1.0), trimming is disabled and the backend logs a warning:

```
Sliding window disabled: conversation budget is 0
(max_token_context=N, security_buffer=M, budget_ratio=R).
```

### Budget formula

The conversation budget is derived from two Django settings:

| Setting | Description | Default |
|---|---|---|
| `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS` | Tokens reserved as a safety margin per pool | `1000` |
| `DOCUMENT_CONTEXT_BUDGET_RATIO` | Fraction of the usable window allocated to documents | `0.5` |

```text
conversation_budget = int(max_token_context × (1 - DOCUMENT_CONTEXT_BUDGET_RATIO)) - DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS
```

The security buffer is subtracted from **both** the conversation pool and the document pool independently — each pool's token count is approximated, so each pool needs its own safety margin.

For example, with `max_token_context=128000`, `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS=1000`, and `DOCUMENT_CONTEXT_BUDGET_RATIO=0.3`:

```
conversation_budget = int(128000 × 0.7) - 1000 = 88600 tokens
```

## Token estimation

Tokens are estimated without calling the model's tokenizer, using tiktoken (`cl100k_base`). This is intentionally rough — the goal is to stay well within the context limit, not to maximise usage. Each message also carries a small fixed overhead (4 tokens per part + 4 per message) to account for role markers and formatting.

**Images** are counted using a flat constant of 1 500 tokens per image part (`ImageUrl` or `BinaryContent` with an `image/*` MIME type). Precise estimation is model-specific (OpenAI uses tile math, Anthropic uses a different formula), so a conservative constant keeps the estimator model-agnostic.

**System prompt** tokens are subtracted from the conversation budget at calculation time using the static `configuration.system_prompt` string. Dynamic content injected at runtime (e.g. inlined document context) is not counted here — the security buffer absorbs that drift.

**Agent instructions** (tool schemas, pydantic-ai framework overhead) are not counted. The security buffer is the backstop.

## Local testing

To trigger trimming locally, set a small `max_token_context` on the default model:

```json
"max_token_context": 500
```

After ~10 short messages the banner should appear and the chat should continue to work normally.
