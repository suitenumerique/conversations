# History Processing (Conversation Summarization)

When a conversation grows long enough to exceed its token budget, the backend summarizes the oldest turns instead of sending them verbatim to the model. The full history is always preserved in the database — only the slice sent to the model is reduced, with a running summary standing in for the summarized prefix.

## How it works

At the start of each user turn — before `agent.iter` — `maybe_summarize_history` (`chat/agents/history_processors.py`) checks whether the estimated token count of the **active history** (the messages after the last summary checkpoint, plus a small retained window before it) exceeds the conversation budget.

If it does, a dedicated summarization agent (`LLM_SUMMARIZATION_MODEL_HRID`) folds the un-summarized messages into the previous summary and the result is persisted on the conversation:

- `history_summary` — the running summary text, injected into the model's dynamic instructions.
- `history_summary_checkpoint` — the message index up to which the summary is valid.

The model then receives the summary plus the last `CONVERSATION_SUMMARY_CONTEXT_MESSAGES` `ModelMessage` entries before the checkpoint, so recent detail is kept verbatim. Use an **even** value so the retained window starts on a user message.

```text
Full history:   [msg 1 … msg 20] [msg 21 … msg 30]   ← exceeds budget
Sent to model:  [summary of 1–20] [msg 21 … msg 30]  ← fits within budget
Database:       [msg 1 … msg 30] + summary           ← history untouched
```

Summarization is **incremental**: later turns only summarize messages added since the last checkpoint, folding them into the existing summary.

While the summarization call runs, the backend emits a `summarize` tool-call event so the frontend can show a "Summarizing conversation..." notice; the matching tool-result event reports `done` (checkpoint advanced) or `error` (summary kept as-is, retried on a later turn).

Independently of summarization, old tool returns are compacted on every turn (`clean_tool_history`): only the latest tool cycle keeps its full tool responses, older ones are replaced with a `<tool response compacted>` placeholder.

## Failure behavior

Every step degrades gracefully. If the summarization LLM call fails, the previous summary and checkpoint are kept, the active slice is sent as-is, and summarization is retried on the next turn. A summarization failure never breaks the user's request.

## Configuration

Summarization is enabled by setting `max_token_context` on a model in the LLM configuration file:

```json
{
  "hrid": "default-model",
  "max_token_context": 128000,
  ...
}
```

The conversation budget is derived from the same settings that drive the document inlining budget:

```text
usable_context          = max_token_context - DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS
message_token_budget    = int(usable_context × (1 - DOCUMENT_CONTEXT_BUDGET_RATIO))
```

See [attachments.md](attachments.md#conversation-history-summarization) for the full budget formulas, the settings reference (`DOCUMENT_CONTEXT_BUDGET_RATIO`, `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS`, `CONVERSATION_SUMMARY_CONTEXT_MESSAGES`, `CONVERSATION_SUMMARY_MAX_TOKENS`, `LLM_SUMMARIZATION_MODEL_HRID`) and how to disable summarization without changing document budgets.

## Token estimation

Tokens are estimated without calling the model's tokenizer, using tiktoken (`cl100k_base`). This is intentionally rough — the goal is to stay well within the context limit, not to maximise usage. Each message also carries a small fixed overhead (4 tokens per part + 4 per message) to account for role markers and formatting.

**System prompt, tool schemas and pydantic-ai framework overhead** are not counted; the security buffer is the backstop.

## Local testing

To trigger summarization locally, set a small `max_token_context` on the default model (large enough to survive `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS`, or lower that setting too). After a few messages the "Summarizing conversation..." notice should appear and the chat should continue to work normally, with `history_summary` populated on the conversation row.
