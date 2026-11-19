# ADR 0001: MCP connector model and trust tiers

- **Status:** Proposed
- **Date:** 2026-11-19
- **Issue:** [#956](https://github.com/suitenumerique/conversations/issues/956), follows [#847](https://github.com/suitenumerique/conversations/issues/847)

## Context

Conversations ships one MCP connector, data.gouv.fr. It is wired by hand in
`chat/mcp_servers.py`, configured by `DATAGOUV_CONNECTOR_URL`, and its opt-in is
a dedicated boolean on the user (`User.allow_datagouv_connector`). #847 asks
for new connectors to be added through configuration, not code.

A connector is a remote server whose tool names, descriptions and results
enter the model's context, and to which the model sends parts of the user's
conversation. The [trust boundary](../tools.md#trust-boundary) accepted for
data.gouv was set for a state-run server and explicitly asks to be revisited
before the next one ships.

Every later choice (authentication, tool policy, retention, consent) depends
on how far we trust the server. Without a shared vocabulary, each new
connector gets argued from scratch.

## Decision

### 1. Three trust tiers

A tier depends on **who operates the server and how far we can hold them to
account**, not on whether its data is public.

| Tier | Definition | Example |
|---|---|---|
| `internal` | Same operator, hosting and IdP as this Conversations instance; we can read or review the code | A Docs MCP server in the same cluster |
| `partner` | A public body or contracted vendor outside our infrastructure, with a named operator and a DPA if personal data can flow | data.gouv.fr |
| `user` | Declared by an end user; nobody reviewed it | A user's own GitHub MCP server |

### 2. Scope: partner connectors only

We build and ship **`partner` connectors only**. `internal` and `user` stay in
the vocabulary so the data model does not have to change later, but neither
can be created or enabled yet:

- `user` is the hardest case: arbitrary URLs (SSRF), per-user credentials,
  unreviewed tool descriptions (prompt injection), and no one to hold to
  account. Supporting it before the catalogue is mature would force every
  open question below to be answered at its strictest.
- `internal` is deferred by choice: partner servers carry the most immediate
  demand, and the user-delegated authentication they need (see section 7)
  will serve internal servers too once it exists.

Every design choice must still **keep `user` possible**: nothing may assume
a connector is reviewed just because it exists in the database.

### 3. Catalogue first, managed in the Django admin

Connectors are a **catalogue** managed by instance administrators in the
Django admin. Adding a partner connector is an operator action, not a code
change or a deployment. Code still owns the behaviours (auth strategies,
egress guard, tool policy enforcement); the admin only picks among them.

Who integrates a new partner server: an **instance administrator**, after
checking the partner conditions (named operator, DPA when personal data can
flow, consent notice written). The admin form is the checklist.

### 4. What a connector is

A connector is one `ConnectorDefinition`: frozen data, no I/O, built from the
catalogue row at the start of each turn. Other modules read the fields they
own and never write them.

| Group | Fields | Read by |
|---|---|---|
| Identity | `slug` (`^[a-z0-9_]{1,20}$`, immutable), `name`, `description` | UI, tool prefix |
| Endpoint | `url`, `transport` (`streamable_http` only, see below), `tier`, `init_timeout`, `read_timeout` | `egress.py`, `runtime.py` |
| Auth | `AuthSpec`: `kind` + reference to a secret, never the secret | `auth.py` |
| Model | `instructions` (written by us, never taken from the server), `ToolPolicy` | `policy.py` |
| Data | `ConsentNotice` (versioned), `RetentionPolicy` | consent, history, traces |
| Access | `AccessRule`: `flag`, `allowed_roles`, `allowed_orgs`, `default_enabled` | `access.py` |

Rules the model holds to:

- **One way out.** Every network call a connector makes goes through
  `egress_client(definition)`, which applies the guard for its tier.
- **Forcing never widens access.** A forced connector must already be visible
  to the user; forcing only replaces the opt-in.
- **Fail closed.** In `AccessRule`, `None` means "no restriction" and an empty
  set means "nobody", so removing the last allowed org hides the connector.
- **Fresh identity per turn.** Visibility is computed from an identity
  snapshot taken each turn, so losing a role takes effect on the next turn.
- **`slug` is immutable.** Tool names, history and approvals depend on it; the
  admin makes it read-only after creation.
- **We never accept the server's own instructions** (`include_instructions=False`).
- **Streamable HTTP only.** The MCP specification replaced the HTTP+SSE
  transport with Streamable HTTP in its 2025-03-26 revision; Streamable HTTP
  may still stream responses as SSE, but over a single endpoint. We do not
  support the deprecated transport: a partner offering only that is asked to
  upgrade. `stdio` is excluded because connectors are remote by definition.
  `transport` stays a field, so adding a value later is not a schema change.

### 5. Defaults per tier

Only the `partner` column is in force. The others record the direction so
later ADRs start from it.

| Policy | `internal` | `partner` | `user` |
|---|---|---|---|
| Can be created | Not yet | Yes, by an admin | Not yet |
| Egress | Internal network allowed | Public internet only | Public internet only, private ranges blocked, redirects re-checked |
| Auth kinds | Open (see below) | `none` or user-delegated; never token passthrough | Open (see below) |
| Tool descriptions | Accepted | Accepted, truncated | Truncated, treated as untrusted |
| `default_enabled` | May be true | False: opt-in after consent | False |
| Consent notice | Optional | Required | Required |

### 6. Classification of known servers

| Server | Tier | Reasoning |
|---|---|---|
| data.gouv.fr MCP | `partner` | Run by a public body (DINUM / Etalab) outside our cluster; public data, may have user authentication, but conversation excerpts are sent as tool arguments. |
| Docs MCP in the same cluster | `internal` | Same operator, hosting and IdP; code reviewable. Out of scope until delegated auth is decided. |
| A user's own GitHub MCP server | `user` | Declared by the user, unreviewed, needs the user's own credentials. Out of scope. |

### 7. Deliberately left open

These are not decided here. The data model reserves room for each so it can
be decided in a later ADR without a migration of the connector shape.

- **Authentication.** Partner servers may require authentication, and
  ProConnect is expected on both sides: Conversations and the partner each
  sign users in through it. The mechanism is not decided, but these
  constraints are:
  - **No token passthrough.** The user's ProConnect token is issued to
    Conversations; forwarding it to a partner is forbidden by the MCP
    authorization specification, since the partner cannot tell a replayed
    token from a legitimate one.
  - **Candidates**, in order of preference:
    1. *Per-user OAuth following the MCP authorization specification.* The
       partner is the protected resource, its authorization server signs the
       user in through ProConnect (usually silently, since the session
       exists), and Conversations stores an encrypted, revocable refresh token
       per user and connector.
    2. *Token exchange (RFC 8693) at ProConnect*, trading our token for one
       whose audience is the partner. Avoids the second sign-in; depends on
       ProConnect supporting it.
    3. *A service key plus the user's identity asserted by us.* Simplest, but
       the partner has to trust our assertion; acceptable only under contract.
  - `AuthSpec.kind` is an open enum (`none` today), and each `AuthStrategy`
    declares its `allowed_tiers`.
  - Any kind that sends the user's identity to a partner makes personal data
    flow, so it brings the DPA condition with it and must be stated in the
    consent notice.
- **Tool limits.** `ToolPolicy` carries `allow`, `deny`, `max_tools`,
  `max_description_chars`, `read_only_only` and `require_approval`. The values
  are undecided; until they are, partner connectors get a description cap and
  no other filter, matching today's data.gouv behaviour. Limits on the number
  of connectors per turn are undecided too; the decision should start from the
  measured token cost of each connector's tool list.
- **Consent handling.** The shape is decided, the flow is not. The connector
  carries a versioned `ConsentNotice` (operator, data sent, operator
  retention). A user's opt-in is stored per user, per connector `slug`, with
  the notice version accepted and the date. Changing the operator, URL or data
  sent must bump the version, and a bumped version invalidates the opt-in.
  This replaces `User.allow_datagouv_connector`.

## Consequences

- New partner connectors no longer need a release, but the catalogue becomes
  security-relevant configuration: admin access to it must be restricted and
  changes to it audited.
- The catalogue row and the frozen definition are two shapes of one thing:
  the row is editable, the definition a per-turn snapshot of it. The tests
  must check that one always builds the other.
- `User.allow_datagouv_connector` is migrated to the per-connector consent
  record, with data.gouv's current opt-ins kept under notice version 1.
- `DATAGOUV_CONNECTOR_URL` becomes a data migration seeding the catalogue.
- Authenticated partners will need per-user credential storage (encrypted,
  revocable on disconnect and on account deletion), and the turn must handle
  an expired or revoked credential as a reason to ask the user to reconnect,
  not as an outage.
- The trust boundary in `docs/tools.md` now applies to the `partner` tier and
  links here.
- Supporting `user` connectors later means writing the egress guard, an auth
  kind with per-user credentials and stricter tool defaults, not reshaping the
  connector.

## Alternatives considered

- **Connectors defined in code or settings files.** Keeps everything reviewed
  in pull requests, but every connector needs a deployment, which is what #847
  wants to avoid.
- **User-declared servers first.** Most flexible, but forces every open
  question to its strictest answer before anything ships.
- **Supporting the legacy HTTP+SSE transport.** It would cover older servers,
  but it is deprecated in the MCP specification, adds a second long-lived
  connection to secure and time out, and a curated partner catalogue does not
  need it.
- **An allowlist of reviewed tool names.** Rejected in the trust boundary:
  it silently freezes a connector's capabilities. `ToolPolicy.allow` stays
  available per connector, not as the default.
