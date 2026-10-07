# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Fixed
- **(AUT-2468):** The `HEALTHCHECK` now uses `${PORT:-8000}` so it tracks the
  actual `CMD` port. Previously the check probed `localhost:8000` even when the
  container was started with `--port 8011`, leaving the rego-lookup container
  on EP5 (Hosted) in `(unhealthy)` for 18h while still serving traffic.

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
