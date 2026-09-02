"""Regression test for AUT-2145: X-API-Key auth must run BEFORE Pydantic body
validation, so unauthenticated requests receive 401 (not 422) regardless of
body shape.

Run: API_KEY=test-key pytest test_rego_auth_before_validation.py
     (or python test_rego_auth_before_validation.py)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__) or ".")

# Set API_KEY BEFORE importing main so the module picks up the test value.
os.environ.setdefault("API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)
VALID_KEY = os.environ["API_KEY"]


def _auth():
    return {"X-API-Key": VALID_KEY}


def test_missing_body_without_key_returns_401_not_422():
    r = client.post("/lookup", json={})
    assert r.status_code == 401, f"expected 401, got {r.status_code} body={r.text}"
    assert "plate" not in r.text, "422 schema leak: 'plate' must not appear in unauth response"
    assert "state" not in r.text, "422 schema leak: 'state' must not appear in unauth response"


def test_empty_body_without_key_returns_401_not_422():
    r = client.post("/lookup", content=b"")
    assert r.status_code == 401, f"expected 401, got {r.status_code} body={r.text}"


def test_valid_body_without_key_returns_401():
    r = client.post("/lookup", json={"plate": "1ABC123", "state": "QLD"})
    assert r.status_code == 401, f"expected 401, got {r.status_code} body={r.text}"


def test_valid_body_with_wrong_key_returns_401():
    r = client.post("/lookup", json={"plate": "1ABC123", "state": "QLD"},
                    headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401, f"expected 401, got {r.status_code} body={r.text}"


def test_bearer_auth_works():
    # Regression: bearer token path should still authenticate and reach
    # downstream (which may 404/502 on the live upstream, but never 401/422).
    r = client.post("/lookup", json={"plate": "1ABC123", "state": "QLD"},
                    headers={"Authorization": f"Bearer {VALID_KEY}"})
    assert r.status_code != 401, "valid bearer should not be 401"
    assert r.status_code != 422, "valid bearer should not be 422"


def test_valid_key_invalid_body_returns_422():
    # After AUTH passes, validation errors must surface as 422 (sanitised).
    r = client.post("/lookup", json={"plate": "1ABC123", "state": "XX"}, headers=_auth())
    # state is checked in the handler (400), not pydantic — accept either.
    assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code}"


def test_valid_key_missing_body_returns_422():
    r = client.post("/lookup", json={}, headers=_auth())
    assert r.status_code == 422, f"expected 422 (auth passed), got {r.status_code}"


if __name__ == "__main__":
    test_missing_body_without_key_returns_401_not_422()
    test_empty_body_without_key_returns_401_not_422()
    test_valid_body_without_key_returns_401()
    test_valid_body_with_wrong_key_returns_401()
    test_bearer_auth_works()
    test_valid_key_invalid_body_returns_422()
    test_valid_key_missing_body_returns_422()
    print("all AUT-2145 regression tests passed")