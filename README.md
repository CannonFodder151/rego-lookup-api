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
| `PLAYWRIGHT` | no | `1` enables the Playwright Firefox worker for NSW/SA/NT/TAS/WA/ACT. |
| `UNDETECTED` | no | `1` enables the `undetected-chromedriver` provider for VIC. |

## Run

```bash
docker build -t rego-lookup .
docker run -d --name rego-lookup -p 8000:8000 \
  -e API_KEY='change-me' \
  -e PLAYWRIGHT=1 \
  -e UNDETECTED=1 \
  rego-lookup
```

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
| VIC | `FZR60` | 200 — YAMAHA FZ6S / 2009 / BLACK / SOLO / VIN `JYARJ14487A000061` (motorcycle field `Registration-Number-motorcycle` + `VehicleType` select) |
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
