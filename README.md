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

The API scrapes each state's government "check registration" service. Plain HTTP is used for QLD; the other states are driven by headless Chromium (Playwright async) that first takes the FlareSolverr Cloudflare-clearance cookies, then fills the form and clicks Search. VIC uses `undetected-chromedriver` headful under Xvfb (`UNDETECTED=1`), which defeats Cloudflare's fingerprinting. A state returns `502` when its site blocks the request or no vehicle details are retrievable.

| State | Status |
|---|---|
| QLD | Working (verified) |
| VIC | Working (verified) — returns full VIN, e.g. `TCRWN` → TOYOTA / 2009 / BLACK / SEDAN / `6ZZ9GWS2040011605` |
| NT | Working (verified) — note its first/last-name fields are hidden anti-bot honeypots, so the submitted names are ignored |
| WA | Working (verified) |
| NSW | Blocked — check form is behind a JS popup flow |
| SA | Blocked — JS single-page app, timed out |
| TAS | Blocked — reCAPTCHA v3 on submit |
| ACT | Blocked — no search form reachable on the check page |

`ponytail:` NSW/SA/TAS/ACT need the same treatment VIC got (an `undetected-chromedriver` headful provider per state). Respect each state site's terms of service and rate limits.
