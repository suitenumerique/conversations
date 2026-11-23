## Architecture

### Global system architecture

![Conversations architecture: web app, backend, background jobs, data stores and external services](assets/architecture.svg)

The backend and the worker both call the LLM providers and the Albert API: the backend for chat prompts and RAG searches, the worker for parsing, indexing and summaries. By default (`FILE_UPLOAD_MODE=presigned_url`) the web app uploads files straight to S3 (dashed line); see [file-upload-modes.md](file-upload-modes.md) for the other modes. Observability (Sentry, Langfuse, PostHog, Prometheus) is optional and not drawn.

### Components

| Component | Role |
|-----------|------|
| Web app | Single-page app. Talks to the backend REST API and reads chat responses as a stream. |
| App API | Django app (`core`, `chat`). Auth, conversations, projects, attachments, and the LLM agent that runs each chat turn and its tools. |
| Django admin | Back office for staff, served by the same Django app. |
| Celery worker | Off-request work: document parsing and RAG indexing, conversation summarization, tabular queries. See [celery.md](celery.md). |
| Celery beat | Schedules periodic tasks (model health polling, inactive collection cleanup, tabular result purge). |
| PostgreSQL | Users, conversations, messages, projects, attachment metadata. |
| Redis | Django cache, rate limiting state, Celery broker and result backend. |
| S3 storage | Attachment files. See [file-upload-modes.md](file-upload-modes.md). |
| LLM providers | Configured in the LLM configuration file. See [llm-configuration.md](llm-configuration.md). |
| Albert API | RAG backend: document parsing, OCR, vector collections and search. See [attachments.md](attachments.md) and [project-file-indexing.md](project-file-indexing.md). |
| OIDC provider | Login. Keycloak in development, ProConnect in production. |
| Web search, MCP, Docs | Optional tool integrations used by the agent. See [tools.md](tools.md). |
| Malware detection | Scans uploads before they are used when a malware backend is configured; the default `DummyBackend` marks all files safe. Reports back through a callback. See [attachments.md](attachments.md#malware-detection). |
| Observability | Errors (Sentry), LLM traces (Langfuse), product analytics (PostHog), metrics (Prometheus). See [logging.md](logging.md) and [metrics.md](metrics.md). |
