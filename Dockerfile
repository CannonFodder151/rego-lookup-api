FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium firefox \
    && apt-get update \
    && apt-get install -y --no-install-recommends wget xvfb \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm -f google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/* \
    && python -c "import setuptools, undetected_chromedriver as uc; uc.Chrome(options=uc.ChromeOptions(), headless=True).quit()" || true

COPY . .

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
