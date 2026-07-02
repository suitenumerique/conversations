# Model Fallback & Health-Aware Routing

When the default LLM is degraded, Conversations transparently routes new
conversations to a healthy fallback model. This document describes the
mechanism, how it is configured, and how operators can tune it at runtime.

## Slots

Three environment variables define the routing slots:

| Variable                       | Role                          |
| ------------------------------ | ----------------------------- |
| `LLM_DEFAULT_MODEL_HRID`       | Preferred (main) model        |
| `LLM_FALLBACK_MODEL_HRID_1`    | First fallback                |
| `LLM_FALLBACK_MODEL_HRID_2`    | Second fallback (optional)    |

Each HRID must correspond to an entry in the LLM configuration file (see
[`llm-configuration.md`](llm-configuration.md)).

## Health states

A background probe writes each model's health into the Django cache:

- `green` — healthy
- `yellow` — degraded (slow but responding)
- `red` — failing
- `None` — unknown / not yet probed

Cache key: `model_health_cache_key(provider_hrid, model_name)` (see
`chat/model_health.py`).

## Routing cascade

`chat/model_routing.py:resolve_effective_model_hrid` decides which model
to pin to a *new* conversation:

1. An explicit non-default `model_hrid` in the request always wins (used by
   the dev/staging picker).
2. Otherwise, if the main model is below its eviction threshold → use the
   default.
3. Otherwise, try fallback 1, then fallback 2: the first one not above the
   fallback threshold wins.
4. If everything is down, fall back to the default and let the caller
   surface the outage banner.

## Pin-once behavior

`ChatConversation.model_hrid` is set on the **first** POST to the
conversation endpoint (`chat/views/__init__.py`) and never changes
afterwards. A recovered main model does not move an in-progress chat — the
conversation stays on whatever model it was pinned to. Pre-existing
conversations were backfilled to `settings.LLM_DEFAULT_MODEL_HRID` by
migration `chat/0011_chatconversation_model_hrid`.

## Image guard

If the pinned model has `supports_image=False` and the conversation or its
parent project carries image attachments, images are stripped before the
call and a `chat_notice` SSE event is emitted. The frontend surfaces this
via the `ImageProcessingUnavailableBanner`. Text-bearing attachments
(PDFs, documents) are unaffected — they are handled by the RAG pipeline
independently of vision capability.

## Live thresholds

`ModelHealthSettings` is a `SingletonModel` (django-solo) editable in the
Django admin. It exposes two choices fields:

| Field                          | Default | Choices            | Effect                                                                          |
| ------------------------------ | ------- | ------------------ | ------------------------------------------------------------------------------- |
| `main_eviction_threshold`      | `red`   | `yellow` / `red`   | `yellow` cascades on any degradation; `red` tolerates a slow main.              |
| `fallback_eviction_threshold`  | `red`   | `yellow` / `red`   | Same semantics, applied uniformly to fallback 1 and fallback 2.                 |

Admin writes are mirrored to the cache via `transaction.on_commit`
(`core/admin.py`), so workers pick up the new thresholds immediately
without a restart.
