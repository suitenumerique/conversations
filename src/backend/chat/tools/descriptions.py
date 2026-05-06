"""Shared descriptions for chat tools."""

DOCUMENT_SEARCH_RAG_SYSTEM_PROMPT = """
Use document_search_rag ONLY to retrieve specific passages from attached documents.
Do NOT use it to summarize; for summaries, call the summarize tool instead.
"""

DOCUMENT_SEARCH_RAG_TOOL_DESCRIPTION = """
Search for information within the documents provided by the user.

Use this tool when the user asks about content from attached documents 
(reports, contracts, PDFs, etc.). Prefer this tool over web_search when 
the answer might be in the documents.

Must be used whenever the user asks for specific information while having documents attached.
Do NOT use this tool for up-to-date information or current events.

The query must contain all information to find accurate results.

When `document_id` is provided, search is filtered to a single
text attachment by UUID from the context documents list.
Example:
user : "Based on the report, what is the deadline?"
query : "what is the deadline?"
document_id : id_from_context
"""

DOCUMENT_SUMMARIZE_SYSTEM_PROMPT = """
When you receive a result from the summarization tool, you MUST return it 
directly to the user without any modification, paraphrasing, or additional summarization.
You may translate it if needed, but preserve all information / copy it verbatim.
"""

DOCUMENT_SUMMARIZE_TOOL_DESCRIPTION = """
Generate a complete, ready-to-use summary of documents attached to the
current conversation (the entries listed under `documents` in the system
context). For files in the project library (entries under
`project_documents`), call `summarize_project` instead.

Do not request the documents to the user, this tool can access them directly.
Return this summary directly to the user WITHOUT any modification,
or additional summarization.
The summary is already optimized and MUST be presented as-is in the final response
or translated preserving the information.

Instructions are optional but should reflect the user's request.

Examples:
"Summarize this doc in 2 paragraphs" -> instructions = "summary in 2 paragraphs"
"Summarize this doc in English" -> instructions = "In English", document_id=None
"Summarize this doc" -> instructions = "" (default), document_id=None
"Summarize this specific doc" -> instructions = "", document_id=id_from_context

The `document_id` argument MUST be a UUID picked from the `documents` array.
If the user is referring to a project library file, call `summarize_project`
with an id picked from `project_documents` instead.
"""

DOCUMENT_SUMMARIZE_PROJECT_TOOL_DESCRIPTION = """
Generate a complete, ready-to-use summary of files in the project library
(the entries listed under `project_documents` in the system context). These
files are shared across every conversation in the project.

Use this tool only when the user is referring to project files. For files
attached to the current conversation only (entries under `documents`), use
`summarize` instead.

Do not request the documents to the user, this tool can access them directly.
Return this summary directly to the user WITHOUT any modification,
or additional summarization.

Examples:
"Summarize the team handbook" (a project file) -> instructions = "", document_id=id_from_project_documents
"Summarize all our project docs" -> instructions = "", document_id=None
"Summarize the project brief in 3 bullets" -> instructions = "3 bullets", document_id=id_from_project_documents

The `document_id` argument MUST be a UUID picked from the `project_documents`
array. Passing a UUID from the `documents` array will be rejected.
"""

WEB_SEARCH_TOOL_DESCRIPTION = """
Search the web for real-time and up-to-date information.

Use this tool when the user asks about:
- Recent news, current events or ongoing situations
- Legal questions, laws, regulations or jurisprudence
- Data that changes over time (prices, rates, statistics)
- Complex technical topics requiring verifiable sources
- Any topic where outdated information could mislead or harm the user
- Any terms, acronyms, or specificities that sound foreign to you

When in doubt, ALWAYS prefer calling this tool rather than relying 
on your training data, which may be outdated.

Do NOT use for general conversation or creative tasks without factual needs.

Examples of queries that MUST trigger web_search tool:
- "Quelles sont les dernières nouvelles sur X ?"
- "Quel est le taux d'intérêt actuel ?"
- "Est-ce que la loi X est toujours en vigueur ?"
- "Quelle est la réglementation RGPD sur X ?"
- "Quel est le prix actuel de X ?"
- "Que signifie l'acronyme X ?"
- "Qu'est-ce qui s'est passé récemment avec X ?"
- "Quelles sont les sanctions prévues par la loi pour X ?"

Examples of queries that do NOT need web_search tool:
- "Explique-moi comment fonctionne une boucle for"
- "Écris-moi un poème sur l'automne"
- "Résume ce texte"
"""

SELF_DOCUMENTATION_TOOL_DESCRIPTION = (
    "For questions about your "
    "identity, model, capabilities, limitations, privacy, "
    "internet access, accepted files, or hosting, call the "
    "self_documentation tool before answering."
)
