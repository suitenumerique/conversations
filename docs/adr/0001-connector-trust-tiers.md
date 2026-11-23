# ADR 0001: MCP connector model and trust tiers

- **Status:** Proposed
- **Date:** 2026-11-19, updated 2026-11-23 to match the implementation
- **Issue:** [#956](https://github.com/suitenumerique/conversations/issues/956), follows [#847](https://github.com/suitenumerique/conversations/issues/847)

## Context

Conversations shipped one MCP connector, data.gouv.fr, wired by hand in
`chat/mcp_servers.py`, configured by `DATAGOUV_CONNECTOR_URL`, with its opt-in
stored as a dedicated boolean on the user (`User.allow_datagouv_connector`).
#847 asks for new connectors to be added through configuration, not code.

A connector is a remote server whose tool names, descriptions and results
enter the model's context, and to which the model sends parts of the user's
conversation. The [trust boundary](../tools.md#trust-boundary) accepted for
data.gouv was set for a state-run server and explicitly asks to be revisited
before the next one ships.

Every later choice (authentication, tool policy, retention, consent) depends
on how far we trust the server.

## Decision

### 1. Three trust tiers

A tier depends on **who operates the server and how far we can hold them to
account**, not on whether its data is public.

| Tier | Definition | Example |
|---|---|---|
| `internal` | Same operator, hosting and IdP as this Conversations instance; we can read or review the code | A Docs MCP server in the same cluster |
| `partner` | A public body or contracted vendor outside our infrastructure, with a named operator and a DPA if personal data can flow | data.gouv.fr, SofIA (ADEME) |
| `user` | Declared by an end user; nobody reviewed it | A user's own GitHub MCP server |

The tiers are `chat.connectors.Tier`. A declaration that omits `tier` is
`partner`.

### 2. Scope: partner connectors only

We build and ship **`partner` connectors only**. `internal` and `user` stay in
the vocabulary so the data model does not have to change later:

- `user` is the hardest case: arbitrary URLs (SSRF), unreviewed tool
  descriptions (prompt injection), and no one to hold to account. Supporting
  it before the catalogue is mature would force every open question below to
  be answered at its strictest. There is no way for an end user to declare a
  connector: only the deployment can.
- `internal` is deferred by choice: partner servers carry the most immediate
  demand.

The tier is **recorded, not enforced** yet (see section 9): nothing in the
code behaves differently per tier. Declaring an `internal` or `user`
connector is therefore a review decision, not something the registry refuses.

Every design choice must still **keep `user` possible**: nothing may assume a
connector is reviewed just because it is declared.

### 3. Connectors are declared by the deployment

Connectors are declared as data in the **`MCP_CONNECTORS` setting**, a JSON
list with one object per connector (see
[Declaring a connector](../tools.md#declaring-a-connector)). Adding a partner
connector is a configuration change: no code, no migration, no frontend
change. Code still owns the behaviours (auth kinds, outage handling,
instructions handling); the declaration only picks among them.

data.gouv is no exception: it is declared in `MCP_CONNECTORS` under the
`datagouv` slug, like any other connector. A deployment that leaves it out of
the list does not offer it and never contacts it.

The registry (`chat/connectors/registry.py`) is the only reader of the
declarations:

- At **startup**, a Django system check (`chat.E101`) fails `manage.py check`
  on any declaration it cannot use: unknown field, invalid slug, duplicate
  slug, unknown feature flag, unsupported auth kind, a `user_oauth` connector
  without `CONNECTORS_TOKEN_ENCRYPTION_KEY` or with a missing client secret.
- At **runtime**, the same declaration is logged
  (`connector_declaration_refused`) and left out, so one typo never costs
  every user their turn.

Who integrates a new partner server: the **operator of the deployment**,
after checking the partner conditions (named operator, DPA when personal data
can flow, OAuth client registered when the server needs one). The decision is
reviewed in the deployment's configuration, not in this repository.

A catalogue editable in the Django admin remains possible later: the
definition is built from a plain dictionary (`ConnectorDefinition.from_dict`),
so a database row can feed it without changing the shape.

### 4. What a connector is

A connector is one `ConnectorDefinition` (`chat/connectors/definition.py`):
frozen, validated data, no I/O, no secret. It is rebuilt from the
declarations each time the registry is read, and other modules read its
fields, never write them.

| Group | Fields | Read by |
|---|---|---|
| Identity | `slug` (`^[a-z0-9_]{1,20}$`), `name` | tool prefix, events, analytics, opt-in, UI |
| Endpoint | `url` (streamable-HTTP endpoint), `tier`, `init_timeout` (default 5 s), `read_timeout` (default 30 s); `0` means no limit | `turn.py`, `runtime.py` |
| Auth | `ConnectorAuth`: `kind` plus references to secrets (`client_secret_env`, `token_env`), never the secret itself | `auth.py`, `oauth.py` |
| Model | `instructions`, written by us, never taken from the server; the forced and unreachable wordings are derived from `name` | `ConnectorToolset`, `UserConnector.instruction()` |
| Access | `feature_flag`: a `FeatureFlags` field gating the connector to a cohort, or `null` for everyone | `UserConnector.for_user`, OAuth views |

Per-turn state lives in `UserConnector` (one connector) and `TurnConnectors`
(all of them), never in the definition.

Rules the model holds to:

- **Three gates.** A connector reaches the agent only when the deployment
  declares it, the user is in its cohort (`feature_flag`), and the user
  opted in to it (`User.allowed_connectors`) or forced it for this turn. A
  `user_oauth` connector also needs the user's account to be linked.
- **Forcing never widens access.** A force stands in for the opt-in only. A
  force the cohort denies is logged (`connector_forced_but_not_enabled`) and
  dropped; a force on an unlinked connector reports it unavailable.
- **Fail closed on configuration.** A declaration the registry cannot fully
  validate (including an unknown feature flag or an unsupported auth kind) is
  not offered at all, never offered with a weaker setting.
- **Fail open on outages.** A connector that cannot be reached, or whose
  authorization server cannot refresh a token, is dropped for the turn; the
  user still gets an answer. When the user forced it, the model is told to say
  so and a `connector_unavailable` notice is streamed.
- **Fresh identity per turn.** The registry, the cohort and the opt-in are
  read again at the start of each turn (`TurnConnectors.for_user`), so leaving
  a cohort or switching a connector off takes effect on the next turn.
- **The server never writes our prompt.** `include_instructions=False` is set
  explicitly on every toolset; the only connector text in the instructions is
  the declaration's `instructions`, carried by `ConnectorToolset` so it reaches
  the model exactly when the tools do.
- **`slug` must not change** once users have opted in: tool names, history,
  opt-ins and credentials are keyed on it. This is documented, not enforced.
- **Streamable HTTP only.** The MCP specification replaced the HTTP+SSE
  transport with Streamable HTTP in its 2025-03-26 revision. `url` is the
  server's streamable-HTTP endpoint and there is no `transport` field; a
  partner offering only the deprecated transport is asked to upgrade. `stdio`
  is excluded because connectors are remote by definition. Adding a
  `transport` field later is an additive change to the declaration.

### 5. Authentication

Authentication is a closed set of kinds in code (`AuthKind`), chosen per
connector by the `auth` object of its declaration. Every kind is resolved by
one function, `connector_client_kwargs(definition, user)`, called per turn;
nothing else in the turn knows how a connector authenticates.

| Kind | State | Use |
|---|---|---|
| `none` (default) | Implemented | Public server, called anonymously (data.gouv.fr). |
| `user_oauth` | Implemented | Each user links their own account on the connector's authorization server (SofIA). |
| `deployment_token` | Named, refused | One secret for the whole deployment, read from `token_env`. Declaring it fails the system check rather than calling the server anonymously. |

**No token passthrough.** The user's ProConnect token is issued to
Conversations; forwarding it to a partner is forbidden by the MCP
authorization specification, since the partner cannot tell a replayed token
from a legitimate one. No auth kind does it.

`user_oauth` follows the MCP authorization specification from the client
side (`chat/connectors/oauth.py`, `chat/views/connectors.py`):

- **Discovery.** The authorization server is found from the MCP server's
  protected resource metadata (RFC 9728), then its own metadata (RFC 8414 or
  OpenID Connect discovery), cached for an hour. A declaration may name the
  `issuer` instead. An issuer without PKCE `S256` is refused.
- **Linking.** Switching the connector on sends the browser through an
  authorization code flow with PKCE `S256`, a random `state` kept in the
  session, and `resource` set to the connector URL (RFC 8707). The callback
  stores the tokens and records the opt-in. The users API refuses to switch
  such a connector on without a link.
- **Storage.** Tokens are stored per user and connector in
  `ConnectorCredential`, encrypted with `CONNECTORS_TOKEN_ENCRYPTION_KEY`
  (Fernet). They never reach logs, analytics, the frontend or the model. The
  admin lists who linked what, never the tokens.
- **Use.** `UserOAuthHTTPAuth` puts the access token on each request,
  refreshes it a minute before expiry and once more on a `401`, locking the
  credential row so concurrent turns never spend a rotating refresh token
  twice.
- **Revocation.** Switching the connector off, or deleting the credential in
  the admin, deletes the tokens and revokes the refresh token. A refresh the
  authorization server refuses unlinks the connector and switches it off: the
  user must link again. An authorization server that cannot be reached keeps
  the link and drops the connector for that turn, like an outage.

When the partner's authorization server signs users in through ProConnect,
the second sign-in is usually silent since the session exists. Token exchange
at ProConnect (RFC 8693) stays a possible future kind; it does not change the
connector's shape.

Any kind that sends the user's identity to a partner makes personal data
flow, so it brings the DPA condition with it.

### 6. Consent

A user's opt-in is the list of connector slugs in `User.allowed_connectors`,
which replaced `User.allow_datagouv_connector` (migration
`core.0017_user_allowed_connectors` carried existing data.gouv opt-ins over as
the `datagouv` slug). It records a choice, not an entitlement: the cohort gate
still applies.

- The users API accepts only slugs the deployment offers, but keeps a slug the
  user already had, so a connector taken offline for a while keeps its users'
  consent.
- `connector_toggled` (PostHog) records each change; the admin can set the list
  on a user's behalf to enrol them in a beta.
- For `user_oauth`, linking the account is the opt-in and unlinking removes it.

The opt-in is **not versioned**: there is no consent notice attached to a
connector, so changing a connector's operator, URL or the data it receives
does not invalidate existing opt-ins. Changing those is a reason to declare a
new slug.

### 7. Defaults per tier

Only the `partner` column is in force, and it describes what the code does for
every connector today, since tiers are not enforced. The other columns record
the direction so later ADRs start from it.

| Policy | `internal` | `partner` (in force) | `user` |
|---|---|---|---|
| Who declares it | The deployment | The deployment (`MCP_CONNECTORS`) | An end user (not possible yet) |
| Egress | Internal network allowed | Any URL the deployment declares; no guard | Public internet only, private ranges blocked, redirects re-checked |
| Auth kinds | Any | `none` or `user_oauth`; never token passthrough | `user_oauth` |
| Server instructions | Refused | Refused | Refused |
| Tool names, descriptions, results | Accepted | Accepted as-is, no filter or cap | Truncated, treated as untrusted |
| Default for a user | Opt-in | Opt-in (empty `allowed_connectors`), or forced per turn | Opt-in |
| Consent | Opt-in | Opt-in by slug; account link for `user_oauth` | Versioned notice required |

### 8. Classification of known servers

| Server | Tier | Auth | Reasoning |
|---|---|---|---|
| data.gouv.fr MCP | `partner` | `none` | Run by a public body (DINUM / Etalab) outside our cluster; public data, but conversation excerpts are sent as tool arguments. |
| SofIA (ADEME) | `partner` | `user_oauth` | Run by a public body outside our cluster; each user signs in on its own authorization server. |
| Docs MCP in the same cluster | `internal` | — | Same operator, hosting and IdP; code reviewable. Out of scope. |
| A user's own GitHub MCP server | `user` | — | Declared by the user, unreviewed, needs the user's own credentials. Out of scope. |

### 9. Decided but not enforced yet

Each of these is a known gap between the policy above and the code. None needs
the connector's shape to change.

- **Tier enforcement.** `tier` is validated and stored, but no behaviour reads
  it: the registry accepts `internal` and `user` declarations, and auth kinds
  do not declare which tiers they allow. Before an `internal` or `user`
  connector ships, the registry should refuse what a tier does not allow.
- **Egress guard.** Calls to the MCP server and to its authorization server go
  through the default HTTP clients, with no check of the target address or of
  redirects. Acceptable while every URL is chosen by the deployment; required
  before `user`.
- **Tool policy.** There is no allowlist, denylist, tool count limit,
  description cap or approval step: tool descriptions are accepted as-is, as
  the trust boundary states for data.gouv. Limits on the number of connectors
  per turn are undecided too; the decision should start from the measured
  token cost of each connector's tool list.
- **Versioned consent notice.** See section 6. Needed before a partner whose
  data handling users must be told about explicitly.
- **Slug immutability.** Documented only. Renaming a slug in `MCP_CONNECTORS`
  orphans opt-ins and credentials.
- **Credentials on account deletion.** Deleting a user cascades to their
  `ConnectorCredential` rows, but does not revoke the refresh tokens at the
  authorization server as unlinking does.

## Consequences

- New partner connectors no longer need a release, only a configuration
  change. `MCP_CONNECTORS` and the OAuth client secrets become
  security-relevant configuration, reviewed like any other deployment secret.
- Startup fails on a broken declaration (`chat.E101`), while a running
  instance survives one, so a mistake is caught at deployment, not by users.
- `User.allow_datagouv_connector` is gone, replaced by
  `User.allowed_connectors`, with data.gouv's opt-ins kept.
- The `DATAGOUV_CONNECTOR_*` settings are gone. A deployment that used them
  declares data.gouv in `MCP_CONNECTORS` instead, keeping the `datagouv` slug
  so existing opt-ins still apply.
- `chat/mcp_servers.py` only re-exports the runtime names, for one release.
- The frontend learns the offered connectors from `GET /config/` (slug, name,
  feature flag; never the URL) and needs no change for a new connector.
- Per-user credentials exist (`ConnectorCredential`), encrypted and revocable.
  A refresh the authorization server refuses switches the connector off, so
  the user has to link again; it is not retried as an outage.
- The trust boundary in `docs/tools.md` applies to the `partner` tier; it
  should link here.
- Supporting `user` connectors later means a way for users to declare one,
  tier enforcement in the registry, the egress guard and a stricter tool
  policy, not reshaping the connector.

## Alternatives considered

- **Connectors defined in code.** Keeps everything reviewed in pull requests,
  but every connector needs a release, which is what #847 wants to avoid.
- **A catalogue in the Django admin.** Lets instance administrators add a
  connector without a redeployment, but makes the database security-relevant
  configuration that needs auditing, and secrets would still live in the
  environment. Deferred: a settings declaration is reviewed with the rest of
  the deployment and validated at startup. `from_dict` keeps the door open.
- **User-declared servers first.** Most flexible, but forces every open
  question to its strictest answer before anything ships.
- **Token passthrough of the ProConnect token.** Forbidden by the MCP
  authorization specification. Per-user OAuth was chosen instead; token
  exchange (RFC 8693) remains a candidate for a future kind.
- **Supporting the legacy HTTP+SSE transport.** It would cover older servers,
  but it is deprecated in the MCP specification, adds a second long-lived
  connection to secure and time out, and a curated partner list does not
  need it.
- **An allowlist of reviewed tool names.** Rejected in the trust boundary:
  it silently freezes a connector's capabilities. It may return as an
  optional per-connector tool policy, not as the default.
