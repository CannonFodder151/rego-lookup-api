# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
FROM python:3.13-slim@sha256:16f75ad0fbc6c4883a8afd63b2d700c3cf68ccffc1aaeca5304ca0a3a908451f

ARG TARGETARCH

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

COPY . .

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
