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

# The task releases its claim in `finally`, including when Celery is about to
# schedule a retry, so an absent claim does not mean generation is over. The
# waiting turn only gives up once the claim has been dead *continuously* for
# this long. It must exceed the longest single retry backoff (1s/2s/4s) plus
# broker latency; under a worker backlog the gap can still outlast it, in
# which case the turn fails while the retry goes on to persist the summary
# for the next turn.
HISTORY_SUMMARY_CLAIM_DEAD_GRACE_SECONDS = 10

# How often the waiting turn re-reads the conversation from the DB while a
# worker generates the summary. Each tick is an `arefresh_from_db`, so this
# bounds the DB load per concurrent over-budget turn; summaries take seconds,
# so a couple-second cadence is responsive enough.
HISTORY_SUMMARY_POLL_INTERVAL_SECONDS = 2

# How the turn in flight is written to `ChatStreamChunk`. Text is appended
# often and cheaply; a snapshot of the whole turn is appended rarely, because
# it is the only thing that carries structure (a tool call, its result) and the
# request the answer belongs to. Rebuilding the turn means taking the last
# snapshot and adding the text appended after it, so the interval on the
# snapshot bounds nothing a reader sees: it bounds only how much structure a
# turn cut short can lose.
STREAM_TEXT_FLUSH_INTERVAL_SECONDS = 0.25
STREAM_TEXT_FLUSH_CHARS = 200
STREAM_SNAPSHOT_INTERVAL_SECONDS = 5

# How long after its last row a turn is still considered to be running. Past
# it, the chunks are read as what an interrupted turn left behind rather than
# as an answer still on its way.
#
# Must stay comfortably above KEEPALIVE_INTERVAL: a turn blocked on a document
# parse or a tool call produces nothing for minutes, and what keeps it from
# reading as abandoned is the beat row the keepalive loop appends on every
# tick. Below that interval a running turn would look dead, and a turn from
# another tab would fold and delete its trail from under it. Above it, the only
# cost is that a turn whose reader vanished keeps looking live for one window,
# which resolves itself.
STREAM_LIVE_WINDOW_SECONDS = 120
