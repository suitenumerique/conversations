# Setup Find for RAG document search

This configuration enables the RAG (Retrieval-Augmented Generation) feature in Conversations,
backed by the [Find](https://github.com/suitenumerique/find) search service:

- Uploaded documents are indexed in Find when attached to a conversation.
- Find is queried during AI generation to retrieve relevant document chunks.

## Prerequisites

Both projects must share the same Docker network. Each `compose.yml` must declare:

```yaml
networks:
  lasuite:
    name: lasuite-network
    driver: bridge
```

And the `find` app service must join it with its network alias:

```yaml
services:
  app:
    networks:
      default: {}
      lasuite:
        aliases:
          - find
```

## Shared Keycloak (development)

Both projects must authenticate users against the same Keycloak realm.
Use the Keycloak bundled with Conversations (`http://localhost:8083`, realm `conversations`).

**In `find/env.d/development/common`**, point all OIDC endpoints at the conversations realm:

```shell
OIDC_OP_JWKS_ENDPOINT=http://nginx:8083/realms/conversations/protocol/openid-connect/certs
OIDC_OP_AUTHORIZATION_ENDPOINT=http://nginx:8083/realms/conversations/protocol/openid-connect/auth
OIDC_OP_TOKEN_ENDPOINT=http://nginx:8083/realms/conversations/protocol/openid-connect/token
OIDC_OP_USER_ENDPOINT=http://nginx:8083/realms/conversations/protocol/openid-connect/userinfo
OIDC_OP_INTROSPECTION_ENDPOINT=http://nginx:8083/realms/conversations/protocol/openid-connect/token/introspect
OIDC_OP_URL=http://localhost:8083/realms/conversations

OIDC_RS_CLIENT_ID=conversations
OIDC_RS_CLIENT_SECRET=ThisIsAnExampleKeyForDevPurposeOnly
```

No changes are needed to `conversations/docker/auth/realm.json`. Find validates incoming
bearer tokens using the existing `conversations` client via token introspection - no
separate `find` client is required.

## Create a Find service for Conversations

Run the following command in the `find` project to register the Conversations service token:

```shell
docker compose exec app python manage.py create_demo
```

This creates a `Service` row with name `conversations` and a known dev token.

## Configure Conversations

Add these settings to `conversations/env.d/development/common`:

```shell
RAG_DOCUMENT_SEARCH_BACKEND="chat.agent_rag.document_rag_backends.find_rag_backend.FindRagBackend"

# Internal URL: conversations container -> find container via lasuite-network
FIND_API_URL=http://find:8000

# Token from the "conversations" Service in Find (created by create_demo above)
FIND_API_KEY=find-api-key-for-conv-with-exactly-50-chars-length

# Store OIDC tokens in session so Find search requests can use the user's bearer token
OIDC_STORE_ACCESS_TOKEN=True
OIDC_STORE_REFRESH_TOKEN=True
OIDC_STORE_REFRESH_TOKEN_KEY="your-32-byte-fernet-key=="
```

`FIND_API_KEY` is used for indexing and deletion (service-to-service).
The user's OIDC access token is used for search requests.

## Startup order

1. Start Conversations with the usual command - this starts the shared Keycloak.
2. Start Find (`make run` in the find repo) - it connects to the shared Keycloak on 
   `lasuite-network`.
3. Run `create_demo` in Find once to seed the service token (only needed after a DB reset).

If you have an ES/OS gui, you can connect to localhost:9200 to inspect your indices.