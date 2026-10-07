"""Regression test: /docs, /redoc, /openapi.json disabled in production (AUT-1745).

Mirrors backend behavior — CWE-200 information disclosure prevention.
Run: ENVIRONMENT=production python test_docs_disabled.py
"""

import os
import sys

os.environ.setdefault("API_KEY", "test-key")

sys.path.insert(0, ".")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ENV = os.getenv("ENVIRONMENT", "production")
client = TestClient(main.app)


def test_docs_disabled_in_production():
    if ENV == "production":
        assert client.get("/docs").status_code == 404, "/docs must be disabled in production"
        assert client.get("/openapi.json").status_code == 404, "/openapi.json must be disabled in production"
        assert client.get("/redoc").status_code == 404, "/redoc must be disabled in production"
    else:
        assert client.get("/docs").status_code == 200, "/docs must be enabled in non-prod"
        assert client.get("/openapi.json").status_code == 200, "/openapi.json must be enabled in non-prod"
        assert client.get("/redoc").status_code == 200, "/redoc must be enabled in non-prod"


def test_health_unaffected():
    assert client.get("/health").status_code == 200


if __name__ == "__main__":
    test_docs_disabled_in_production()
    test_health_unaffected()
    print(f"ENVIRONMENT={ENV}: all docs-disabled checks passed")