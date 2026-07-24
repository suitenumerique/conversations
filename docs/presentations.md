# Slide Deck Generation

The conversation agent can produce a downloadable PowerPoint (`.pptx`) slide deck
from a user's request through the `generate_presentation` tool. When a user asks for
a presentation, a deck, slides, or a support to project in a meeting, the agent calls
the tool with a *brief* (the subject, the audience and any structure asked for) and
hands back a time-limited download link.

This tool is **feature-flag gated** and registered directly on the conversation agent
(it is not part of the per-model tool registry in [tools.md](tools.md); like the
`summarize` tool documented in [attachments.md](attachments.md), it is enabled globally
rather than per model).

## Enabling the tool

The tool is disabled by default (`presentation_generation` in
`core/feature_flags/flags.py`). Enable it with an environment variable:

```bash
FEATURE_FLAG_PRESENTATION_GENERATION=enabled   # on for everyone
# or
FEATURE_FLAG_PRESENTATION_GENERATION=dynamic   # per-user rollout via PostHog
```

`dynamic` resolves the flag per user at runtime and falls back to *disabled* when no
PostHog backend is configured. The flag is read when the agent service is built, so the
tool is registered (and visible to the model) only for requests where it is enabled.

## How it works

```text
user brief
  → PresentationAgent (LLM)      produces a validated Presentation spec
  → renderer                      Markdown in each field → pptx runs, lists, tables
  → builder                       assembles the deck from the bundled template
  → object storage (S3/MinIO)     the .pptx bytes are written
  → presigned URL                 a time-limited link is returned to the user
```

- **`PresentationAgent`** (`chat/agents/presentation.py`) is a dedicated Pydantic AI
  agent whose structured output is a `Presentation`: a deck title and an ordered list
  of typed slides. Its system prompt lists the available slide types straight from the
  template bindings.
- **The spec** (`chat/file_generation/entities.py`) constrains the model: each slide
  has a `type` (`cover`, `section`, `title_one_column`, `title_two_columns`,
  `title_three_columns`) and only the fields that type declares are used.
- **The renderer** (`chat/file_generation/renderer.py`) turns each field's Markdown
  into formatted content. Supported: inline styles (bold, italic, underline, code),
  links, and nested lists (indent with 4 spaces). Tables are supported too, but a table
  **takes over its whole field** — a pptx table is a separate graphic frame, so any
  other content in the same field is dropped.
- **The template** (`chat/file_generation/templates/generic.pptx` + `generic.py`)
  carries the visual identity (colour scheme, Marianne typeface, layouts). `generic.py`
  only declares which placeholder of which layout receives which field; a test
  (`check_template`) keeps those bindings consistent with the file.

## Access model

The generated deck is a one-off artifact: nothing is recorded in the database. It is
written to object storage under a conversation-scoped key and reached **only** through
a signed, time-limited URL (15 minutes).

The object key ends in a readable slug plus random hex (`<slug>_<hex>.pptx`), not a
UUID. This is deliberate: it does **not** match the media proxy's URL pattern
(`AttachmentMixin.MEDIA_STORAGE_URL_PATTERN`, which requires a UUID), so the deck cannot
be served through the cookie-authenticated media proxy and is reachable solely via the
presigned URL. The random hex keeps the key non-guessable.

## See Also

- [Tools for the Conversation Agent](tools.md)
- [Attachments and Summarization](attachments.md)
- [Environment Variables](env.md)
