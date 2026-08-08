FROM python:3.12-slim

ARG TARGETARCH

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium firefox \
    && apt-get update \
    && apt-get install -y --no-install-recommends wget xvfb \
    && if [ "$TARGETARCH" = "amd64" ]; then \
         wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
         && apt-get install -y ./google-chrome-stable_current_amd64.deb \
         && rm -f google-chrome-stable_current_amd64.deb; \
       elif [ "$TARGETARCH" = "arm64" ]; then \
         apt-get install -y --no-install-recommends chromium; \
       fi \
    && rm -rf /var/lib/apt/lists/*

COPY . .

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
