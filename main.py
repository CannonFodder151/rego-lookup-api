import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from providers import UpstreamBlocked, UpstreamError, NotFound, STATES, lookup

app = FastAPI(title="Rego Lookup API", version="1.0.0")

API_KEY = os.getenv("API_KEY", "")


class LookupRequest(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    state: str = Field(min_length=2, max_length=3)
    first_name: str | None = None
    last_name: str | None = None
    vehicle_type: str = "car"


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
    return {"status": "ok"}


@app.post("/lookup", response_model=LookupResponse)
async def rego_lookup(
    req: LookupRequest,
    x_api_key: str | None = Header(None),
    authorization: str | None = Header(None),
):
    key = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:]
    if not API_KEY or key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")

    state = req.state.strip().upper()
    if state not in STATES:
        raise HTTPException(status_code=400, detail="state must be one of VIC, NSW, QLD, WA, SA, NT, TAS, ACT")

    plate = req.plate.strip().upper()
    try:
        return await lookup(plate, state, req.first_name, req.last_name, req.vehicle_type)
    except NotFound:
        raise HTTPException(status_code=404, detail="registration not found")
    except UpstreamBlocked as e:
        raise HTTPException(status_code=502, detail=str(e))
    except UpstreamError as e:
        raise HTTPException(status_code=502, detail=str(e))
