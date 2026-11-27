# ADR 0001: MCP connector model and trust tiers

- **Status:** Proposed
- **Date:** 2026-11-19, updated 2026-11-27 with the review decisions of #967
- **Issue:** [#956](https://github.com/suitenumerique/conversations/issues/956), follows [#847](https://github.com/suitenumerique/conversations/issues/847)
- **Delivered by:** #1005 (connector model, `MCP_CONNECTORS`), #985 (consent, force, UI),
  #986 (lifecycle), #987 (per-user authentication)

This record states decisions. Where a decision is delivered by an issue still
open, the text names it; everything else describes the code as it is.

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

The tiers are `chat.connectors.Tier`. **`tier` is required**: a declaration
that does not say how far we trust the server is refused, since defaulting it
would contradict failing closed on configuration (section 4).

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
connector is a configuration change: no code, no migration. Code still owns
the behaviours (outage handling, instructions handling, and auth kinds from
#987); the declaration only picks among them.

data.gouv is no exception: it is declared in `MCP_CONNECTORS` under the
`datagouv` slug, like any other connector. A deployment that leaves it out of
the list does not offer it and never contacts it.

The registry (`chat/connectors/registry.py`) is the only reader of the
declarations, read again on every turn:

- At **startup**, a Django system check (`chat.E101`) fails `manage.py check`,
  and with it `migrate` and `runserver`, on any declaration it cannot use:
  invalid JSON, a value that is not a list, an unknown field, a missing or
  unknown `tier`, a bad, duplicate or overlapping slug, an unknown feature
  flag, a malformed URL, a negative or non-finite timeout. #987 adds the
  authentication cases (unsupported auth kind, missing `issuer`, missing
  encryption key).
- In **deployment**, the Helm migrate job fails and shows the error. Its
  wait-for-the-database loop only probes the connection and runs no system
  check, so a configuration error is not mistaken for a database still
  starting.
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
| Identity | `slug` (`^[a-z0-9_]{1,20}$`), `name` (one string, shown as-is in every language) | tool prefix, events, analytics, opt-in, UI |
| Endpoint | `url` (http or https streamable-HTTP endpoint), `tier`, `init_timeout` (default 5 s), `read_timeout` (default 30 s); `0` means no limit | `turn.py`, `runtime.py` |
| Model | `instructions`, written by us, never taken from the server; the forced and unreachable wordings are derived from `name` | `ConnectorToolset`, `UserConnector.instruction()` |
| Access | `feature_flag`: a `FeatureFlags` toggle gating the connector to a cohort, or absent for everyone | `UserConnector.for_user` |
| Added by later issues | `description` with per-language values (#985), `retired` (#986), `auth` (#987) | UI, lifecycle task, `auth.py` |

Per-turn state lives in `UserConnector` (one connector) and `TurnConnectors`
(all of them), never in the definition.

Rules the model holds to:

- **Three gates.** A connector reaches the agent only when the deployment
  declares it, the user is in its cohort (`feature_flag`), and the user
  opted in to it or forced it for this turn. A `user_oauth` connector also
  needs the user's account to be linked (#987).
- **Forcing never widens access.** A force stands in for the opt-in only. A
  force the cohort denies, or one on an undeclared connector, is logged
  (`connector_forced_but_not_enabled`) and dropped.
- **Fail closed on configuration.** A declaration the registry cannot fully
  validate is not offered at all, never offered with a weaker setting.
- **Fail open on outages.** A connector that cannot be reached is dropped for
  the turn; the user still gets an answer. When the user forced it, the model
  is told to say so and a `connector_unavailable` notice naming the slug is
  streamed. Each connector is connected on its own deadline and fails on its
  own.
- **Fresh identity per turn.** The registry, the cohort and the opt-in are
  read again at the start of each turn (`TurnConnectors.for_user`), so leaving
  a cohort or switching a connector off takes effect on the next turn.
- **The server never writes our prompt.** `include_instructions=False` is set
  explicitly on every toolset; the only connector text in the instructions is
  the declaration's `instructions`, carried by `ConnectorToolset` so it reaches
  the model exactly when the tools do. Tool names, descriptions and results
  are **not filtered** (section 7).
- **No two connectors share a tool name.** Slugs whose prefixes overlap
  (`geo` and `geo_ign`) are refused, since their servers could publish the same
  tool name, which ends the agent run.
- **`slug` must not change** once users have opted in: tool names, history,
  opt-ins and credentials are keyed on it. A new operator or URL means a new
  slug.
- **Streamable HTTP only.** The MCP specification replaced the HTTP+SSE
  transport with Streamable HTTP in its 2025-03-26 revision. `url` is the
  server's streamable-HTTP endpoint and there is no `transport` field; a
  partner offering only the deprecated transport is asked to upgrade. `stdio`
  is excluded because connectors are remote by definition. Adding a
  `transport` field later is an additive change to the declaration.

### 5. Authentication (#987)

Authentication is a closed set of kinds in code (`AuthKind`), chosen per
connector by the `auth` object of its declaration and resolved in a single
place. Until #987, no `auth` field is accepted and every connector is called
anonymously.

| Kind | Use |
|---|---|
| `none` (default) | Public server, called anonymously (data.gouv.fr). The only kind today. |
| `user_oauth` | Each user links their own account on the connector's authorization server (SofIA). Public clients (PKCE only) are allowed. |
| `deployment_token` | Named, refused: declaring it fails the system check rather than calling the server anonymously. |

**No token passthrough.** The user's ProConnect token is issued to
Conversations; forwarding it to a partner is forbidden by the MCP
authorization specification, since the partner cannot tell a replayed token
from a legitimate one. No auth kind does it.

`user_oauth` follows the MCP authorization specification from the client
side, with every URL pinned by the deployment:

- **Issuer.** `issuer` is required. Linking is refused, and logged, when the
  MCP server's protected resource metadata (RFC 9728) does not list the
  declared issuer. Authorization, token and revocation endpoints come from
  the issuer's own metadata only (RFC 8414 or OpenID Connect discovery).
- **PKCE.** An issuer whose metadata has no `code_challenge_methods_supported`,
  or does not list `S256` in it, is refused.
- **Linking.** An authorization code flow with PKCE `S256`, a random `state`
  kept in the session, and `resource` set to the connector URL (RFC 8707).
  Linking the account is the opt-in.
- **Storage.** Tokens are stored per user and connector in an encrypted
  `ConnectorCredential` that also records the `resource` and `issuer` it was
  issued for. When either no longer matches the declaration, the token is not
  sent and the user links again. Tokens never reach logs, analytics, the
  frontend or the model.
- **Use.** The access token is refreshed 60 s before expiry and once more on a
  `401`, under a row lock so concurrent turns never spend a rotating refresh
  token twice. A refresh the authorization server refuses unlinks the
  connector; one that cannot reach it drops the connector for the turn, like
  an outage.
- **Revocation.** Tokens are revoked on switch-off, admin deletion,
  retirement (#986) and account deletion.

When the partner's authorization server signs users in through ProConnect,
the second sign-in is usually silent since the session exists. Token exchange
at ProConnect (RFC 8693) stays a possible future kind; it does not change the
connector's shape.

Any kind that sends the user's identity to a partner makes personal data
flow, so it brings the DPA condition with it.

### 6. Consent (#985)

Today the only opt-in is data.gouv's `User.allow_datagouv_connector`, and the
force is the `force_datagouv` request parameter. #985 makes both generic:

- **Opt-in.** `User.allowed_connectors`, a JSON array of slugs, migrated from
  the old field. It records a choice, not an entitlement: the cohort gate
  still applies. New connectors need no migration, but there is no foreign key
  to the declarations, so orphaned slugs are handled by #986.
- **Users API.** It accepts only slugs the deployment offers, but keeps a slug
  the user already had, so a connector taken offline for a while keeps its
  users' consent.
- **Force.** A `force_connectors` request parameter, remembered in the
  browser's `localStorage`; never stored on the message or the conversation.
- **Analytics.** `connector_toggled` and `connector_force_toggled` (PostHog),
  with `connector_id` and `enabled`. `connector_forced` keeps recording each
  forced turn and whether it was reachable.
- **UI.** `GET /config/` lists the offered connectors (never the URL), and the
  UI is built from it with generic strings in the translation files, so a new
  connector needs no frontend release. The declaration's `description`
  carries its per-language values for the same reason.

Still open in #985: the language of the model-facing wordings, and whether
opt-ins are tied to `(slug, url)`.

The opt-in is **not versioned**: changing a connector's operator, URL or the
data it receives does not invalidate existing opt-ins. Changing those is a
reason to declare a new slug.

### 7. Defaults per tier

Only the `partner` column is in force, and it describes what the code does for
every connector today, since tiers are not enforced. The other columns record
the direction so later ADRs start from it.

| Policy | `internal` | `partner` (in force) | `user` |
|---|---|---|---|
| Who declares it | The deployment | The deployment (`MCP_CONNECTORS`) | An end user (not possible yet) |
| Egress | Internal network allowed | Any http(s) URL the deployment declares; no guard | Public internet only, private ranges blocked, redirects re-checked |
| Auth kinds | Any | `none`; `user_oauth` with #987; never token passthrough | `user_oauth` |
| Server instructions | Refused | Refused | Refused |
| Tool names, descriptions, results | Accepted | Accepted as-is, not filtered or capped | Truncated, treated as untrusted |
| Default for a user | Opt-in | Opt-in, or forced per turn | Opt-in |
| Consent | Opt-in | Opt-in by slug; account link for `user_oauth` | Versioned notice required |

### 8. Classification of known servers

| Server | Tier | Auth | Reasoning |
|---|---|---|---|
| data.gouv.fr MCP | `partner` | `none` | Run by a public body (DINUM / Etalab) outside our cluster; public data, but conversation excerpts are sent as tool arguments. |
| SofIA (ADEME) | `partner` | `user_oauth` (#987) | Run by a public body outside our cluster; each user signs in on its own authorization server. |
| Docs MCP in the same cluster | `internal` | — | Same operator, hosting and IdP; code reviewable. Out of scope. |
| A user's own GitHub MCP server | `user` | — | Declared by the user, unreviewed, needs the user's own credentials. Out of scope. |

### 9. Lifecycle (#986)

Removing a connector is explicit: a `retired` flag in the declaration means
it is never offered or used, and a Celery task, safe to rerun, unlinks it and
removes its slug from every user. A connector only taken offline (left out of
the declarations) keeps its opt-ins. A system check warns about slugs still in
the database but no longer declared.

### 10. Decided but not enforced yet

Each of these is a known gap between the policy above and the code. None needs
the connector's shape to change.

- **Tier enforcement.** `tier` is validated and stored, but no behaviour reads
  it: the registry accepts `internal` and `user` declarations. Before an
  `internal` or `user` connector ships, the registry should refuse what a tier
  does not allow.
- **Egress guard.** Calls to the MCP server go through the default HTTP
  client, with no check of the target address or of redirects. Acceptable
  while every URL is chosen by the deployment; required before `user`.
- **Tool policy.** There is no allowlist, denylist, tool count limit,
  description cap or approval step. Limits on the number of connectors per
  turn are undecided too; the decision should start from the measured token
  cost of each connector's tool list.
- **Connection time.** Connectors are connected one after another, so several
  unreachable connectors add up their `init_timeout` before the model is
  called. Connecting them concurrently is not possible as is, since the MCP
  client must be closed in the task that opened it; an overall budget is the
  likely answer.
- **Built-in tool names.** A slug whose prefix collides with a built-in tool
  name (`web` and `web_search`) is not detected.
- **Versioned consent notice.** Needed before a partner whose data handling
  users must be told about explicitly.
- **Slug immutability.** Documented only. Renaming a slug orphans opt-ins;
  #986's system check makes it visible, and #987 binds credentials to the
  server they were issued for.

## Consequences

- New partner connectors no longer need a release, only a configuration
  change. `MCP_CONNECTORS` (and, with #987, the OAuth client secrets) becomes
  security-relevant configuration, reviewed like any other deployment secret.
- A broken declaration fails `manage.py check`, `migrate` and the Helm migrate
  job (`chat.E101`), while a running instance survives one, so a mistake is
  caught at deployment, not by users.
- The `DATAGOUV_CONNECTOR_*` settings are gone. A deployment that used them
  declares data.gouv in `MCP_CONNECTORS` instead, keeping the `datagouv` slug
  so existing opt-ins still apply.
- `chat/mcp_servers.py` only re-exports the runtime names, for one release;
  #985 removes it.
- Until #985, only data.gouv has an opt-in and a UI; another declared
  connector can only be forced through the API.
- The trust boundary in `docs/tools.md` applies to the `partner` tier and
  links here.
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
- **Defaulting `tier` to `partner`.** Convenient for the only tier shipped,
  but a forgotten field would silently grant a trust level. Rejected in the
  review of #967.
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
- **Translations of connector texts in `translations.json`.** Would need a
  frontend release for each connector; per-language values in the
  declaration were chosen instead (#985).
