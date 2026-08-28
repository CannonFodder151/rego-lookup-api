FROM python:3.12-slim

ARG TARGETARCH

# CWE-250: run the container (and the Chromium/Playwright browser automation) as
# a non-root user. A browser exploit can no longer escalate to container root.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --shell /usr/sbin/nologin --create-home appuser

WORKDIR /app

# Keep Playwright browsers in a world-readable path: the default /root/.cache is
# not traversable by a non-root user and would make browser launch fail.
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_ROOT_USER_ACTION=ignore

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

COPY . .

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Hand ownership of app + browser cache to the non-root user.
RUN chown -R appuser:appuser /app /usr/local/share/ms-playwright

# Let Chromium sandbox as the non-root user: the SUID sandbox helper must be
# root-owned and setuid so Chromium can drop privileges after launch. Without
# this, the only way to run Chromium as non-root is --no-sandbox (worse).
RUN SB=$(find /usr/local/share/ms-playwright -name chrome-sandbox -type f | head -n1); \
    if [ -n "$SB" ]; then chown root:root "$SB" && chmod 4755 "$SB"; fi; \
    if [ -x /opt/google/chrome/chrome-sandbox ]; then \
       chown root:root /opt/google/chrome/chrome-sandbox \
       && chmod 4755 /opt/google/chrome/chrome-sandbox; fi

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
