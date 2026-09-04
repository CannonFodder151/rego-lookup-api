# Rego Lookup API

Docker-deployable HTTP API that looks up Australian vehicle registration plates and returns VIN, make, model, year, colour and body type.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| POST | `/lookup` | API key | Look up a registration |

### POST /lookup

Request body:

```json
{ "plate": "1ABC123", "state": "QLD" }
```

`vehicle_type` is optional and defaults to `car`. Set it to `motorcycle` for
bikes — VIC requires the type so the correct vicroads field is used:

```json
{ "plate": "3B4PV", "state": "VIC", "vehicle_type": "motorcycle" }
```

`plate` is normalised (trimmed, upper-cased) and must match 1-8 letters/digits
(`A-Z`, `0-9`) — malformed plates return `422`.

Optional for states that verify the owner (currently unused by the providers):

```json
{ "plate": "1ABC123", "state": "NT", "first_name": "John", "last_name": "Doe" }
```

`state` is one of `VIC, NSW, QLD, WA, SA, NT, TAS, ACT`.

Auth: send the API key as `X-API-Key: <key>` header or `Authorization: Bearer <key>`.

Response:

```json
{
  "plate": "1ABC123",
  "state": "QLD",
  "vin": null,
  "make": "TOYOTA",
  "model": "COROLLA",
  "year": 2019,
  "colour": "SILVER",
  "body_type": "SEDAN",
  "rego_status": "valid",
  "rego_expiry_date": "2026-03-14"
}
```

`rego_status` is `"valid"` (current/registered/active), `"expired"`
(expired/unregistered/cancelled/surrendered), `"unknown"` (state site returned
a label we don't recognise — surfaced for the caller to decide) or `null` (no
status surfaced). `rego_expiry_date` is ISO 8601 `YYYY-MM-DD` or `null`. Both
fields are always present in the JSON so consumers can rely on the schema.

Status codes:

- `200` found
- `400` invalid state
- `401` missing or wrong API key
- `404` registration not found
- `422` malformed request — `plate` must be 1-8 letters/digits (A-Z, 0-9, normalised to upper case) and `vehicle_type` must be `car` or `motorcycle`
- `429` rate limit exceeded (per-IP or per-API-key; `Retry-After` header set)
- `502` upstream state site unreachable / blocked

## Rate limiting (AUT-315)

Every `/lookup` is rate limited twice — once per client IP and once per API key —
to prevent cost/compute abuse and excessive scraping of state sites. Excess
requests return `429` with a `Retry-After` header.

Client IPs come from the socket address by default (AUT-1476). `X-Forwarded-For`
is honoured only when the direct peer is in the `TRUSTED_PROXIES` allowlist
(comma-separated IPs/CIDRs, e.g. your reverse-proxy docker subnet); in that case
the rightmost non-trusted hop wins, so spoofed entries appended by clients are
ignored. With no allowlist set, client-supplied XFF headers cannot influence
rate-limit buckets.

`/health` is never rate limited.

## Concurrency

Browser-based lookups (Playwright subprocess workers) are capped so a burst of
requests cannot spawn unbounded Chrome/Firefox processes. VIC's
`undetected-chromedriver` worker is already serialised behind a lock.

## Configuration

| Env var | Required | Description |
|---|---|---|
| `API_KEY` | yes | Key clients must present. Set a long random string. |
| `PLAYWRIGHT` | no | `1` enables the Playwright Firefox worker for NSW/SA/NT/TAS/WA/ACT. |
| `UNDETECTED` | no | `1` enables the `undetected-chromedriver` provider for VIC. |
| `RATE_LIMIT_IP` | no | Per-IP rate limit on `/lookup`. Default `30/minute`. |
| `RATE_LIMIT_KEY` | no | Per-API-key rate limit on `/lookup`. Default `120/minute`. |
| `TRUSTED_PROXIES` | no | Comma-separated IPs/CIDRs allowed to set `X-Forwarded-For`. Unset: XFF ignored, socket address used. |
| `BROWSER_MAX_CONCURRENCY` | no | Max concurrent browser worker subprocesses. Default `2`. |

## Run

```bash
docker build -t rego-lookup .
docker run -d --name rego-lookup -p 127.0.0.1:8000:8000 \
  -e API_KEY='<generate-long-random>' \
  -e PLAYWRIGHT=1 \
  -e UNDETECTED=1 \
  rego-lookup
```

**Security:** bind to loopback/private interfaces only (`127.0.0.1:PORT:PORT`).
Do not publish on a public IP — `/lookup` sends the static API key in cleartext
and has no TLS. Consumers on the same host (or a shared docker network, e.g.
`autobrain-hosted_default`) reach it by `localhost` / container name; nothing
from the internet should ever reach it. See AUT-316.

## Deploy (auto — AUT-264)

**Every push to `main` deploys automatically.** No manual step required.

1. GitHub Actions (`build.yml`) triggers on push to `main` (and manual dispatch).
2. The `build` job builds and pushes the multi-arch image:
   `ghcr.io/cannonfodder151/rego-lookup:hosted` (+ GHCR/Docker Hub aliases).
3. The `deploy` job then redeploys **both** production tiers via Portainer with
   `PullImage: true`:
   - **On-prem** — Portainer stack `plate-api-scraper` (EP2, `10.0.3.17:8011`),
     stack id **75**.
   - **Hosted** — Portainer stack `rego-lookup` (EP5, `152.69.188.133:8011`,
     Oracle Cloud), stack id **85**.

Both stacks pull the `:hosted` tag, so a rebuilt image is picked up on the next
redeploy. The deploy job reads each stack's current compose from Portainer and
re-applies it with `PullImage: true`, so config never drifts. It tolerates a
reverse-proxy `504`/timeout on the PUT — Portainer applies the update
server-side regardless.

Credentials come from repo secrets: `PORTAINER_URL`, `PORTAINER_API_KEY`.

Rollback: `PUT /api/stacks/{75|85}?endpointId={2|5}` with the previous compose
or pin a specific image digest.

## State support (2026-08)

All 8 states work. QLD uses plain HTTP; VIC uses `undetected-chromedriver` headful under Xvfb (`UNDETECTED=1`, defeats Cloudflare and returns the full VIN); NSW, SA, NT, TAS, WA, ACT use a Playwright **Firefox** worker run as a subprocess (`PLAYWRIGHT=1`) — a real Firefox passes the state sites' reCAPTCHA v2/v3 and JS-rendered checks without a solver.

| State | Status |
|---|---|
| QLD | Working (verified) |
| VIC | Working (verified) — full VIN, e.g. `TCRWN` → TOYOTA / 2009 / BLACK / SEDAN / `6ZZ9GWS2040011605` |
| NSW | Working (verified) — T&C checkbox + reCAPTCHA |
| NT | Working (verified) — first/last-name fields are hidden anti-bot honeypots, ignored |
| WA | Working (verified) |
| SA | Working (verified) |
| TAS | Working (verified) |
| ACT | Working (verified) — Wicket wizard + privacy checkbox |

Respect each state site's terms of service and rate limits.

## Motorcycle verification (2026-08-06)

`vehicle_type=motorcycle` tested across states (unregistered sample plates —
a clean `404 registration not found` confirms the flow ran):

| State | Plate | Result |
|---|---|---|
| VIC | `FZR60` | 200 — make YAMAHA / model FZ6S / 2009 / BLACK / SOLO / VIN `JYARJ14487A000061` (motorcycle field `Registration-Number-motorcycle` + `VehicleType` select) |
| VIC | `3B4PV` | 404 (motorcycle field + vehicle-type dropdown selected) |
| QLD | `1ABC1` | 404 |
| NSW | `ABC12D` | 404 |
| WA | `1AAA2B` | 404 |
| SA | `1ABC2C` | 404 |
| ACT | `1AB2CD` | 404 |
| NT | `1A23B` | 502 — same as cars; NT site doesn't return a parseable result for this format |
| TAS | `1ABCD3` | 502 — same as cars; TAS site doesn't return a parseable result for this format |

NT/TAS 502s are pre-existing (identical for car regos of the same format),
not motorcycle-specific.

## Rego status + expiry (AUT-2413)

Every `/lookup` response includes `rego_status` (`"valid"` | `"expired"` |
`"unknown"` | `null`) and `rego_expiry_date` (ISO 8601 `YYYY-MM-DD` | `null`).
The parser handles the date formats each AU state actually renders:

| State | Status label | Date label | Format |
|---|---|---|---|
| QLD | `Registration status` | `Registration expiry date` | DD/MM/YYYY |
| VIC | `Status` | `Registration expiry date` | DD Month YYYY |
| NSW | `Status` | `Until: <date>` (no Expiry label) | DD/MM/YYYY |
| WA | `Status` | `Expiry` | DD-Mon-YYYY |
| SA | `Registration status` | `Expiry date` | DD Month YYYY |
| NT/TAS/ACT | variants of the above (same patterns) | | |

Unrecognised labels surface as `"unknown"` rather than being silently dropped;
unparseable dates become `null` so callers can decide how to handle them.
