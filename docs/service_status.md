# Service Status

Two admin-controlled mechanisms communicate service state to users:

- **Status banner** — non-blocking notice shown at the top of the SPA
  (announcements, incidents, planned-but-not-started maintenance).
- **Maintenance mode** — blocking; the app returns `503` and the SPA renders a
  dedicated maintenance page.

Both are exposed to the frontend through `/api/<version>/config/`.

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

| Situation                                  | Use                |
|--------------------------------------------|--------------------|
| Heads-up about an upcoming change          | Status banner      |
| Ongoing degraded service, app still usable | Status banner (`warning` or `alert`) |
| Hard downtime — block all user traffic     | Maintenance mode   |
| Emergency lockout (admin DB unreachable)   | `MAINTENANCE_MODE` env var |
