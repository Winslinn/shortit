import json
import os
import string

from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, Depends, Request
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from shortit.database import Base, engine, get_session, Address

from contextlib import asynccontextmanager

from pydantic import BaseModel, HttpUrl
from secrets import choice
from sqlalchemy import select
from sqlalchemy.orm import Session

alphabet = string.ascii_letters + string.digits

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield

limiter = Limiter(key_func=lambda request: request.client.host)
app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,    
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

class ShortenRequest(BaseModel):
    url: HttpUrl
    turnstile_token: str


def verify_turnstile_token(token: str, remote_ip: str | None) -> bool:
    secret = os.getenv("TURNSTILE_SECRET", "").strip()
    expected_hostnames = {
        hostname.strip().lower().rstrip(".")
        for hostname in os.getenv("TURNSTILE_HOSTNAMES", "").split(",")
        if hostname.strip()
    }
    if not secret or not expected_hostnames:
        raise HTTPException(
            status_code=503,
            detail="Link shortening is temporarily unavailable.",
        )
    if not token.strip() or len(token) > 2048:
        return False

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    siteverify_request = UrlRequest(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(siteverify_request, timeout=10) as response:
            result = json.loads(response.read())
    except (OSError, TimeoutError, URLError, ValueError):
        return False

    if not isinstance(result, dict):
        return False
    hostname = str(result.get("hostname", "")).lower().rstrip(".")
    return (
        result.get("success") is True
        and result.get("action") == "shorten"
        and hostname in expected_hostnames
    )

@app.get("/")
async def read_root():
    return {"message": "Congratulations, you've found the most boring endpoint on the internet"}

@app.get("/s/{code}")
def redirect_url(code: str, session: Session = Depends(get_session)):
    address = session.scalars(select(Address).where(Address.id == code)).first()

    if address is None:
        raise HTTPException(
            status_code=404,
            detail="Short URL not found"
        )

    return RedirectResponse(
        url=address.url,
        status_code=302
    )


@app.post("/api/shorten")
@limiter.limit("5/day")
def shorten_url(
    data: ShortenRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    if not verify_turnstile_token(
        data.turnstile_token,
        request.client.host if request.client else None,
    ):
        raise HTTPException(status_code=403, detail="Complete the security check and try again.")

    code = ''.join(choice(alphabet) for _ in range(8))
    link = Address(id=code, url=str(data.url))
    session.add(link)
    session.commit()
    return {"short_url": f"https://winslinn.dpdns.org/s/{code}"}
