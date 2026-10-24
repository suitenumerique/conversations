"""Shared descriptions for chat tools."""

DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT = """
Use document_search_rag to retrieve specific passages from attached documents.
Do NOT use it to summarize; for summaries, call the summarize tool instead.
When a question combines document content with freshness or current events,
search the document first, then use web_search for the up-to-date part.
When the user asks to extract passages and then summarize them, search first,
then call summarize.
If the user asks about document content — or asks to ignore the document for
general/legal knowledge — always search first and answer only from retrieved
passages. Never replace them with statutory defaults or outside legal knowledge.
Do not cite filenames unless they appear in the passages.
"""

DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION = """
Search for information within the documents provided by the user.

Use when the user asks about content from attached documents (reports, contracts,
PDFs, etc.). Prefer this over web_search when the answer might be in the documents.

Must be used for questions about attached-document content, including when the
user quotes the document or asks to ignore it for legal/general knowledge.
Do NOT use when the user only asks to summarize (use summarize) or only needs
live external data with no document involved.
When freshness/current events also matter: search the document first, then web_search.

The query must contain all information to find accurate results.
When `document_id` is provided, filter to that attachment UUID from context.
"""

DOCUMENT_SUMMARIZE_SYSTEM_PROMPT = """
When you receive a result from the summarization tool, you MUST return it
directly to the user without any modification, paraphrasing, or additional
summarization. You may translate it if needed, but preserve all information.
"""

DOCUMENT_SUMMARIZE_TOOL_DESCRIPTION = """
Generate a complete, ready-to-use summary of documents attached to the
current conversation (`documents` in context). For project library files
(`project_documents`), call `summarize_project` instead.

Use when the user asks for a summary. Prefer summarize over document_search_rag
for pure summary requests. When they ask to find/extract passages then summarize,
call document_search_rag first, then summarize — do not skip summarize. When they
ask to summarize then check whether information is still current, call summarize
first, then web_search (no document_search_rag needed).

Do not request the documents; present the summary as-is (or translate preserving
information). Instructions are optional. `document_id` MUST be a UUID from
`documents` (use `summarize_project` for project library ids).
"""

DOCUMENT_SUMMARIZE_PROJECT_TOOL_DESCRIPTION = """
Generate a complete, ready-to-use summary of files in the project library
(`project_documents` in context), shared across the project.

Use only for project files. For conversation attachments (`documents`), use
`summarize` instead.

Do not request the documents; present the summary as-is.
`document_id` MUST be a UUID from `project_documents` (ids from `documents`
are rejected).
"""

WEB_SEARCH_TOOL_DESCRIPTION = """
Search the web for real-time and up-to-date information.

Use for: recent news/current events; laws, regulations, jurisprudence;
time-varying data (prices, rates, stats); topics where outdated info could
mislead; unfamiliar terms/acronyms; whether attached-document info is still
current — after document_search_rag or summarize.

When in doubt on time-sensitive topics, prefer this tool over training data.

Do NOT use for:
- General conversation or creative tasks without factual needs
- Stable historical or geographic facts that do not change over time,
  even if the user uses words like "still" or "always"
  (e.g. who invented X, capitals, discovery dates)
"""

GENERATE_PRESENTATION_TOOL_DESCRIPTION = """
Generate a slide deck (.pptx) and return a link to download it.

Use this tool whenever the user asks for a presentation, a deck, slides, or a
support to project in a meeting. The tool writes the slides itself: pass a
brief describing the subject, the audience and any structure the user asked
for, not the slides themselves. The tool reads the attached documents on its
own: point it at the right ones with `document_ids`, and do not summarize or
search them, neither in the brief nor before calling it. Pass `slide_count`
when the user asked for a number of slides, and `style` when they asked for
colours, fonts or text sizes.

To change a deck already generated in the conversation, use
`update_presentation` instead.

When the user attaches a pptx to use as a template, a model, or a deck to start
from, pass it as `template_id`: the deck is then built out of copies of its
slides and keeps their design. When the user asks to change that deck, say so
in the brief. Without it, the deck uses the standard template.

What the tool CANNOT do: add logos, insert images, charts or diagrams, or change
the ones of the user's slides. When the user asks for any of these, still
generate the deck, then tell them plainly that this part was not applied.

The tool returns a download link. Pass that link on to the user as-is; do NOT
restate the deck's content or list the slides.

Do NOT use this tool to:
- Write a document, a report or a note (no slides involved)
- Summarize an attached document (use the summarize tool)
- Answer a question about presentations in general

Examples that MUST trigger this tool:
- "Fais-moi une présentation sur la sobriété énergétique"
- "Prépare un support de 10 slides pour le comité de lundi"
- "Convertis cette note en deck"

Examples that must NOT trigger this tool:
- "Résume ce document"
- "Comment structurer une bonne présentation ?"
"""

UPDATE_PRESENTATION_TOOL_DESCRIPTION = """
Change the last slide deck generated in the conversation and return a link to
the new version.

Use this tool whenever the user asks to change a deck they already got:
- its style: pass in `style` only the fields they want changed (colours, fonts,
  text sizes). The content is kept word for word. Unless changed, titles are
  about 26 pt and text about 14 pt: start from there for "bigger" or "smaller".
- its content or layout: pass their request in `instructions` (expand, shorten,
  add, remove or reorder slides, put a slide on two columns, fix a figure...).
  The tool keeps the deck's source documents: do not summarize or search them.
- to undo the last change ("reviens à la version d'avant"): set `revert`. The
  previous version is restored exactly; never rewrite the deck to undo a change.
A style and instructions can be passed at once.

The same limitations as generate_presentation apply: no new logos, images,
charts or diagrams. Tell the user plainly when they asked for one of these.

The tool returns a download link. Pass that link on to the user as-is; do NOT
restate the deck's content or list the slides.

Examples that MUST trigger this tool, once a deck was generated:
- "Mets les titres en bleu"
- "Agrandis le texte"
- "Développe la troisième diapositive"
- "Ajoute une slide sur le budget"
"""

SELF_DOCUMENTATION_SYSTEM_PROMPT = (
    "For meta questions about THIS assistant itself (identity, model, "
    "capabilities, limitations, privacy, internet access, accepted files, "
    "hosting, or when it uses web search), call the self_documentation tool "
    "before answering. This applies when the user addresses you directly "
    "(you / tu / vous) about what you can do or how you work. "
    "Do not call it for generic questions about AI or LLMs in general, "
    "for document content, or for tasks you should perform."
)

SELF_DOCUMENTATION_TOOL_DESCRIPTION = """
Call self_documentation ONLY for meta questions about THIS assistant itself:
identity, model, capabilities, limitations, privacy, internet access, accepted
files, hosting, or when it uses web search.

Use when the user addresses you directly (you / tu / vous). Do NOT use for
generic AI/LLM questions (third person), document content, or performing a
coding/writing/translation task.

Examples that MUST trigger: "Which model are you?", "What can you do?",
"Can you analyze spreadsheets?", "When do you search the web?"
Examples that must NOT: "Can language models analyze spreadsheets?",
"Summarize this document", "Write a sorting function in Rust"
"""

CONVERSATION_SUMMARY_TOOL_DESCRIPTION = (
    "You are a conversation summarization assistant. Your role is to maintain\n"
    "a concise and accurate running summary of a conversation, "
    "omitting small talk and unrelated topics.\n\n"
    "Given the previous summary (if any) and the new exchanges provided,\n"
    "generate an updated summary that:\n\n"
    "- **Preserves** every key information, decisions, and important facts\n"
    "- **Integrates** the new exchanges in a coherent way\n"
    "- **Removes** redundant or non-essential details\n"
    "- **Maintains** the context needed for the conversation to continue\n"
    "- Is written in a neutral, factual, third-person style\n"
    "- Stays **concise** (5-10 lines maximum)\n\n"
    "## Previous Summary:\n"
    "{latest_summary}\n\n"
    "## New Exchanges:\n"
    "{exchanges}\n\n"
    "Only answer with the updated summary, including the new exchanges "
    "information and the previous summary.\n\n"
    "## Updated Summary:\n"
)
