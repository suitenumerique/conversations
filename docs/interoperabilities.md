# Interoperability with La Suite Docs

Conversations talks to **La Suite Docs** in two ways: **"Edit in Docs"** sends an
assistant reply to Docs, and **"Read a Docs link"** lets the Assistant read a Docs
document whose link the user pastes. Both call Docs as the user (see
[How authentication works](#how-authentication-works-resource-server)).

## What "Edit in Docs" does

**"Edit in Docs"** turns an assistant reply into a real, editable document in
**La Suite Docs**. In the actions menu under an assistant message, the user clicks
**"Edit in Docs"**: Conversations creates a new Docs document from that message and
opens it in a new browser tab, where the user can keep refining the text in a full
editor.

What to expect as a user:

- **Every click creates a brand-new document.** It never overwrites a previous one,
  and there is no link kept between a message and a document.
- **Only assistant messages with text** can be sent. Images and attachments from the
  message are not transferred.
- **The button only appears when the deployment is connected to a Docs instance**
  (see `DOCS_BASE_URL` in [env.md](env.md)).

```
┌───────────┐  click "Edit in Docs"   ┌───────────────┐  create document   ┌──────────┐
│  Browser  │ ──────────────────────► │ Conversations │ ─────────────────► │   Docs   │
└───────────┘                         └───────────────┘   (as the user)    └──────────┘
       ▲                                                                          │
       └──────────────────────── opens the new document ◄────────────────────────┘
```

## How authentication works (resource server)

The interesting part is that Conversations creates the document **as the user** —
no shared service account, no extra password.

Both applications trust the **same identity provider** (Keycloak locally, ProConnect
in staging/production). When the user signs into Conversations, their OIDC **access
token** is kept in their session. To create the document, Conversations calls the
Docs API and forwards that access token as a `Bearer` credential — nothing more.

Docs plays the role of an OAuth 2.0 **resource server**: rather than running its own
login for this call, it takes the incoming token and asks the identity provider
*"is this token valid, and who does it belong to?"* (token introspection). If the
token is active and carries the expected audience and issuer, Docs looks up the
matching user and creates the document on their behalf.

```
   Conversations ──► Docs ──► Identity provider
   "here is the     "is this token       ✓ active, right audience/issuer
    user's token"    still good,         ► Docs creates the doc as that user
                     and whose is it?"
```

Two consequences worth remembering:

- **No user provisioning.** Docs only recognizes a user who has **already logged into
  Docs at least once**. A brand-new user is rejected — the resource server does not
  create accounts.
- **The token must still be valid.** Access tokens are short-lived. If one expires
  before the call, Docs rejects it and the user is asked to sign in again.
  Conversations can refresh the token automatically when refresh-token storage is
  enabled (`OIDC_STORE_REFRESH_TOKEN`).

## Local development

The same feature can be exercised locally in two ways, depending on which identity
provider you want to test against. Both run via Tilt against the local kind cluster.

### 1. Local Keycloak + local Docs

```bash
make start-tilt-keycloak   # DEV_ENV=dev
```

Conversations and a **local Docs** instance both point at the **local Keycloak**
(realm `conversations`). Because they share the same Keycloak, the access token minted
for Conversations is accepted by Docs. Here `DOCS_BASE_URL` points at the local Docs
ingress (`https://docs.127.0.0.1.nip.io/`).

This is the simplest setup: everything runs on your machine and you control the
identity provider.

### 2. Staging ProConnect + staging Docs

```bash
make start-tilt-proconnect   # DEV_ENV=dev-proconnect
```

Conversations authenticates against **ProConnect** (AgentConnect `integ01`) instead of
the local Keycloak. In this mode `DOCS_BASE_URL` must point at a **ProConnect-federated
Docs** (the shared staging instance,
`https://impress-staging.beta.numerique.gouv.fr`) — a local Docs wired to Keycloak
would reject the ProConnect token.

ProConnect client credentials are not committed: Tilt loads them from
`env.d/development/kube-secret` into the `secret-dev` Kubernetes secret, and the
ProConnect overlay reads them via `secretKeyRef`.

> Both setups require the local TLS trust chain (`mkcert`) so Conversations can reach
> Docs and the identity provider over HTTPS through the ingress.

## Limitations

- Only **assistant messages with text** are eligible.
- The message content is treated as markdown; attachments and images are not
  transferred.
- Each action **always creates a new document**; there is no update of an existing one.
- A user who has **never logged into Docs** cannot use the feature (the resource
  server does not provision users).

## Read a Docs link

When a user pastes a link to a document on the connected Docs instance, the
Assistant reads that document before answering. The user only sees the
"document parsing" indicator listing the pasted links; snapshots do not show up as
attachments in the UI.

### Flow

1. Before the model runs, Conversations looks for **Docs links** in the **current**
   user message only. A Docs link has the same scheme and host as `DOCS_BASE_URL`
   and a `docs/<uuid>/` path under it (query strings and fragments are ignored).
   At most `DOCS_LINKS_MAX_PER_MESSAGE` links are read per message; extra links are
   ignored and logged.
2. For each link, Conversations calls
   `GET {DOCS_BASE_URL}/external_api/v1.0/documents/{uuid}/formatted-content/?content_format=markdown`
   with the user's access token. The pasted URL itself is never fetched: the request
   is always built from `DOCS_BASE_URL` and the document id.
3. The markdown is stored as a conversation attachment (a **Docs snapshot**) and
   indexed like an uploaded file. Small documents are then put directly in the
   model's context and large ones are reached through document search (RAG), with
   the same budget as uploads.

```
┌───────────┐  message with a     ┌───────────────┐  formatted-content   ┌──────────┐
│  Browser  │  Docs link          │ Conversations │  (as the user)       │   Docs   │
│           │ ──────────────────► │               │ ───────────────────► │          │
└───────────┘                     └───────────────┘ ◄─────────────────── └──────────┘
                                          │            markdown
                                          ▼
                              snapshot attachment → inline or RAG → model
```

### Snapshot and replace

- The content is read **once**, when the link is pasted. Later edits in Docs are not
  seen until the user pastes the link again.
- There is **one snapshot per Docs document per conversation**. Pasting the same link
  again deletes the previous snapshot (stored file, RAG document and attachment row)
  and stores a fresh one.
- The model is told which attached document each pasted link points to. Without this,
  the snapshot is only listed by file name, and the model may answer that it cannot open
  the URL.

### When a document cannot be read

A failed read never aborts the turn: the other documents are still used, and the
model is told why the document is missing so it can explain it to the user:

| Docs answer                   | What the model is told                               |
|-------------------------------|------------------------------------------------------|
| 400, 401, or no access token  | The Docs session expired / the user never signed in  |
| 403                           | The user has no access to the document               |
| 404                           | The document does not exist or was deleted           |
| 5xx, timeout, network error, non-JSON answer | Docs is unavailable                                  |
| Content over `ATTACHMENT_MAX_SIZE` | The document is too large                       |
| Empty or whitespace-only content | The document is empty                           |
| Snapshot could not be stored (S3 or database error) | The document could not be saved; try again later |

A 403 is also logged as a warning: it is what Docs answers when the
`formatted_content` action is not allowed (see below).

### Enabling it

- On Conversations: set `DOCS_BASE_URL`, enable `FEATURE_FLAG_DOCUMENT_UPLOAD` and set
  `FEATURE_FLAG_DOCS_LINK_FETCHING` (see [env.md](env.md)). The feature is off unless
  all three are set.
- **On Docs (operator prerequisite):** the `formatted_content` action is **not** in
  Docs' default `EXTERNAL_API["documents"]["actions"]`, and the resource server
  rejects with a 403 every action missing from that list. Add `"formatted_content"`
  to it.

### Limitations

- Only the document's **text** is read, as markdown; images are not transferred.
- **No live sync**: the snapshot does not follow later edits in Docs (paste the link
  again to refresh it).
- As for "Edit in Docs", a user who has **never logged into Docs** cannot use it.
- Content from a shared document is trusted like an uploaded file (same prompt
  injection risk, no malware scan since it is markdown generated by Docs).

## References

- `docs/docs/resource_server.md` (Docs repo) — using Docs as a resource server.
- `django-lasuite/documentation/how-to-use-oidc-call-to-resource-server.md` —
  calling a resource server from the OIDC backend.
