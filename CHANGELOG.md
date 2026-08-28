# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed
- **Security (AUT-1739):** The image no longer runs as root — the API and the
  Chromium/Playwright browser automation now run as the non-root `appuser` user,
  closing the container-shell escape path (CWE-250, trivy DS-0002). Playwright
  browsers relocated to a world-readable `/usr/local/share/ms-playwright` so the
  non-root user can use them.
- **Security (AUT-1739):** Chromium SUID sandbox helper kept root-owned +
  setuid (`4755`) so the undetected-chromium (VIC) flow sandboxes as non-root
  instead of requiring `--no-sandbox`; `undetected.py` now tries the sandboxed
  launch first and only falls back to `--no-sandbox` if the host can't sandbox.
