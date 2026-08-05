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
| `FLARESOLVERR_URL` | no | FlareSolverr instance (e.g. `http://10.0.3.17:8191`). When set, browser-based states route through it to bypass Cloudflare. |
| `PLAYWRIGHT` | no | `1` enables the headless-Chromium providers as a fallback when FlareSolverr is not configured. |

## Run

```bash
docker build -t rego-lookup .
docker run -d --name rego-lookup -p 8000:8000 \
  -e API_KEY='change-me' \
  -e FLARESOLVERR_URL='http://10.0.3.17:8191' \
  rego-lookup
```

## State support (2026-08)

The API scrapes each state's government "check registration" service. Plain HTTP works for QLD only; the other states sit behind Cloudflare, JS-rendered forms, captchas, or owner-name verification, so they return `502` with the reason.

| State | Status |
|---|---|
| QLD | Working (verified) |
| VIC | Cloudflare bypassed via FlareSolverr, but the check form is a JS state-machine that needs click interaction — `502` |
| NSW | JS-injected form — `502` |
| WA | Wicket AJAX flow — `502` |
| SA | JS single-page app — `502` |
| NT | Check form requires owner first/last name — `502` |
| TAS | reCAPTCHA v3 token at submit — `502` |
| ACT | JS-rendered check — `502` |

`ponytail:` FlareSolverr gets past Cloudflare; what's missing for VIC/NSW/WA/SA/ACT is *click* automation. A state machine that replays clicks (e.g. Playwright with the challenge solved by FlareSolverr's proxy) is the upgrade path. Public state checks generally do **not** expose the full VIN; when shown (e.g. VIC displays a partial VIN), it is returned as-is.

Respect each state site's terms of service and rate limits.
