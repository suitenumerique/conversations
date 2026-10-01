# LLM Router

The router picks, on every turn, the lightest model able to answer the user's
message. Each message is rated `simple`, `standard` or `complex` by a small
classifier model, and the turn runs on the model of that tier. Users can also
pin a tier themselves for the rest of a conversation.

## Enabling it

The router is behind the `router` feature flag, off by default:

```
FEATURE_FLAG_ROUTER=ENABLED   # or DYNAMIC to roll it out through PostHog
```

With the flag off, nothing changes: the conversation keeps the model pinned on
its first message, and the model selector stays in the compose box.

## Tiers

| Tier       | Label in the UI | Typical requests                         |
| ---------- | --------------- | ---------------------------------------- |
| `simple`   | Fast            | Greetings, rephrasing, short facts       |
| `standard` | Balanced        | Writing, summaries, explanations         |
| `complex`  | Reasoning       | Analyses, calculations, multi-step tasks |

Each tier runs one model, plus optional alternatives. Every HRID must be a
`chat` model of the LLM configuration (see
[`llm-configuration.md`](llm-configuration.md)); models with
`"role": "utility"` (such as the summarization model) are not offered to users
while the flag is on, and are never accepted as a tier model.

A tier with no model falls back to `LLM_DEFAULT_MODEL_HRID`, so enabling the
flag without configuring anything routes every turn to the default model.

## Settings

| Variable                       | Default | Role                                          |
| ------------------------------ | ------- | --------------------------------------------- |
| `LLM_ROUTER_MODEL_HRID`        | `""`    | Classifier model; blank uses the default model |
| `LLM_ROUTER_TIMEOUT_S`         | `2.5`   | Budget of the classifier call                 |
| `LLM_TIER_SIMPLE_MODEL_HRID`   | `""`    | Model of the `simple` tier                    |
| `LLM_TIER_STANDARD_MODEL_HRID` | `""`    | Model of the `standard` tier                  |
| `LLM_TIER_COMPLEX_MODEL_HRID`  | `""`    | Model of the `complex` tier                   |

The **Routing Tier Settings** admin page overrides these values at runtime: the
model and alternatives of each tier, the classifier model, and the confidence
threshold (`0.70` by default).

## How a turn is routed

1. A pinned tier is used as is. Otherwise the classifier rates the message; a
   short follow-up (under six words, no attachment) reuses the previous turn's
   rating without calling it. On timeout or error the turn falls back to the previous rating,
   else to `standard`.
2. `simple` and `complex` are only kept at or above the confidence threshold;
   below it the turn runs on `standard`.
3. The tier's models (then those of the tiers above) are tried until one has
   what the turn needs: image input when the message or the conversation has
   an image, web search when it is forced, a context window large enough for
   the history. When no tier model fits, the default model is used.
4. The usual health cascade applies among the tier's models and the
   `LLM_FALLBACK_MODEL_HRID_*` slots (see [`model-fallback.md`](model-fallback.md)).

An explicit `model_hrid` in the request is still honoured as is.

## What the user sees

- The tier selector replaces the model selector in the compose box: **Auto**
  (recommended), and behind one more click **Fast**, **Balanced** and
  **Reasoning**, each with an energy pictogram. A manual choice applies to the
  conversation until the user goes back to Auto; a new conversation starts on
  Auto. Model names are never shown.
- While the router decides, the answer shows "Choosing the model…". Each
  answer then carries a caption such as "Auto · Balanced model" or
  "Fast model · your choice" (or "Reasoning model · needed for this request" when
  a constraint such as an image or forced web search raised the tier, whether it
  was pinned or Auto), next to its energy indicator.
- The first routed answer a user sees comes with a one-line explanation of
  what Auto does.

The decision is streamed to the client as a transient `routing` data part
before the first token, and recorded on the assistant message metadata
(`tier`, `tier_source`, `router_reason`, `router_confidence`,
`router_latency_ms`) so the caption survives a reload.
