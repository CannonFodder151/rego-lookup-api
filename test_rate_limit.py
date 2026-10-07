"""Regression tests for /lookup rate limiting (AUT-315, AUT-1476).

Run: python test_rate_limit.py   (needs: slowapi + httpx installed)
"""

import os
import sys

os.environ.setdefault("RATE_LIMIT_IP", "4/minute")
os.environ.setdefault("RATE_LIMIT_KEY", "6/minute")
os.environ.setdefault("API_KEY", "test-key")
# Simulate deployment behind an allowlisted reverse proxy: the TestClient
# connects from 203.0.113.7, which is the only trusted proxy.
os.environ.setdefault("TRUSTED_PROXIES", "203.0.113.7")

sys.path.insert(0, ".")
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


async def _fake_lookup(plate, state, first_name=None, last_name=None, vehicle_type="car"):
    return {"plate": plate, "state": state, "vin": None, "make": "TOYOTA",
            "model": "COROLLA", "year": 2019, "colour": "SILVER", "body_type": "SEDAN"}


main.lookup = _fake_lookup
client = TestClient(main.app, client=("203.0.113.7", 1500))

KEY = "test-key"


def _lookup(ip, key=KEY):
    headers = {}
    if key:
        headers["X-API-Key"] = key
    if ip:
        headers["X-Forwarded-For"] = ip
    return client.post("/lookup", json={"plate": "1ABC123", "state": "QLD"}, headers=headers)


def test_per_ip_limit():
    # Each IP is allowed RATE_LIMIT_IP (4) lookups; the 5th gets 429.
    for _ in range(4):
        r = _lookup("1.2.3.4")
        assert r.status_code == 200, r.text
    r = _lookup("1.2.3.4")
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after"), "429 must carry Retry-After"
    # A different IP shares neither bucket and still works.
    assert _lookup("5.6.7.8").status_code == 200


def test_per_key_limit():
    # A single key is allowed RATE_LIMIT_KEY (6) lookups even from many IPs.
    main.API_KEY = "key-a"
    for i in range(6):
        r = _lookup(f"10.0.0.{i}", key="key-a")
        assert r.status_code == 200, r.text
    r = _lookup("10.0.0.9", key="key-a")
    assert r.status_code == 429, r.text
    # An unrelated key is not rate-limited (auth still rejects the wrong key).
    r = _lookup("10.0.0.10", key="key-b")
    assert r.status_code == 401, r.text


def test_anon_uses_own_bucket():
    # No key falls into the shared "anon" bucket and is still IP-limited.
    main.API_KEY = "test-key"
    for i in range(4):
        r = _lookup(f"10.1.0.{i}", key=None)
        assert r.status_code == 401, r.text
    r = _lookup("10.1.0.99", key=None)
    assert r.status_code == 401, r.text


def test_xff_ignored_without_trusted_proxy():
    # AUT-1476: an untrusted peer cannot mint new per-IP buckets by rotating
    # XFF — every spoofed request lands in the same (socket-addr) bucket.
    main.API_KEY = "key-spoof"
    saved = list(main.TRUSTED_NETWORKS)
    main.TRUSTED_NETWORKS = []
    try:
        for i in range(4):
            r = _lookup(f"10.9.9.{i}", key="key-spoof")
            assert r.status_code == 200, r.text
        r = _lookup("10.9.9.42", key="key-spoof")
        assert r.status_code == 429, r.text
    finally:
        main.TRUSTED_NETWORKS = saved


def test_xff_rightmost_untrusted_hop_wins():
    # Behind a trusted proxy, the rightmost non-trusted XFF hop keys the
    # bucket; spoofed leading entries are ignored.
    main.API_KEY = "key-chain"
    for i in range(4):
        r = _lookup(f"evil.example, 10.2.0.{i}", key="key-chain")
        assert r.status_code == 200, r.text
    assert _lookup("evil.example, 10.2.0.99", key="key-chain").status_code == 429
    # Each distinct rightmost hop gets its own bucket.
    assert _lookup("10.3.0.1, 10.4.0.1", key="key-chain").status_code == 200


if __name__ == "__main__":
    test_per_ip_limit()
    test_per_key_limit()
    test_anon_uses_own_bucket()
    print("all tests passed")
