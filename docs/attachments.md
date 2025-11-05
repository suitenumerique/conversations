# Conversation Attachments

This document describes how conversation attachments work in the Conversations application, including the upload process, security measures, and how documents are processed for use with Large Language Models (LLMs).

## Table of Contents

- [Overview](#overview)
- [Supported Attachment Types](#supported-attachment-types)
- [Architecture & Flow](#architecture--flow)
  - [High-Level Overview](#high-level-overview)
  - [Detailed Technical Flow](#detailed-technical-flow)
- [Security & Validation](#security--validation)
  - [MIME Type Validation](#mime-type-validation)
  - [Malware Detection](#malware-detection)
- [Document Processing for LLMs](#document-processing-for-llms)
  - [Image Attachments](#image-attachments)
  - [PDF Documents](#pdf-documents)
  - [Other Document Types](#other-document-types)
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
one non-PDF/image document is attached, the system enables:
 - a **Retrieval-Augmented Generation (RAG)** search tool to allow the LLM to query relevant sections of the documents.
 - a **summarization tool** to provide document summaries on user request.
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

1. **Document parsing**: When a document is uploaded, it's parsed using the `AlbertRagBackend` class.

2. **Conversion to Markdown**: Documents are converted using **MarkItDown** library or using the "Albert API" for PDFs.

3. **RAG (Retrieval-Augmented Generation)**:
   - Converted text is indexed in a vector database
   - The LLM uses a `document_rag_search` tool to query relevant sections
   - Only relevant chunks are sent to the LLM to fit context windows

4. **Summarization tool** if needed.

### Processing Strategy Decision Tree

**Decision logic**:
- **No documents**: Standard conversation
- **Images**: Send as direct (presigned) URLs to the LLM
- **Only PDFs**: Send as direct (presigned) URLs to the LLM
- **Other documents present**: Enable RAG search tool + convert to Markdown

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

