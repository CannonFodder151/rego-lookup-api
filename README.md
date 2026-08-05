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
| `PLAYWRIGHT` | no | `1` enables headless-Chromium providers for the bot-walled states. Set to `0` to disable. |

## Run

```bash
docker build -t rego-lookup .
docker run -d --name rego-lookup -p 8000:8000 -e API_KEY='change-me' -e PLAYWRIGHT=1 rego-lookup
```

## State support (2026-08)

The API scrapes each state's government "check registration" service. State sites change and many block plain HTTP, so the blocked ones are driven with Playwright (headless Chromium) when `PLAYWRIGHT=1`.

| State | Plain HTTP | Playwright |
|---|---|---|
| QLD | Working (verified) | — |
| VIC | 502 — Cloudflare | Attempts (Cloudflare challenge) |
| NSW | 502 — JS-injected form | Attempts |
| WA | 502 — Wicket AJAX | Attempts |
| SA | 502 — JS SPA + AU-IP geo-block | Attempts (needs AU IP) |
| NT | 502 — Cloudflare | Attempts |
| TAS | 502 — reCAPTCHA v3 + Cloudflare | Attempts |
| ACT | 502 — JS-rendered check | Attempts |

A state returns `502` when its site blocks the request or no vehicle details are retrievable. Public state checks generally do **not** expose the full VIN; when they show one (VIC shows a partial VIN), it is returned as-is.

Respect each state site's terms of service and rate limits.
