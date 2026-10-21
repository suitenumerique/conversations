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
brief + slide_count + source documents
  → fit to the token budget       verbatim, long ones summarized, truncated, or left out
  → PresentationAgent (LLM)      produces a validated Presentation spec
  → renderer                      Markdown in each field → pptx runs, lists, tables
  → builder                       assembles the deck from the bundled template
  → object storage (S3/MinIO)     the .pptx bytes are written
  → presigned URL                 a time-limited link is returned to the user
```

- **Source documents** are the conversation's READY text attachments, or the ones the
  model picks with `document_ids` (which may also target project-library files; `[]`
  means none). They are given verbatim when they all fit the document budget
  (`DOCUMENT_CONTEXT_BUDGET_RATIO` of the default model's context). Otherwise, the
  documents over their share of the budget go through the summarization pipeline of
  the `summarize` tool, asked to keep the details a deck needs. The summary is cached
  on the content for 30 minutes, so a retry or another version of the deck does not
  summarize again, and it is truncated should it still exceed the budget.
- **`PresentationAgent`** (`chat/agents/presentation.py`) is a dedicated Pydantic AI
  agent whose structured output is a `Presentation`: a deck title and an ordered list
  of typed slides. Its system prompt lists the available slide types straight from the
  template bindings. When the user asks for a number of slides (`slide_count`, 1 to
  50, cover and section slides included), a deck of another length is sent back to the
  model, twice at most.
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
  (`check_template`) keeps those bindings consistent with the file. The file was
  edited by hand to give the cover and section layouts a `Sous-titre` placeholder and
  to drop the section layout's photo area; `generic.py` lists the edits and how to
  redo them.

- **The style** (`PresentationStyle`, applied by `chat/file_generation/styling.py`)
  overrides the template's title and text colours, fonts and sizes and the background
  colour, when the user asks for them. Unset fields keep the template's styling.
- **Text fitting** (`styling.py` too): every title and text field is set to shrink to
  fit its placeholder, and the scale body text needs is stored in the file, because
  PowerPoint only recomputes it once the text is edited. The scale is estimated from
  rough font metrics (`CHAR_WIDTH`, `LINE_HEIGHT`, `PARAGRAPH_GAP`): adjust them there
  if decks overflow or shrink too much. Tables never shrink on their own, so their
  text is given the reduced size directly.

## Editing a deck

`update_presentation` changes the last deck of the conversation in a later turn and
saves the result as a new version:

- **style only**: the deck is rebuilt with the merged style, without the agent;
- **instructions**: the agent rewrites the deck from the current one, the changes
  requested and the deck's documents, read again (a deleted one is left out, and the
  model is told so);
- **revert**: the version the current one came from is restored as it was. Undoing
  again goes one step further back; there is no redo.

Each version is kept in the tool result's metadata (`StoredPresentation`), persisted
with the conversation history but never sent to the model or the UI. It keeps the
ids of the deck's documents, not their text, so the history stays small and the text
goes when a document is deleted. An edit summarizes long documents again once the
30-minute summary cache has expired.

## Limitations

Every deck uses the bundled template. An attached pptx template or slide master,
logos, images, charts and diagrams are not supported yet. The tool description
and every tool result say so, so the model tells the user rather than claiming
they were applied.

When the documents do not all fit, each one gets an equal share of the budget,
whatever the size of the others: a document over its share is summarized even when
the room left by shorter ones would have fit it. Summarization also runs however
little budget remains after the verbatim documents, so a long document may be
summarized only to be truncated to a few tokens.

## Access model

The generated deck is a one-off artifact: nothing is recorded in the database. It is
written to object storage under a conversation-scoped key and reached **only** through
a signed, time-limited URL (15 minutes).

The object key ends in a fixed name plus random hex (`presentation_<hex>.pptx`), not a
UUID. This is deliberate: it does **not** match the media proxy's URL pattern
(`AttachmentMixin.MEDIA_STORAGE_URL_PATTERN`, which requires a UUID), so the deck cannot
be served through the cookie-authenticated media proxy and is reachable solely via the
presigned URL. The random hex keeps the key non-guessable. The name never comes from the deck
title: the deck agent writes it after reading the documents, and the URL goes back to
the main model.

## See Also

- [Tools for the Conversation Agent](tools.md)
- [Attachments and Summarization](attachments.md)
- [Environment Variables](env.md)
