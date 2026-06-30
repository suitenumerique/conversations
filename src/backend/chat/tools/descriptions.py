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
