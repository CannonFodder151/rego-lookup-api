import hmac
import ipaddress
import os
import re
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from providers import UpstreamBlocked, UpstreamError, NotFound, STATES, lookup

APP_VERSION = "1.2.3"

API_KEY = os.getenv("API_KEY", "")

# Per-IP and per-API-key limits on /lookup (each lookup scrapes a state site).
# In-memory buckets are fine: each deployment runs a single uvicorn worker.
# Tune with RATE_LIMIT_IP / RATE_LIMIT_KEY env vars.
RATE_LIMIT_IP = os.getenv("RATE_LIMIT_IP", "30/minute")
RATE_LIMIT_KEY = os.getenv("RATE_LIMIT_KEY", "120/minute")

# X-Forwarded-For is trusted only when the direct socket peer is in this
# allowlist (comma-separated IPs/CIDRs, e.g. the reverse-proxy docker subnet).
# Unset/empty (the default): the socket address is always used and client
# XFF headers are ignored, so the per-IP limit cannot be evaded by spoofing.
TRUSTED_NETWORKS = [
    ipaddress.ip_network(p.strip(), strict=False)
    for p in os.getenv("TRUSTED_PROXIES", "").split(",")
    if p.strip()
]


def _client_ip(request: Request) -> str:
    peer = get_remote_address(request)
    fwd = request.headers.get("x-forwarded-for")
    if TRUSTED_NETWORKS and fwd:
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer
        if any(peer_ip in net for net in TRUSTED_NETWORKS):
            # Rightmost non-trusted hop is the real client; proxies overwrite
            # rather than strip, so walk the chain backwards.
            for hop in reversed([h.strip() for h in fwd.split(",")]):
                try:
                    hop_ip = ipaddress.ip_address(hop)
                except ValueError:
                    return hop
                if not any(hop_ip in net for net in TRUSTED_NETWORKS):
                    return hop
    return peer


def _api_key(request: Request) -> str:
    key = request.headers.get("x-api-key")
    if not key:
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            key = auth[7:].strip()
    return key or "anon"


limiter = Limiter(key_func=_api_key, headers_enabled=True)

app = FastAPI(title="Rego Lookup API", version=APP_VERSION)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Plate normalised (strip + upper) then matched against AU plate shapes:
# 1-8 alphanumerics. Matches autobrain backend/app/services/rego.py:_valid_au_plate.
_PLATE_RE = re.compile(r"^[A-Z0-9]{1,8}$")


class LookupRequest(BaseModel):
    plate: str
    state: str = Field(min_length=2, max_length=3)
    first_name: str | None = None
    last_name: str | None = None
    vehicle_type: Literal["car", "motorcycle"] = "car"

    @field_validator("plate")
    @classmethod
    def _normalise_plate(cls, v: str) -> str:
        v = v.strip().upper()
        if not _PLATE_RE.match(v):
            raise ValueError("plate must be 1-8 letters/digits (A-Z, 0-9)")
        return v


class LookupResponse(BaseModel):
    plate: str
    state: str
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    colour: str | None = None
    body_type: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


# AUT-2145: API-key check runs as a FastAPI dependency before Pydantic body
# parsing so unauthenticated requests cannot fingerprint the request schema.
def require_api_key(
    request: Request,
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
) -> str:
    key = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:]
    if not API_KEY or not hmac.compare_digest(key or "", API_KEY):
        raise HTTPException(status_code=401, detail="invalid API key")
    return key or ""


@app.post("/lookup", response_model=LookupResponse)
@limiter.limit(RATE_LIMIT_IP, key_func=_client_ip)
@limiter.limit(RATE_LIMIT_KEY, key_func=_api_key)
async def rego_lookup(
    request: Request,
    response: Response,
    req: LookupRequest,
    _api_key: str = Depends(require_api_key),
):

    state = req.state.strip().upper()
    if state not in STATES:
        raise HTTPException(status_code=400, detail="state must be one of VIC, NSW, QLD, WA, SA, NT, TAS, ACT")

    plate = req.plate
    try:
        return await lookup(plate, state, req.first_name, req.last_name, req.vehicle_type)
    except NotFound:
        raise HTTPException(status_code=404, detail="registration not found")
    except UpstreamBlocked as e:
        raise HTTPException(status_code=502, detail=str(e))
    except UpstreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
