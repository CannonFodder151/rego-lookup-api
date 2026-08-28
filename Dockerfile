FROM python:3.12-slim

ARG TARGETARCH

# AUT-1739: Playwright installs browsers into this path. It must live outside
# root's home so the non-root runtime user can read the binaries at launch.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
# Base image pip 25.0.1 carries PYSEC-2026-196/1795/1796/2875/2876 (AUT-1019);
# pip >= 26.2 clears PYSEC-2026-3721 (AUT-1542).
RUN pip install --upgrade pip==26.2 \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium firefox \
    && apt-get update \
    && apt-get install -y --no-install-recommends wget xvfb \
    && if [ "$TARGETARCH" = "amd64" ]; then \
         wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
         && apt-get install -y ./google-chrome-stable_current_amd64.deb \
         && rm -f google-chrome-stable_current_amd64.deb; \
        elif [ "$TARGETARCH" = "arm64" ]; then \
          apt-get install -y --no-install-recommends chromium chromium-driver; \
          fi \
    && rm -rf /var/lib/apt/lists/*

# AUT-1739 (CWE-250): run as a non-root user so a Chromium/Playwright (or
# Xvfb) compromise can't gain root inside the container. Chromium's SUID
# sandbox helper must stay root-owned with the setuid bit so it can drop
# privileges after launch; without it Chromium falls back to --no-sandbox.
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /ms-playwright \
    && for sb in /opt/google/chrome/chrome-sandbox /usr/lib/chromium/chrome-sandbox; do \
         if [ -e "$sb" ]; then chown root:root "$sb" && chmod 4755 "$sb"; fi; \
       done
USER appuser

COPY . .

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
