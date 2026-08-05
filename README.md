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

`state` is one of `VIC, NSW, QLD, WA, SA, NT, TAS`.

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
  "body_type": "SEDAN"
}
```

Status codes:

- `200` found
- `400` invalid/missing state or plate
- `401` missing or wrong API key
- `404` registration not found
- `502` upstream state site unreachable / blocked

## Configuration

| Env var | Required | Description |
|---|---|---|
| `API_KEY` | yes | Key clients must present. Set a long random string. |

## Run

```bash
docker build -t rego-lookup .
docker run -d --name rego-lookup -p 8000:8000 -e API_KEY='change-me' rego-lookup
```

## State support (2026-08)

The API scrapes each state's government "check registration" service. State sites change and many block plain HTTP.

| State | Status |
|---|---|
| QLD | Working (verified) |
| WA | Attempted; currently blocked by Wicket AJAX flow — returns 502 |
| VIC | 502 — Cloudflare managed challenge |
| NSW | 502 — lookup form is injected client-side |
| SA | 502 — JS single-page app + AU-IP geo-block |
| NT | 502 — Cloudflare managed challenge |
| TAS | 502 — reCAPTCHA v3 + Cloudflare |

`ponytail:` plain-HTTP scrapers are the ceiling here. To get the blocked states working, add a Playwright provider (headless browser inside the container) to pass Cloudflare challenges and JS rendering. Note also that public state checks generally do **not** expose the full VIN, so `vin` is usually `null`.

Respect each state site's terms of service and rate limits.
