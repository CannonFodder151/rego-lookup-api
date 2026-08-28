# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Security
- **(AUT-1739, CWE-250):** The image no longer runs as root. Creates a non-root
  `appuser` (uid 1000), chowns `/app` to it, and sets `USER appuser`. The
  Chromium SUID sandbox helper (`/opt/google/chrome/chrome-sandbox` or
  `/usr/lib/chromium/chrome-sandbox`) is kept root-owned + setuid (`4755`) so
  Chromium can sandbox untrusted third-party content as the non-root user.
   `undetected.py` now launches Chromium sandboxed (no `--no-sandbox`) and only
   falls back to `--no-sandbox` if the sandboxed launch actually fails. Playwright
   browsers are now installed to `/ms-playwright` (outside root's home) so the
   non-root user can read the Firefox/Chromium binaries at launch.
