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

# Conversation summarization task limits. The claim TTL is the hard time
# limit plus a margin: past it, the claiming worker is provably dead
# (SIGKILLed at time_limit, OOM-killed, or crashed) and the claim stops
# blocking. Keep the three values consistent — the liveness math depends
# on TTL > TIME_LIMIT.
SUMMARIZATION_TASK_SOFT_TIME_LIMIT = 110  # seconds, raises SoftTimeLimitExceeded
SUMMARIZATION_TASK_TIME_LIMIT = 120  # seconds, worker is SIGKILLed
HISTORY_SUMMARY_CLAIM_TTL_SECONDS = SUMMARIZATION_TASK_TIME_LIMIT + 60

# After the triggering turn enqueues the summarization task, how long the
# wait loop tolerates "no live claim yet" before giving up and failing the
# turn (covers broker latency and a short worker backlog). Generation stays
# Celery-only; there is no inline fallback (see ADR 0002).
SUMMARIZATION_ENQUEUE_CLAIM_GRACE_SECONDS = 10
