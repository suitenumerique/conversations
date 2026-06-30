"""Shared constants for the chat application."""

# MIME prefix used to identify attachments whose content can be fed to the LLM
# as raw text (markdown, plain, csv, ...). Excludes images and PDFs, which
# the LLM consumes through different channels.
TEXT_MIME_PREFIX = "text/"

# MIME prefix for image attachments - excluded from RAG indexing and routed
# through the LLM's vision channel instead.
IMAGE_MIME_PREFIX = "image/"

# Full MIME types used to label or route specific payloads.
PDF_MIME_TYPE = "application/pdf"  # routed to the dedicated PDF parser
MARKDOWN_MIME_TYPE = "text/markdown"  # markdown companion stored for indexed files
SSE_MIME_TYPE = "text/event-stream"  # Server-Sent Events streaming responses

# Access values exposed to the model in the documents listing. Keep in sync
# with the `Access` Literal in chat.document_context_builder (Python's Literal
# can't reference module-level constants).
ACCESS_FULL_CONTEXT = "full-context"
ACCESS_TOOL_CALL_ONLY = "tool_call_only"
