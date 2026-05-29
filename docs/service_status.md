# Service Status

Three mechanisms communicate service state to users:

- **Status banner** — admin-controlled, non-blocking notice shown at the top of
  the SPA (announcements, incidents, planned-but-not-started maintenance).
- **Dynamic health banners** — automatically derived from live model health;
  surface degradation or unavailability warnings without admin intervention, and
  can block the chat input when all models are down.
- **Maintenance mode** — admin-controlled, blocking; the app returns `503` and
  the SPA renders a dedicated maintenance page.

The status banner and maintenance state are exposed through
`/api/<version>/config/`. Dynamic health banners are served by a dedicated
endpoint, `/api/<version>/assistant-health/`.

---

## Status banner

A single, time-windowed banner driven by the `SiteConfiguration` singleton.

### Admin fields

Edit at **Core > Site Configuration**:

- `status_banner_level` — `info` / `warning` / `alert` (controls styling).
- `status_banner_title` — required; the banner is hidden when blank.
- `status_banner_content` — body text (markdown rendered by the SPA).
- `status_banner_starts_at` / `status_banner_ends_at` — optional window.
  Outside the window, the banner is hidden even with a title set.

### Visibility logic

The banner is visible when **all** of these hold:

1. `status_banner_title` is non-empty.
2. `starts_at` is unset or in the past.
3. `ends_at` is unset or in the future.

When hidden, `/config/` returns `status_banner: null`.

---

## Dynamic health banners

Automatically surfaced banners driven by the Redis-cached model health data
written by the model-health CronJob. No admin action is required; the system
self-heals as models recover.

### Configuration

Two optional env vars extend the main model with a fallback chain:

- `LLM_FALLBACK_MODEL_HRID_1` — HRID of the first fallback model (empty string
  = not configured).
- `LLM_FALLBACK_MODEL_HRID_2` — HRID of the second fallback model (empty string
  = not configured).

Only `fb1` can rescue the service to "slow" mode — `fb1=green` is the
exclusive trigger for the slowdowns banner. "All down" (the condition that
gates the unavailable / blocked state) means **both** fb1 and fb2 are
explicitly `red` or not configured (empty HRID). A Redis cache miss (`null`)
is treated optimistically — it does **not** count as down.

### Admin toggle

Edit at **Core > Site Configuration**:

- `block_on_full_outage` (default `True`) — when all models are down, controls
  whether the chat input is blocked or stays open with a degraded-service
  warning.
  - `True` (default): chat input is disabled; an **alert** banner is shown.
  - `False`: chat input remains active; a **warning** banner is shown instead.

### API endpoint

`GET /api/<version>/assistant-health/` (authenticated)

```json
{
  "banners": [
    { "level": "warning" | "alert", "title": "...", "content": "..." }
  ],
  "blocked": false | true
}
```

Returns an empty `banners` list and `"blocked": false` when the assistant is
healthy or its health status is unknown (Redis miss).

### Decision matrix

`main` is the Redis health of `LLM_DEFAULT_MODEL_HRID`. `fb1` / `fb2` are the
statuses of the two optional fallback models. `null` means the health key is
absent from Redis — treated as healthy (optimistic) to avoid false positives
when the CronJob has not run yet.

| main            | fb1              | fb2           | `block_on_full_outage` | Banner shown                                   | `blocked`    |
|-----------------|------------------|---------------|------------------------|------------------------------------------------|--------------|
| `green` / `null`| any              | any           | any                    | none                                           | `false`      |
| `yellow` / `red`| `green`          | any           | any                    | **warning** — high traffic, possible slowdowns | `false`      |
| `red`           | `red` / empty    | `red` / empty | `True` (default)       | **alert** — service unavailable                | **`true`**   |
| `red`           | `red` / empty    | `red` / empty | `False`                | **warning** — high traffic, degraded service   | `false`      |
| `yellow` / `red`| other            | any           | any                    | **warning** — high traffic, degraded service   | `false`      |

### Frontend behavior

- `useAssistantHealth()` polls the endpoint every **60 s** and fails open
  (empty banners, `blocked: false`) on any network or server error.
- `BannerStack` renders a vertical stack: the static admin banner first,
  followed by dynamic health banners below.
- The `Banner` component shows an interactive details modal when `content` is
  non-empty (warning/alert states with extended copy).
- The `InputChat` textarea is **disabled** when `assistantHealth.blocked` is
  `true`.
- When `blocked` is `true`, the `SuggestionCarousel` placeholder switches from
  rotating suggestions to a carousel of each active banner's `title` and
  `content` fields (non-empty values only), so users see the reason the input
  is unavailable.

---

## Maintenance mode

When active, the backend short-circuits every non-exempt request with HTTP
`503` and the SPA flips to a dedicated maintenance page.

### Two toggles, OR-combined

Maintenance is ON when **either** is true:

1. **Env var** `MAINTENANCE_MODE=true` (escape hatch — wins over the DB).
2. **DB singleton** `MaintenanceMode` has `enabled=True` and the current time
   falls inside `[starts_at, ends_at]` (both optional).

If the env var is set, the admin form shows a warning that the DB value is
overridden.

### Toggling via Django admin

Go to **Core > Maintenance Mode** and edit the singleton:

- `enabled` — master switch.
- `message` — shown on the maintenance page (blank = default copy).
- `starts_at` / `ends_at` — optional window. Outside it, `enabled` has no
  effect.

`updated_at` / `updated_by` are filled automatically. State changes are logged
at `WARNING` level.

### Exempt paths

`MaintenanceMiddleware` lets these through even when maintenance is on:

- `/admin/...` — so you can toggle it back off.
- `/__heartbeat__`, `/__lbheartbeat__` — load-balancer health checks.
- `/api/<version>/config/` — the SPA polls this to detect maintenance state.

Static files are served by `WhiteNoiseMiddleware` upstream and never reach the
maintenance middleware.

### Response

Non-exempt requests get:

```json
HTTP/1.1 503 Service Unavailable
Retry-After: <seconds-until-ends_at>   (only if ends_at is set and in the future)

{"code": "maintenance_mode", "detail": "Service under maintenance"}
```

### Frontend behavior

`ConfigProvider` reads `maintenance` from `/api/<version>/config/`. When it is
non-null, the SPA renders the maintenance page instead of the app shell.

Any `503 maintenance_mode` returned by another API call (query or mutation)
invalidates the `config` query, so users flip to the maintenance page on the
next interaction without a manual reload.

---

## Performance

Both `SiteConfiguration` and `MaintenanceMode` are `django-solo` singletons
cached in the default cache (`SOLO_CACHE_TIMEOUT = 5 min`). `save()`
invalidates the cache key immediately, so changes are effectively instant;
the timeout is just a safety net.

## Choosing between them

| Situation                                         | Use                                   |
|---------------------------------------------------|---------------------------------------|
| Heads-up about an upcoming change                 | Status banner                         |
| Ongoing degraded service, app still usable        | Status banner (`warning` or `alert`)  |
| Model slowness or downtime (detected by CronJob)  | Dynamic health banners (automatic)    |
| Hard downtime — block all user traffic            | Maintenance mode                      |
| Emergency lockout (admin DB unreachable)          | `MAINTENANCE_MODE` env var            |
