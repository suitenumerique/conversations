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

## OCR routing

PDF OCR follows a much simpler rule than the chat cascade, in
`chat/agent_rag/document_converter/parser.py:use_fallback_ocr`:

1. `OCR_HRID` `green` → Mistral OCR.
2. `OCR_HRID` not `green` (including unknown) **and** `OCR_FALLBACK_HRID`
   `green` → the fallback model.
3. Anything else → Mistral OCR, allowed to fail. A degraded fallback is not an
   improvement over a degraded primary, and the failure is what marks the
   attachment as re-indexable.

The admin eviction thresholds above do **not** apply here: OCR treats anything
other than `green` as unusable.

| Variable                      | Role                                                                     |
| ----------------------------- | ------------------------------------------------------------------------ |
| `OCR_HRID`                    | Config entry of the OCR model, called on the provider's `/v1/ocr`         |
| `OCR_FALLBACK_HRID`           | Config entry of the fallback vision model (empty = fallback disabled)     |

Both are ordinary LLM configuration entries carrying `is_active: false`, so
they stay out of the model picker while still exposing a `model_name` — which
is what health is keyed on, and what is sent as `model` in the request. An
entry whose `model_name` is *not* the model doing the OCR would silently route
on some other model's health.

The two OCR backends do not speak the same protocol: Mistral OCR takes the
whole PDF in `OCR_BATCH_PAGES`-sized batches, while the fallback is a
vision-language model that reads images, so pages are rasterised to PNG and
sent one request at a time. See
[`attachments.md`](attachments.md#other-document-types) for the details.
