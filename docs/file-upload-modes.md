# File Upload Modes

This document describes the different modes for handling file uploads in the Conversations application, and how to configure and use them.

## Overview

The application supports two independent configuration points:

1. **`FILE_UPLOAD_MODE`**: how the frontend uploads files (frontend → storage/backend)
2. **`FILE_TO_LLM_MODE`**: how the backend provides files to the LLM (backend → LLM)

Each mode has different trade-offs in terms of security, performance, and LLM accessibility. The two settings can be combined based on your network constraints.

## Configuration

### Frontend upload mode (`FILE_UPLOAD_MODE`)

```bash
# Default: presigned URL upload (backward compatible)
FILE_UPLOAD_MODE=presigned_url

# Frontend uploads directly to backend
FILE_UPLOAD_MODE=backend_to_s3
```

### Backend delivery mode (`FILE_TO_LLM_MODE`)

```bash
# Default: presigned URL mode (backward compatible)
FILE_TO_LLM_MODE=presigned_url

# Backend provides base64-encoded data URLs
FILE_TO_LLM_MODE=backend_base64

# Backend provides temporary URLs through the backend
FILE_TO_LLM_MODE=backend_temporary_url
```

Additional settings for backend temporary URL mode:

```bash
# Base URL to reach backend
FILE_BACKEND_URL="http://localhost:8071"

# Expiration time for temporary URLs (in seconds, default: 180 = 3 minutes)
FILE_BACKEND_TEMPORARY_URL_EXPIRATION=180
```

## Mode Details

### 1. Presigned URL Mode (Default)

**Frontend upload configuration:** `FILE_UPLOAD_MODE=presigned_url`

**Backend delivery configuration:** `FILE_TO_LLM_MODE=presigned_url`

**How it works:**
- Frontend requests a presigned URL from the backend
- Frontend uploads the file directly to S3 using the presigned URL
- Frontend notifies the backend when upload is complete
- Backend initiates malware detection
- Backend returns presigned S3 URLs to the LLM

**Advantages:**
- Files don't pass through the backend server (lower bandwidth usage)
- Faster uploads for large files (direct to S3)
- S3 handles the upload, no backend load
- Backward compatible with existing frontend implementations

**Disadvantages:**
- S3 bucket must be accessible from the frontend
- Presigned URLs can be leaked if not handled carefully
- Frontend needs to handle S3 credentials/configuration

**LLM Access:**
- Images: Presigned S3 URLs with expiration (default: 3 minutes)
- Documents: Presigned S3 URLs with expiration (default: 3 minutes)

**When to use:**
- When frontend has direct access to S3
- When you want to minimize backend load
- When S3 is publicly accessible or accessible via VPN


### 2. Backend Base64 Mode

**Frontend upload configuration:** `FILE_UPLOAD_MODE=backend_to_s3`

**Backend delivery configuration:** `FILE_TO_LLM_MODE=backend_base64`

**How it works:**
- Frontend uploads the file directly to the backend
- Backend stores the file on S3
- Backend reads the file, encodes it as base64, and creates a data URL
- LLM receives the file as a base64-encoded data URL

**Advantages:**
- S3 can be private/internal (not accessible from frontend)
- Files always go through the backend for validation
- No presigned URLs to manage
- Better control over file access
- Data URLs work with all LLMs that support file content

**Disadvantages:**
- Backend memory usage increases (entire file loaded for base64 encoding)
- Slower for very large files (encoding overhead)
- Increased bandwidth on backend
- Data URLs can be very large in responses

**LLM Access:**
- Images: Base64-encoded data URLs (format: `data:image/png;base64,...`)
- Documents: Base64-encoded data URLs (format: `data:application/pdf;base64,...`)

**When to use:**
- When S3 is not accessible from the frontend
- When you want all file uploads to go through the backend
- When the LLM supports base64-encoded data URLs
- For smaller files (< 50MB)


### 3. Backend Temporary URL Mode

**Frontend upload configuration:** `FILE_UPLOAD_MODE=backend_to_s3`

**Backend delivery configuration:** `FILE_TO_LLM_MODE=backend_temporary_url`

**How it works:**
- Frontend uploads the file directly to the backend
- Backend stores the file on S3
- Backend generates a secure temporary access token stored in cache (TTL: 3 minutes by default)
- Backend returns a temporary URL pointing to the backend's file-stream endpoint
- LLM receives the temporary URL and accesses the file through the backend
- Backend validates the token and streams the file content from S3 to the LLM

**Advantages:**
- S3 can be private/internal (not accessible from frontend or LLM directly)
- Files always go through the backend for validation and access control
- LLM doesn't need direct access to S3
- Tokens expire quickly (better security than long-lived presigned URLs)
- No large data URL strings in memory or responses
- Lower backend memory usage than base64 mode
- Centralized file access control through the backend
- Good balance between security and performance

**Disadvantages:**
- LLM must be able to access the backend server
- File streaming goes through the backend (adds some latency)
- Time-limited access (token expires)

**LLM Access:**
- Images: Temporary backend URLs with format `/api/v1.0/file-stream/{temporary_key}/` (token expiration: configurable, default: 3 minutes)
- Documents: Temporary backend URLs with format `/api/v1.0/file-stream/{temporary_key}/` (token expiration: configurable, default: 3 minutes)

**When to use:**
- When S3 is not accessible from the frontend or LLM
- When you want backend control over uploads and file access
- When you want time-limited access to files with centralized control
- When you want the LLM to access files through the backend gateway
- For large files (backend streams directly from S3 without loading entirely into memory)
