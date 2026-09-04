# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- **(AUT-2413):** `POST /lookup` response now includes `rego_status`
  (`"valid"` | `"expired"` | `"unknown"` | `null`) and `rego_expiry_date`
  (ISO 8601 `YYYY-MM-DD` | `null`). Parser handles every AU date format the
  state sites actually render (DD/MM/YYYY, DD-MM-YYYY, DD Month YYYY,
  DD-Mon-YYYY, Mon DD YYYY, ISO) and NSW's "Registered Until: <date>" layout.
  New `_normalise_status` / `_parse_date` helpers + `test_rego_status_expiry.py`
  lock the behaviour across all 8 state shapes.

### Security
- **(AUT-2145):** The X-API-Key check now runs as a FastAPI dependency
  (`require_api_key`) that resolves before Pydantic body parsing. Unauthenticated
  `POST /lookup` requests — including empty/invalid bodies — now return
  `401 invalid API key` instead of `422 Unprocessable Entity`, so the required
  field names (`plate`, `state`) are no longer disclosed to unauthenticated
  callers. The bearer-token header is still honoured. Added
  `test_rego_auth_before_validation.py` to lock the new behaviour.
- **(AUT-1739, CWE-250):** The image no longer runs as root. Creates a non-root
  `appuser` (uid 1000), chowns `/app` to it, and sets `USER appuser`. The
  Chromium SUID sandbox helper (`/opt/google/chrome/chrome-sandbox` or
  `/usr/lib/chromium/chrome-sandbox`) is kept root-owned + setuid (`4755`) so
  Chromium can sandbox untrusted third-party content as the non-root user.
   `undetected.py` now launches Chromium sandboxed (no `--no-sandbox`) and only
   falls back to `--no-sandbox` if the sandboxed launch actually fails. Playwright
   browsers are now installed to `/ms-playwright` (outside root's home) so the
   non-root user can read the Firefox/Chromium binaries at launch.