# Conversation Attachments

This document describes how conversation attachments work in the Conversations application, including the upload process, security measures, and how documents are processed for use with Large Language Models (LLMs).

Two attachment scopes coexist:
- **Conversation attachments** (`ChatConversationAttachment.conversation` set): scoped to a single chat. Indexed on the first chat turn that needs them.
- **Project attachments** (`ChatConversationAttachment.project` set): scoped to a project, shared by every conversation in that project. Indexed at upload time so they are searchable from the very first turn of every conversation in the project.

Both share the same model, same storage, same RAG backend, and the same retrieval tools - they only differ in scope, when indexing happens, and how they appear in the LLM's context (see [Hybrid context delivery](#documents-listing-in-system-instructions)).

## Table of Contents

- [Overview](#overview)
- [Supported Attachment Types](#supported-attachment-types)
- [Architecture & Flow](#architecture--flow)
  - [High-Level Overview](#high-level-overview)
  - [Detailed Technical Flow](#detailed-technical-flow)
- [Project Attachments](#project-attachments)
  - [Indexing at upload time](#indexing-at-upload-time)
  - [Project RAG collection](#project-rag-collection)
  - [Markdown companion attachment](#markdown-companion-attachment)
  - [Deletion lifecycle](#deletion-lifecycle)
- [RAG Collection Lifecycle](#rag-collection-lifecycle)
  - [De-indexing inactive conversations](#de-indexing-inactive-conversations)
  - [Transparent re-indexing on resume](#transparent-re-indexing-on-resume)
- [Security & Validation](#security--validation)
  - [Malware Detection](#malware-detection)
- [Document Processing for LLMs](#document-processing-for-llms)
  - [Image Attachments](#image-attachments)
  - [PDF Documents](#pdf-documents)
  - [Other Document Types](#other-document-types)
  - [Find backend: known limitations](#find-backend-known-limitations)
- [Configuration](#configuration)

---

## Overview

Conversations allows users to attach files to their conversations with the AI assistant. These attachments can be:
- **Images** (displayed directly to vision-capable LLMs)
- **PDF documents** (sent as document URLs to the LLM)
- **Other documents** (converted to text and indexed for semantic search)

The attachment system uses **S3-compatible object storage** (such as MinIO in development) to store files securely. 
The backend generates **presigned URLs** that allow the frontend to upload files directly to the storage, 
without routing the file data through the backend server.

Note about documents: The system uses a tool called **MarkItDown** to convert various document formats 
(Word, Excel, PowerPoint, text files, etc.) into Markdown text for processing by LLMs. When at least 
one non-image document is attached **either to the current conversation or to its project**, the system enables:
 - a **hybrid context delivery** that inlines small conversation documents directly into the LLM's system instructions (`full-context`) and exposes the rest via tools (`tool_call_only`). Project documents are listed separately under `project_documents` and are always `tool_call_only` - they do not compete for the inlining budget. See [Other Document Types](#other-document-types).
 - a **Retrieval-Augmented Generation (RAG)** search tool (`document_search_rag`) to query relevant sections of any attached document. The search payload covers the conversation's collection and, when applicable, the parent project's collection in a single call. Supports an optional `document_id` argument to target a single attachment (conversation- or project-scoped).
 - a **summarization tool** (`summarize`) to provide document summaries of files attached to the **current conversation**, also supporting `document_id` targeting.
 - a **project-scoped summarization tool** (`summarize_project`) for files in the **project library**, registered only when the conversation belongs to a project.
   ⚠️ naive implementation at the moment, needs improvement before being used in production.

## Supported Attachment Types
The following attachment types are supported:
- **Images**: `image/png`, `image/jpeg`, `image/gif`, `image/webp`.
- **PDF documents**: `application/pdf`
- **Other documents**:
  - Microsoft Word: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - Microsoft Excel: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - Microsoft PowerPoint: `application/vnd.openxmlformats-officedocument.presentationml.presentation`
  - Text files: `text/plain`, `text/markdown`, `text/csv`

**Warning**: The current implementation for PDF expects the LLM to be able to manage them. We need to
improve the handling of PDFs in case the LLM cannot process them natively.

**Todo**: 
 - Add support for more file types and improve document processing workflows.
 - Allow PDF management via RAG search when the LLM cannot handle them natively.
 - Allow file type restrictions based on model settings, instead of globally.
 - Improve the summarization tool to provide better summaries and handle larger documents.
 - Start file upload right away when the user selects a file, instead of waiting for the user to send the message.


---

## Architecture & Flow

### High-Level Overview

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Frontend  │       │   Backend   │       │  S3 Storage │       │ Malware Det.│
└──────┬──────┘       └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
       │                     │                     │                     │
       │ 1. Create attachment│                     │                     │
       ├────────────────────>│                     │                     │
       │                     │                     │                     │
       │ 2. Return presigned │                     │                     │
       │    URL for upload   │                     │                     │
       │<────────────────────┤                     │                     │
       │                     │                     │                     │
       │ 3. Upload file      │                     │                     │
       │    directly to S3   │                     │                     │
       ├──────────────────────────────────────────>│                     │
       │                     │                     │                     │
       │ 4. Notify upload    │                     │                     │
       │    completed        │                     │                     │
       ├────────────────────>│                     │                     │
       │                     │                     │                     │
       │                     │ 5. Detect MIME type │                     │
       │                     ├────────────────────>│                     │
       │                     │                     │                     │
       │                     │ 6. Scan for malware │                     │
       │                     ├──────────────────────────────────────────>│
       │                     │                     │                     │
       │                     │ 7. Update status    │                     │
       │ 8. Return status    │<──────────────────────────────────────────┤
       │<────────────────────┤                     │                     │
       │                     │                     │                     │
```

### Detailed Technical Flow

#### Step 1: Attachment Creation Request

When a user selects a file to upload, the frontend sends a POST request to create an attachment record:

**Endpoint**: `POST /api/conversations/{conversation_id}/attachments/`

**Request payload**:
```json
{
  "file_name": "document.pdf",
  "size": 1048576,
  "content_type": "application/pdf"
}
```

**Backend processing** (`ChatConversationAttachmentViewSet.perform_create`):
1. Verifies the user owns the conversation
2. Generates a unique UUID for the file
3. Creates a storage key: `{conversation_id}/attachments/{uuid}.{extension}`
4. Creates a database record with status `PENDING`

**Response**:
```json
{
  "id": "uuid-of-attachment",
  "key": "conversation-id/attachments/file-id.pdf",
  "file_name": "document.pdf",
  "size": 1048576,
  "upload_state": "pending",
  "policy": "https://s3.example.com/bucket/...?presigned-params"
}
```

The `policy` field contains a **presigned URL** valid for a limited time (configured by `AWS_S3_UPLOAD_POLICY_EXPIRATION`).

#### Step 2: Direct Upload to S3

The frontend uses the presigned URL to upload the file directly to S3 storage using a PUT request.

**Technical details**:
- The presigned URL includes authentication parameters
- The upload is done with `Content-Type` header matching the file's MIME type
- No backend involvement in the data transfer

#### Step 3: Upload Completion Notification

After successful upload, the frontend notifies the backend:

**Endpoint**: `POST /api/conversations/{conversation_id}/attachments/{attachment_id}/upload-ended/`

**Backend processing** (`ChatConversationAttachmentViewSet.upload_ended`):

1. **MIME Type Detection** (`chat/views.py`):
   ```python
   mime_detector = magic.Magic(mime=True)
   with default_storage.open(attachment.key, "rb") as file:
       mimetype = mime_detector.from_buffer(file.read(2048))
       size = file.size
   ```
   
   Uses `python-magic` to detect the actual MIME type from file content (first 2048 bytes).

2. **Update attachment status**:
   - Status: `PENDING` → `ANALYZING`
   - Store detected MIME type and actual file size

3. **Trigger Malware Detection**:
   ```python
   malware_detection.analyse_file(
       attachment.key,
       safe_callback="chat.malware_detection.conversation_safe_attachment_callback",
       unknown_callback="chat.malware_detection.unknown_attachment_callback",
       unsafe_callback="chat.malware_detection.conversation_unsafe_attachment_callback",
       conversation_id=conversation_id,
   )
   ```

#### Step 4: Malware Detection Callbacks

The malware detection service (configurable via `MALWARE_DETECTION_BACKEND`) scans the file and calls one of three callbacks:

**Safe file** (`conversation_safe_attachment_callback`):
- Status: `ANALYZING` → `READY`
- File is ready for use

**Unsafe file** (`conversation_unsafe_attachment_callback`):
- Status: `ANALYZING` → `SUSPICIOUS`
- File is quarantined and not accessible
- Security log entry created

**Unknown status** (`unknown_attachment_callback`):
- Handles special cases (e.g., file too large to analyze)
- Status: `ANALYZING` → `FILE_TOO_LARGE_TO_ANALYZE`

---

## Project Attachments

Project attachments live on `ChatProject` rather than on a single `ChatConversation`. They are uploaded through a parallel viewset (`ChatProjectAttachmentViewSet`, `POST /api/v1.0/projects/{project_id}/attachments/`) and reuse the same upload pipeline (presigned URL → upload-ended → MIME detection → malware scan). Three things differ from the conversation flow.

### Indexing at upload time

Conversation attachments are indexed lazily when a chat turn first builds RAG context. Project attachments cannot follow that pattern - any conversation in the project may be the first to ask about a file, and we want them searchable immediately.

The malware safe callback for projects (`chat.malware_detection.project_safe_attachment_callback`) does two things in sequence after marking the attachment `READY`:

1. Fetches the attachment with `select_related("project", "uploaded_by")`.
2. Calls `chat.agent_rag.indexing.index_project_attachment(attachment)`.

`index_project_attachment` is a one-shot, idempotent indexer: it skips images, skips markdown companion rows (`conversion_from` set), skips attachments already carrying a `rag_document_id`, parses the file via `RAG_DOCUMENT_PARSER`, and stores the result in the project's RAG collection. Failures are logged and swallowed - the file stays `READY` and downloadable but won't surface in RAG search until a future re-index.

### Project RAG collection

Each project lazily creates its own RAG collection on the first indexable upload. `ChatProject.
collection_id` starts NULL; `_ensure_project_collection(project)` runs the creation under 
`select_for_update` + `transaction.atomic` so two concurrent first-uploads on a fresh project cannot each create a competing collection at the backend (race condition).

At search time, when a conversation belongs to a project, the project's collection is added to the search payload alongside the conversation's own collection (`read_only_collection_id=[project.collection_id]`). The model can therefore pull chunks from both scopes in a single tool call.

The Albert backend records a per-document id (`rag_document_id`) at index time. The search tool prefers it over name-based filtering (`document_ids: [<int>]` instead of `metadata_filters: document_name`) - this is collection-aware and unambiguous, whereas a name match could collide across the conversation and project collections. The Find backend currently does not return per-document ids; both id-based and name-based filters fall back to a plain query.

### Markdown companion attachment

Parsing a non-text input (PDF, DOCX, ODT, ...) is expensive: it can call Albert's parser endpoint, run MarkItDown, or shell out to `odfdo`. We do not want to pay that cost on every chat turn that reads the document. The companion attachment is the **parsed-content cache** that solves this:

| | Original row | Companion row |
|---|---|---|
| `file_name` | `report.pdf` | `report.pdf.md` |
| `content_type` | `application/pdf` | `text/markdown` |
| `conversion_from` | `NULL` | `<original.key>` (the marker that distinguishes a companion from a real markdown upload) |
| `upload_state` | `READY` | `READY` |
| `rag_document_id` | populated (Albert) | `NULL` |
| S3 key | **Conversation**: shared - one blob backs both rows (companion overwrites the original on upload). **Project**: distinct - companion stored at `<original.key>.md` so the original binary stays intact for direct retrieval. |

What reads it:
- **Hybrid context delivery** (`build_document_context_instruction`): when a conversation attachment is small enough to inline as `full-context`, the builder reads the companion's markdown from S3 and embeds it in the system prompt. Without the companion, every turn would have to re-parse the original.
- **System-prompt listing**: every turn lists every text attachment by `id` and `title`. The companion gives the listing a stable markdown title (`report.pdf` after stripping `.md`) and a `document_id` that maps to the original through `conversion_from`.
- **`summarize` tool**: pulls the parsed markdown directly from the companion's S3 blob.
- **RAG `document_id` resolution**: searches text attachments, which means companions are filtered out (`conversion_from` set) - the model targets the **original** UUID, and the search uses the original's `rag_document_id`. The companion exists only as a parsed-content cache; it is never the search target.

What writes it:
- **Conversation attachments**: created lazily by `_parse_input_documents` on the first chat turn that needs RAG context, after the parser runs.
- **Project attachments**: created at index time inside `index_project_attachment`, so the companion is in place before the very first chat turn that asks about the file.

Cleanup is set-based: the per-attachment delete path collects every key scheduled for removal (original + companion) into a `set` and hands it to `_bulk_delete_s3_blobs`, which issues one `DELETE` per unique blob. For project attachments this means **two** `DELETE` calls (original + `<original.key>.md`); for conversation attachments where the companion shares the original's key, set semantics dedup it down to one. The companion DB row is dropped explicitly on per-attachment delete (filter on `conversion_from = original.key`); on conversation/project cascade delete, both rows are dropped by the same DB cascade.

### Deletion lifecycle

Three paths drop project attachments and each one cleans up the side effects in a defined order:

| Path | Order | Notes |
|---|---|---|
| Per-attachment delete (`DELETE /projects/{p}/attachments/{a}/`) | RAG document → S3 blob → companion row → original row | Each step is best-effort; failures are logged but never block the user-facing delete. Companion is matched by `(project_id, conversion_from = original.key)`. |
| Conversation delete (`DELETE /chats/{c}/`) | RAG collection → S3 blobs (deduped) → DB cascade | Collection drop covers all per-doc state in one call, so per-attachment `delete_document` is not iterated. S3 keys are collected before cascade since CASCADE drops attachment rows but never touches storage. |
| Project delete (`DELETE /projects/{p}/`) | Child-conversation RAG collections → collect S3 keys → bulk conversation delete → project RAG collection → S3 blobs (deduped) → DB cascade | `ChatConversation.project` uses `on_delete=SET_NULL`, so child conversations are explicitly deleted here. Bulk `QuerySet.delete()` bypasses `ChatViewSet.perform_destroy`, which is why child collections are dropped above before the bulk delete fires. The S3-key set must be assembled **before** the bulk conversation delete so the queries still resolve to live attachment rows. |

The trade-off accepted on every path: a transient backend hiccup may strand orphaned RAG/S3 storage rather than strand a DB row the user cannot remove. Cleanup deduplicates S3 keys into a `set` before calling `default_storage.delete`, so conversation companions (which share the original's key) cost one `DELETE` while project companions (distinct `<original.key>.md`) cost two.

---

## RAG Collection Lifecycle

Every conversation that has indexed text attachments owns a RAG collection in the vector store, identified by `ChatConversation.collection_id`. Long-lived deployments accumulate many idle collections that consume storage and quota. This section describes the two-phase lifecycle: scheduled de-indexing of inactive conversations, and transparent re-indexing when a user resumes one.

### De-indexing inactive conversations

The `deindex_inactive_collections` management command identifies conversations that have been inactive for more than `RAG_COLLECTION_INACTIVITY_DAYS` days and removes their vector store collection.


**What "inactive" means**: `ChatConversation.updated_at < now() - RAG_COLLECTION_INACTIVITY_DAYS days`. Because `reindex_conversation` writes `update_fields=["collection_id", "updated_at"]` on success, a recent re-index resets the inactivity clock — a conversation is not de-indexed again immediately after it was just re-indexed.

**Scheduling**: Run this as a periodic job. A Helm CronJob template is provided (`backend.deindexCronJob`) with `concurrencyPolicy: Forbid` to prevent overlapping runs.

**What is NOT de-indexed**: Project collections are managed separately (their lifecycle is tied to project/attachment delete). Only conversation collections controlled by `ChatConversation.collection_id` are affected.

**Claim-first ordering**: The DB row is updated (`collection_id=None`, `index_state=DEINDEXED`, `is_indexed=False`, `rag_document_id=None`) *before* the HTTP delete is sent to the vector store backend. This acts as a distributed lock — a second concurrent run sees `collection_id=None` and skips the row. If the HTTP delete subsequently fails, the command restores `collection_id` and `is_indexed=True` on the DB row. Note: `rag_document_id` is **not** restored on rollback, so after a failed de-index the attachment rows carry `rag_document_id=None` even though the vector store still holds the document. The next re-index triggered by user activity rebuilds from scratch (safe but slightly wasteful).

### Transparent re-indexing on resume

When a user sends a message to a conversation whose `index_state` is `DEINDEXED` or `ERROR` but which has `READY` text attachments, the backend automatically rebuilds the collection before running the agent. This is handled by `reindex_conversation` in `chat/clients/conversation_reindexer.py`.

#### `reindex_conversation` — behaviour summary

An async generator that brings a conversation's RAG collection up to date before the agent runs. It emits a `conversation_resume`
tool-call/result pair so the UI can show progress.

**Claim (concurrency guard)**

Before doing any work it atomically sets `index_state = INDEXING` on the row, but only if the conversation is in a claimable state:

- `DEINDEXED` or `ERROR` → always claimable
- `INDEXING` with `updated_at` older than `REINDEX_CLAIM_TIMEOUT_SECONDS` → stale lock, also claimable

If the row is not updated (another process holds a fresh claim), the generator returns immediately with **no events**.

**Early exits (no events emitted)**

| Condition | New state |
|-----------|-----------|
| No READY attachments | `UNINDEXED` |
| All text attachments are already indexed or in-context | `INDEXED` (if collection exists) / `UNINDEXED` |

**Main path**

1. **Collection**: reuses `conversation.collection_id` if set (so partial-failure retries add only the missing docs to the existing
collection). Creates a new collection otherwise; on creation failure → `ERROR`, error event, return.
2. **Per-attachment loop**: reads the file asynchronously (`asyncio.to_thread`), stores it in the document backend, marks `is_indexed =
True`. Individual failures are caught and collected; the loop always continues.
3. **Final state transition**:
    - Zero failures → `index_state = INDEXED`, `collection_id` updated, `{state: "done"}`
    - Partial failure → `index_state = ERROR`, `collection_id` updated, `{state: "partial", failed_documents: [...]}`
    - Total failure → `index_state = ERROR`, `collection_id` updated (collection exists but is empty), `{state: "error"}`

    The only path that leaves `collection_id=None` is a collection *creation* failure, which returns early before the per-attachment loop.

`ERROR` always triggers a retry on the next request, and because successful attachments have `is_indexed = True`, only the failed ones are
  attempted again.

**What gets re-indexed**: Only `text/*` attachments that are READY, not already inlined as `full-context`, **and** not already indexed (`is_indexed=False`). Small documents that fit the inlining budget are already readable by the model directly from the system prompt — putting them in the vector store too would be redundant. The `is_indexed` flag is what makes partial-failure retries efficient: successful attachments from a previous attempt are skipped, so only genuinely missing documents are re-uploaded.

**Error states**:

| `result.state` | Meaning | User-visible outcome |
|---|---|---|
| `"done"` | All attachments re-indexed | Silent — loader disappears, conversation continues |
| `"partial"` | Some attachments indexed, some failed | Error modal listing failed filenames — user can re-upload them |
| `"error"` | Collection creation failed (`collection_id` stays `None`) **or** all attachments failed (empty collection, `collection_id` set) | Error modal — RAG tools unavailable for this turn |

**Frontend**: While re-indexing is in progress, `ToolInvocationItem` renders a `ConversationResumeLoader` with a chat-bubble illustration and the copy "Picking up where you left off". Once the `ToolResultPart` arrives, the loader disappears. Errors surface via `setChatErrorModal`.

**Binary attachments** (PDF, images): never re-indexed — `reindex_conversation` only processes `text/*` content types. PDFs are sent directly to the LLM as document URLs; images as presigned `ImageUrl` objects. Neither needs a vector store entry.

---

## Security & Validation

For now, the system is not intended to host user-uploaded files for public download.
All files are stored in private S3 buckets with presigned URLs for controlled access and only
the owner of the conversation/the uploader can access them, so the risk is quite low around bad use of
the attachment system.

Also, the document content is sent to the LLM and does not prevent any prompt injection attacks, which is not
an issue specific to the attachment system but to the overall design of LLM-based applications and should be
addressed globally. Also for the moment, the system does not have any action tools that could be used to execute
malicious code based on document content.

### Malware Detection

The malware detection system is **pluggable** and configurable, allowing different backends to be used.
By default, a `DummyBackend` is provided that marks all files as safe.

⚠️ The current implementation does not disallow any file types or status from being used in conversations.
This is a potential security risk and should be addressed in future versions.

---

## Document Processing for LLMs

When a user sends a message with attachments, the system processes them differently based on their type:

### Image Attachments

**MIME types**: `image/png`, `image/jpeg`, `image/gif`, `image/webp`, etc.

**Processing flow**:

1. **URL Conversion**: Local media URLs are converted to presigned S3 URLs before sending to the LLM:
   ```python
   # From: chat/agents/local_media_url_processors.py
   content.url = generate_retrieve_policy(key)
   ```

2. **Sent to LLM**: Images are sent as `ImageUrl` objects in the prompt:
   ```python
   ImageUrl(
       url="https://s3.example.com/bucket/key?presigned-params",
       identifier="file-id.png",
   )
   ```

3. **Vision models** can analyze the image content directly.

4. **Response processing**: After the LLM responds, presigned URLs are converted back to local URLs for storage:
   ```python
   # Mapping: presigned_url -> /media-key/{conversation_id}/attachments/{file_id}.png
   ```

### PDF Documents

**MIME type**: `application/pdf`

**Processing flow**:

1. **Direct URL passing**: PDFs are sent as `DocumentUrl` objects :
   ```python
   DocumentUrl(
       url="https://s3.example.com/bucket/key?presigned-params",
       identifier="file-id.pdf",
   )
   ```

2. **LLM processing**: Compatible LLMs can:
   - Extract and read text from PDFs
   - Understand document structure
   - Answer questions about the content

3. **No conversion needed**: PDFs are passed directly without preprocessing.

### Other Document Types

**MIME types**: Word documents, Excel spreadsheets, PowerPoint, text files, Markdown, etc.

**Processing flow**:

1. **Document parsing**: Two pluggable settings drive parsing and storage:
   - `RAG_DOCUMENT_PARSER` (default `chat.agent_rag.document_converter.parser.AlbertParser`): converts the source bytes to Markdown. Routes by content type - ODT files always use `odfdo`, everything other than PDF/ODT goes through **MarkItDown**, PDFs depend on which parser is configured (see below).
   - `RAG_DOCUMENT_SEARCH_BACKEND` (`AlbertRagBackend` or `FindRagBackend`): stores the converted markdown in the configured vector index and serves search queries.

   **PDF parsing strategies** (per `RAG_DOCUMENT_PARSER`):
   - `AlbertParser`: every PDF is sent unconditionally to the Albert `/v1/parse-beta` endpoint.
   - `AdaptivePdfParser`: runs a `pypdf`-based heuristic on the upload first (see `analyze_pdf` in `parser.py`):
     - Counts pages with extractable text and the average characters per page.
     - If `avg_chars_per_page > MIN_AVG_CHARS_FOR_TEXT_EXTRACTION` AND `text_coverage > MIN_TEXT_COVERAGE_FOR_TEXT_EXTRACTION`, the PDF is treated as a born-digital text PDF and converted **locally** via MarkItDown - no external API call.
     - Otherwise (scanned, image-only, or low-text-density PDF), the parser falls back to the configured OCR endpoint (`OCR_HRID` provider's `/v1/ocr`, default Mistral OCR), processing the document in `OCR_BATCH_PAGES`-sized batches with `OCR_MAX_RETRIES` retry attempts.

     The point of the heuristic is to avoid the latency/cost of OCR when `pypdf` can already pull clean text out of the PDF.

2. **Conversion artifacts**: For non-text inputs (PDF, DOCX, etc.) a hidden markdown companion attachment is created (`content_type=text/markdown`, `conversion_from=<original.key>`). Conversation attachments create the companion lazily on the first chat turn that needs RAG; project attachments create it at upload time (see [Project Attachments](#project-attachments)). Conversation companions reuse the original's S3 key (the companion overwrites the original blob); project companions are stored at a distinct `<original.key>.md` blob so the original binary remains available for direct retrieval.

3. **Hybrid context delivery**: On every chat turn, each text attachment is exposed to the LLM in one of two modes (described in detail below):
   - **`full-context`**: small enough conversation documents are inlined directly into the system instructions so the LLM can read them without calling a tool.
   - **`tool_call_only`**: oversized or evicted conversation documents, **and every project document**, stay reachable via the `document_search_rag` tool, plus `summarize` for conversation files or `summarize_project` for project-library files.

4. **RAG (Retrieval-Augmented Generation)**:
   - Converted text is indexed in a vector database (Albert collection or Find index). Conversations and projects each have their own collection.
   - The LLM uses the `document_search_rag` tool to query relevant chunks. When the conversation belongs to a project, both the conversation collection and the project collection are searched in a single call. The tool accepts an optional `document_id` argument to target a single attachment from either scope.

5. **Summarization tool** if needed (also accepts `document_id`).

#### Documents listing in system instructions

When at least one text attachment exists, the assembled system instruction includes a JSON listing of the attached documents. This is the LLM's "table of contents" — it tells the model which documents are present, which are inlined as full content, and which can only be reached via tools.

Listing shape (sent on every turn):

```json
{
  "documents_order": "newest_to_oldest",
  "documents": [
    {
      "document_id": "<UUID>",
      "title": "report.pdf",
      "access": "full-context",
      "content": "<full markdown of the document>",
      "info": "last_uploaded_document"
    },
    {
      "document_id": "<UUID>",
      "title": "big_dataset.csv",
      "access": "tool_call_only",
      "content": "available via tools",
      "info": null
    }
  ],
  "project_documents": [
    {
      "document_id": "<UUID>",
      "title": "team-handbook.pdf",
      "access": "tool_call_only",
      "content": null,
      "info": "first_uploaded_document"
    }
  ],
  "note": "Documents marked 'tool_call_only' are accessible through tools like RAG search or summary. Documents marked 'full-context' can be directly manipulated by you, ... Entries listed under 'project_documents' come from the user's project library and are shared across every conversation in this project."
}
```

Notes:
- `document_id` is the attachment's UUID and is the value the model passes back to `document_search_rag(document_id=...)`, `summarize(document_id=...)`, or `summarize_project(document_id=...)` to target a specific document. The id MUST come from the matching array (`documents` ↔ `summarize`, `project_documents` ↔ `summarize_project`); cross-array ids are rejected as IDOR violations.
- `info` flags the first and last uploaded documents to help the LLM reason about temporal context. `documents` and `project_documents` carry their own independent `info` ordering.
- `access` is the per-doc decision made by the inlining policy described below.
- `project_documents` is present **only** when the conversation belongs to a project that has at least one indexable file. Every entry under `project_documents` is `tool_call_only` - project files do not compete for the inlining budget. The key is dropped from the JSON entirely (not rendered as `null` or `[]`) when no project files exist.

#### Inlining policy and FIFO eviction

The decision of which documents are inlined as `full-context` vs left as `tool_call_only` is made by `chat/document_context_builder.py:build_documents_listing` on each turn (called via `_build_document_context_instruction` in `chat/clients/pydantic_ai.py`):

1. Compute budgets in tokens (`chat/clients/pydantic_ai.py` subtracts the security buffer once, then splits the remainder):
   ```text
   document_budget = max(int(model.max_token_context * DOCUMENT_CONTEXT_BUDGET_RATIO)
                         - DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS, 0)
   ```
   The conversation history budget (summarization trigger) uses the other share:
   `message_token_budget = max(int(usable_context * (1 - DOCUMENT_CONTEXT_BUDGET_RATIO)), 0)`.
   `build_document_context_instruction` receives `usable_context` as its `max_token_context` argument (buffer already applied).
2. Load all text attachments from object storage **in parallel** (`asyncio.gather`). Attachments that fail to load are marked `tool_call_only` with their failure logged; other documents are not affected.
3. Iterate documents oldest-first (`order_by("created_at", "id")`). For each document:
   - If its token count exceeds the whole budget alone → keep `tool_call_only`.
   - Otherwise, while adding it would overflow the budget, **evict the oldest currently-inlined document** (FIFO): demote it to `tool_call_only`, free its tokens.
   - Once it fits, mark it `full-context` and inline its content.
4. Edge cases:
   - If the model has no `max_token_context` configured → all documents stay `tool_call_only` (warning logged).
   - If `DOCUMENT_CONTEXT_BUDGET_RATIO` is `0` → all documents stay `tool_call_only`.

Token estimation uses `tiktoken` with the `cl100k_base` encoding (GPT-4 tokenizer). For non-OpenAI models (Mistral, Llama, Anthropic) actual usage may run 5-15% higher; the security buffer absorbs that drift.

The assembled instruction is **cached** per turn keyed on:
`conversation_id`, `user_id`, `model_hrid`, `model.max_token_context`, `DOCUMENT_CONTEXT_BUDGET_RATIO`, `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS`, and a fingerprint of `(attachment.id, attachment.updated_at)` for every text attachment - **conversation and project text attachments both contribute to the fingerprint**. Any attachment add / remove / edit (including project files), or any settings change, invalidates the cache. TTL is 30 minutes (`CACHE_TIMEOUT`).

#### Conversation history summarization

When `message_token_budget` is exceeded, `chat/agents/history_processors.py` calls a separate summarization model (`LLM_SUMMARIZATION_MODEL_HRID`) and stores the result on the conversation (`history_summary`, `history_summary_checkpoint`). This runs at the **start of a new user turn**, before `agent.iter`, against **stored** `pydantic_messages` from previous turns only (the current user prompt is extracted separately and is not in that list yet). That stored history usually ends on an assistant `ModelResponse`.

1. **Trigger**: estimated tokens in the active history slice exceed `message_token_budget` (see formulas above) and there are new messages after the last checkpoint.
2. **After a summary**: the model receives the stored summary text (dynamic instruction) plus the last `CONVERSATION_SUMMARY_CONTEXT_MESSAGES` `ModelMessage` entries before the checkpoint. Use an **even** value so the retained window starts on a user `ModelRequest` in a plain user/assistant alternation (tool messages can break parity).
3. **Summary length**: capped by `CONVERSATION_SUMMARY_MAX_TOKENS` on the summarization LLM call.
4. **Disable summarization** without changing document budgets: remove `max_token_context` from the chat model in `LLM_CONFIGURATIONS`, or set `message_token_budget` to zero (`DOCUMENT_CONTEXT_BUDGET_RATIO=1` also zeroes it but reallocates all `usable_context` to documents).

The security buffer is **not** a dedicated reserve for system prompts, tool schemas, or completion tokens; those are added on top of the planned document/history split. Size the buffer (and/or plan `max_token_context` below the model nominal window) to leave headroom for that overhead.

#### Targeted document operations (`document_id`)

Three tools accept an optional `document_id` argument, each with its own IDOR boundary:

| Tool | Default scope (no `document_id`) | `document_id` resolves against |
|---|---|---|
| `document_search_rag(query, document_id=None)` | Conversation collection + project collection (when applicable) | Conversation text attachments + project text attachments. |
| `summarize(instructions=None, document_id=None)` | Every conversation text attachment | Conversation text attachments only. |
| `summarize_project(instructions=None, document_id=None)` (registered only when the conversation belongs to a project) | Every project text attachment | Project text attachments only. |

For all three tools, the resolution is:
1. Validate the value is a UUID.
2. Look it up against the tool-specific attachment set (see table). **If the UUID is not in that set, the tool raises `ModelRetry` ("not found")** - this is the IDOR boundary. The boundaries are deliberately strict per-tool: `summarize` rejects a project-attachment id (the LLM should call `summarize_project` instead), `summarize_project` rejects a conversation-attachment id, and `document_search_rag` is the only widening tool because the model cannot tell from the question alone which scope to prefer.
3. For `document_search_rag`, forward the resolved attachment to the backend, preferring the per-document id (`rag_document_id`) recorded at index time over the file name:
   - **Albert**: sends `document_ids: [<int>]` on `/v1/search`. This is collection-aware and unambiguous, which matters when conversation and project collections both carry a file with the same name.
   - **Find**: per-document id is not available; the backend currently ignores both `document_id` and `document_name` filters and runs a plain query (known gap, follow-up work).
   - When `rag_document_id` is missing (e.g. older attachment, Find backend), Albert falls back to a `metadata_filters: { key: "document_name", value: ..., type: "eq" }` clause; the file name is `report.pdf.md` stripped to `report.pdf` if the attachment is a converted markdown copy.

The two `summarize*` tools share the same chunk-and-merge pipeline (`_summarize_text_attachments` in `chat/tools/document_summarize.py`) - they only differ in which attachment set they fetch and which scope-specific soft-fail message they emit ("no docs in this conversation" vs. "no project files").

#### Empty filtered RAG result → `ModelRetry`

If the model targeted a document via `document_id` and the backend returned no results, `document_search_rag` raises `ModelRetry` with explicit guidance: either retry without `document_id` (and explicitly tell the user the search was broadened) or stop and tell the user the targeted document does not contain the requested information. This replaces an earlier silent fallback that quietly widened scope without informing the model. See `chat/tools/document_search_rag.py` for the exact text.

#### Find backend: known limitations

`FindRagBackend` does not have feature parity with `AlbertRagBackend`. Operators selecting `RAG_DOCUMENT_SEARCH_BACKEND` should account for the following gaps:

| Capability | Albert | Find |
|---|---|---|
| Per-document id captured at index time (`rag_document_id`) | ✅ | ❌ |
| Per-attachment delete (`DELETE /v1/documents/{id}`) | ✅ removes chunks immediately | ❌ no-op; chunks remain searchable until the parent conversation/project is deleted and the whole collection is dropped |
| `document_id`-targeted RAG search | ✅ filtered to one document | ❌ raises `FindFilterUnsupportedError` instead of silently returning full-collection hits |
| `document_name`-targeted fallback | ✅ `metadata_filters` clause | ❌ raises `FindFilterUnsupportedError` |
| RAG enable-gate (`_check_should_enable_rag`) | ✅ fires once any attachment has `rag_document_id` set | ❌ never fires - Find never populates `rag_document_id`, so the agent runs without RAG tools registered |

User-visible consequences when running Find:
- Deleting a sensitive attachment from a project does **not** remove its chunks from the search index. They keep surfacing in RAG searches until the project itself is deleted.
- A `document_id`-targeted search fails fast with `FindFilterUnsupportedError` rather than silently returning unrelated hits. Callers (e.g. the `document_search_rag` tool) need to catch this and surface a clear "this backend cannot scope to one document; retry without document_id or switch backend" message.
- **The agent does not register any RAG tools.** Because the enable-gate uses `rag_document_id` as the "actually indexed" signal and Find never sets it, even successful Find indexing is invisible to the gate. The model answers from training data alone unless documents arrive in the current message. Selecting Find is therefore a deliberate "no per-document features, no RAG tools" choice until per-document ids are wired in.

The Albert backend is the recommended choice for any deployment that needs per-document control or RAG tooling. Wiring per-document operations into Find is a known follow-up.

### Processing Strategy Decision Tree

**Decision logic**:
- **No documents anywhere**: Standard conversation, no RAG tools registered.
- **Images on this turn**: Send as direct (presigned) URLs to the LLM.
- **PDFs on this turn**: Send as direct (presigned) URLs to the LLM.
- **Other documents present** (this turn, the conversation, **or** the parent project): Convert to Markdown, build the documents listing (and `project_documents` listing if applicable) for the system instruction, inline what fits the budget as `full-context`, expose the rest via the `document_search_rag`, `summarize`, and (when in a project) `summarize_project` tools (with optional `document_id` targeting). RAG search covers the conversation collection and the project collection together.

The RAG-tool gate (`AIAgentService._check_should_enable_rag`) keys off `rag_document_id` - the "actually indexed" signal written only after `parse_and_store_document` round-trips successfully through the RAG backend - not raw `READY` upload state. It returns true when any of:
- the user message carries an in-message document upload,
- the conversation owns at least one attachment with a non-empty `rag_document_id`,
- the conversation belongs to a project that owns at least one such attachment.

A `READY` attachment whose `rag_document_id` is null (e.g. parse succeeded but the backend store call failed, or the backend simply never returns ids) does not trip the gate. This is why the Find backend - which never returns a per-document id - leaves RAG disabled even when its index call succeeds, as called out in the Find section above.

---

## Configuration

### Environment Variables

| Variable                                     | Default        | Description                                                |
|----------------------------------------------|----------------|------------------------------------------------------------|
| `ATTACHMENT_MAX_SIZE`                        | Configurable   | Maximum file size in bytes                                 |
| `ATTACHMENT_CHECK_UNSAFE_MIME_TYPES_ENABLED` | `True`         | Enable/disable MIME type validation                        |
| `AWS_S3_UPLOAD_POLICY_EXPIRATION`            | 3600           | Presigned URL expiration (seconds)                         |
| `AWS_S3_RETRIEVE_POLICY_EXPIRATION`          | 3600           | Presigned retrieval URL expiration (seconds)               |
| `AWS_S3_DOMAIN_REPLACE`                      | None           | Alternative S3 domain for presigned URLs (for development) |
| `MALWARE_DETECTION_BACKEND`                  | `DummyBackend` | Malware scanning backend class                             |
| `MALWARE_DETECTION_PARAMETERS`               | `{}`           | Backend-specific configuration                             |
| `RAG_FILES_ACCEPTED_FORMATS`                 | See below      | List of MIME types accepted for file uploads               |
| `RAG_DOCUMENT_PARSER`                        | `AlbertParser` | Import path of the parser that converts uploads to Markdown (PDF -> Albert API, ODT -> odfdo, others -> MarkItDown) |
| `RAG_DOCUMENT_SEARCH_BACKEND`                | `AlbertRagBackend` | Import path of the vector-search backend used for indexing and search (Albert or Find) |
| `PROJECT_FILES_MAX_COUNT`                    | `10`           | Max non-image attachments per project (excludes hidden markdown companions). Enforced at upload-time in `ChatProjectAttachmentViewSet`. Bounds per-turn system-prompt token cost (every entry contributes to `project_documents` on every conversation turn). |
| `PROJECT_IMAGES_MAX_COUNT`                   | `3`            | Max image attachments per project. Enforced at upload-time. Bounds per-turn vision token cost - every project image is pinned to every turn alongside conversation-message images, and provider request-level image caps (Anthropic ~20/request) clip the trailing entries first. |
| `DOCUMENT_CONTEXT_BUDGET_RATIO`              | `0.5`          | Fraction of `model.max_token_context` reserved for inlined documents (0 disables full-context inlining; everything stays `tool_call_only`) |
| `DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS`    | `10000`        | Tokens subtracted once from `max_token_context` before the document/history split, to absorb tokenizer drift on non-OpenAI models and leave headroom beyond the planned split |

#### RAG_FILES_ACCEPTED_FORMATS

This environment variable controls which file types users are allowed to upload as attachments to conversations.

**Configuration**:
- **Type**: List of strings (comma-separated MIME types when using environment variable)
- **Default value**: Includes a comprehensive list of document and image formats:
  - Microsoft Office documents (`.docx`, `.pptx`, `.xlsx`, `.xls`)
  - Text files (`.txt`, `.csv`)
  - PDF documents (`.pdf`)
  - HTML files
  - Markdown files (`.md`)
  - Outlook messages (`.msg`)
  - Images (`.jpeg`, `.png`, `.gif`, `.webp`)

**Example configuration**:
```ini
# In environment variable (comma-separated)
RAG_FILES_ACCEPTED_FORMATS="application/pdf,text/plain,image/png,image/jpeg"
```

```python
# In Django settings (as a Python list)
RAG_FILES_ACCEPTED_FORMATS = [
    "application/pdf",
    "text/plain",
    "image/png",
    "image/jpeg",
]
```

**How it's used**:
1. **Backend**: The list is exposed via the `/api/v1.0/config/` endpoint as `chat_upload_accept` (MIME types joined with commas)
2. **Frontend**: The configuration is used to validate files before upload in the chat interface:
   - Checks exact MIME type matches
   - Supports wildcard patterns (e.g., `image/*` for all image types)
   - Supports file extension patterns (e.g., `.pdf`)
3. **User experience**: Files that don't match the accepted formats are rejected with a user-friendly error message

**Notes**:

 - This setting controls frontend validation only. Backend validation should also be implemented for security.
 - Future improvements may include per-model file type restrictions.

### Per-model setting: `max_token_context`

Each entry in `LLM_CONFIGURATIONS` accepts a `max_token_context` integer field declaring the model's context window size. When set, it drives document inlining and conversation summarization budgets (`usable_context = max_token_context - DOCUMENT_CONTEXT_SECURITY_BUFFER_TOKENS`; `document_budget = usable_context * DOCUMENT_CONTEXT_BUDGET_RATIO`).

If a model has no `max_token_context`, all of its documents are kept `tool_call_only` regardless of size and a warning is logged on every chat turn. Setting the field accurately matters: too low and small documents get pushed to RAG-only when they could be inlined; too high and the LLM may exceed its real window.

### Storage Configuration

**MinIO (Development)**:
```yaml
# docker-compose.yml
minio:
  image: minio/minio
  environment:
    MINIO_ROOT_USER: minioadmin
    MINIO_ROOT_PASSWORD: minioadmin
  command: server /data --console-address ":9001"
```

---

## Troubleshooting

### LLM Cannot Access Image/PDF

**Possible causes**:
- Presigned URL has expired
- S3 storage is not accessible from the LLM provider
- CORS configuration issues

**Solution**: Check `AWS_S3_RETRIEVE_POLICY_EXPIRATION` and S3 access policies.

### Document Not Appearing in RAG Search

**Possible causes**:
- Document conversion failed
- Vector database indexing failed

**Check logs**: Look for errors in `DocumentConverter` and RAG backend logs.

---

## Related Documentation

- [Installation Guide](installation.md) - S3 storage setup
- [LLM Configuration](llm-configuration.md) - Model capabilities for attachments
- [Architecture](architecture.md) - System overview
- [Tools](tools.md) - Document search and RAG tools

